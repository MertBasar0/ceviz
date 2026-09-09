import Combine
import CryptoKit
import Foundation
import SQLite3

struct ConversationSessionScope: Equatable {
    fileprivate let generation: UUID
    let sessionKey: String
}

struct ConversationSessionState {
    var draft = ""
    var submission: ConversationSubmission = .idle
    var error: String?
}

/// One owner for navigation and process recovery. Drafts stay in memory; only
/// delivery identities and status cross the synchronous SQLite commit boundary.
@MainActor
final class ConversationSessionStore: ObservableObject {
    private var pairing: String
    private var generation = UUID()
    private var journal: ConversationDeliveryJournal?
    @Published private var entries: [String: ConversationSessionState] = [:]
    @Published private(set) var storageError: String?

    init(baseURL: String, token: String, databaseURL: URL? = nil) {
        pairing = Self.pairingIdentity(baseURL: baseURL, token: token)
        do {
            journal = try ConversationDeliveryJournal(url: databaseURL)
            try restore()
        } catch { storageFailed() }
    }

    private static func pairingIdentity(baseURL: String, token: String) -> String {
        // Length framing prevents ambiguous concatenation. Only this opaque
        // connection identifier is stored, never the URL or credential itself.
        let framed = "\(baseURL.utf8.count):\(baseURL)\(token)"
        return SHA256.hash(data: Data(framed.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    func synchronizeConnection(baseURL: String, token: String) {
        let updated = Self.pairingIdentity(baseURL: baseURL, token: token)
        guard updated != pairing else { return }
        pairing = updated
        generation = UUID()
        entries.removeAll()
        do { try restore() } catch { storageFailed() }
    }

    func scope(for sessionKey: String) -> ConversationSessionScope {
        ConversationSessionScope(generation: generation, sessionKey: sessionKey)
    }

    func isCurrent(_ scope: ConversationSessionScope) -> Bool { scope.generation == generation }

    func state(for scope: ConversationSessionScope) -> ConversationSessionState {
        guard isCurrent(scope) else { return ConversationSessionState() }
        return entries[scope.sessionKey] ?? ConversationSessionState()
    }

    func updateDraft(_ text: String, in scope: ConversationSessionScope) {
        guard isCurrent(scope) else { return }
        entries[scope.sessionKey, default: ConversationSessionState()].draft = text
    }

    func recordError(_ message: String, in scope: ConversationSessionScope) {
        guard isCurrent(scope) else { return }
        entries[scope.sessionKey, default: ConversationSessionState()].error = message
    }

    func beginSend(_ delivery: ConversationDelivery, in scope: ConversationSessionScope) -> Bool {
        guard isCurrent(scope), delivery.sessionKey == scope.sessionKey, storageError == nil,
              !state(for: scope).submission.preventsNewMessage else { return false }
        do {
            try persist(delivery, status: "unconfirmed")
            var value = state(for: scope)
            value.submission = .sending(delivery)
            value.error = nil
            entries[scope.sessionKey] = value
            return true
        } catch { storageFailed(); return false }
    }

    @discardableResult
    func acknowledge(_ receipt: OpenClawConversationReceipt, delivery: ConversationDelivery,
                     in scope: ConversationSessionScope) -> Bool {
        guard matches(delivery, in: scope), receipt.runId == delivery.requestId,
              case .sending = state(for: scope).submission else { return false }
        let status: String
        switch receipt.status {
        case "started", "in_flight": status = "running"
        case "pending": status = "queued"
        default: status = "unconfirmed"
        }
        let run = OpenClawConversationRun(runId: delivery.requestId,
            status: receipt.deliveryConfirmed ? status : "unconfirmed", detail: nil)
        return recordRun(run, delivery: delivery, in: scope)
    }

    func rejectSend(_ message: String, delivery: ConversationDelivery,
                    definitelyNotSent: Bool, in scope: ConversationSessionScope) {
        guard matches(delivery, in: scope), case .sending = state(for: scope).submission else { return }
        var value = state(for: scope)
        value.error = message
        // An interrupted send is already durable as unconfirmed. Never clear
        // that guard merely because its HTTP response or a disk write failed.
        value.submission = .tracking(delivery, run: nil)
        if definitelyNotSent {
            do {
                guard let journal else { throw ConversationDeliveryJournal.Failure.unavailable }
                try journal.execute("DELETE FROM deliveries WHERE pairing_id = ? AND session_key = ? AND request_id = ?",
                                    [pairing, delivery.sessionKey, delivery.requestId])
                value.submission = .idle
            } catch { storageFailed() }
        }
        entries[scope.sessionKey] = value
    }

    @discardableResult
    func recordRun(_ run: OpenClawConversationRun, delivery: ConversationDelivery,
                   in scope: ConversationSessionScope) -> Bool {
        guard matches(delivery, in: scope), run.runId == delivery.requestId else { return false }
        var value = state(for: scope)
        if case .reviewed = value.submission { return false }
        var persistedStatus = "unconfirmed"
        if case let .tracking(_, previous) = value.submission {
            if previous?.isTerminal == true { return false }
            persistedStatus = previous?.status ?? "unconfirmed"
        }
        let status = ConversationDeliveryJournal.statuses.contains(run.status) ? run.status : "unconfirmed"
        let verified = OpenClawConversationRun(runId: run.runId, status: status, detail: nil)
        do {
            if status != persistedStatus { try persist(delivery, status: status) }
        }
        catch {
            value.submission = .tracking(delivery, run: nil)
            entries[scope.sessionKey] = value
            storageFailed()
            return false
        }
        value.submission = .tracking(delivery, run: verified)
        if status != "unconfirmed" { value.draft = ""; value.error = nil }
        entries[scope.sessionKey] = value
        return true
    }

    @discardableResult
    func finishReview(_ delivery: ConversationDelivery, in scope: ConversationSessionScope) -> Bool {
        guard matches(delivery, in: scope), storageError == nil,
              case let .tracking(_, run) = state(for: scope).submission,
              run == nil || run?.status == "unconfirmed" else { return false }
        do {
            // This records the operator's decision, not an inferred run result.
            // The helper keeps the original request's no-replay record intact.
            try persist(delivery, status: "reviewed")
            entries[scope.sessionKey] = ConversationSessionState(submission: .reviewed(delivery))
            return true
        } catch { storageFailed(); return false }
    }

    private func matches(_ delivery: ConversationDelivery, in scope: ConversationSessionScope) -> Bool {
        isCurrent(scope) && delivery.sessionKey == scope.sessionKey && state(for: scope).submission.delivery == delivery
    }

    private func persist(_ delivery: ConversationDelivery, status: String) throws {
        guard let journal else { throw ConversationDeliveryJournal.Failure.unavailable }
        try journal.execute("""
            INSERT INTO deliveries (pairing_id, session_key, session_id, request_id, status) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pairing_id, session_key) DO UPDATE SET
                session_id = excluded.session_id, request_id = excluded.request_id, status = excluded.status
            """, [pairing, delivery.sessionKey, delivery.sessionId, delivery.requestId, status])
    }

    private func restore() throws {
        guard let journal else { throw ConversationDeliveryJournal.Failure.unavailable }
        let rows = try journal.execute("SELECT session_key, session_id, request_id, status FROM deliveries WHERE pairing_id = ?", [pairing])
        var recovered: [String: ConversationSessionState] = [:]
        for row in rows {
            guard row.count == 4, !row[0].isEmpty, !row[1].isEmpty, UUID(uuidString: row[2]) != nil,
                  ConversationDeliveryJournal.statuses.contains(row[3]) || row[3] == "reviewed" else {
                throw ConversationDeliveryJournal.Failure.unavailable
            }
            let delivery = ConversationDelivery(sessionKey: row[0], sessionId: row[1], requestId: row[2])
            let run = OpenClawConversationRun(runId: row[2], status: row[3], detail: nil)
            recovered[row[0]] = ConversationSessionState(submission:
                row[3] == "reviewed" ? .reviewed(delivery) : .tracking(delivery, run: run))
        }
        entries = recovered
    }

    private func storageFailed() {
        storageError = NSLocalizedString("Message tracking is unavailable. Restart Ceviz and check the conversation before sending again.", comment: "")
    }
}

/// System SQLite, not another dependency or a transcript store. The entire
/// native API is MainActor-owned; each prepared write is one durable commit.
private final class ConversationDeliveryJournal {
    enum Failure: Error { case unavailable }
    static let statuses: Set<String> = ["unconfirmed", "running", "queued", "completed", "failed", "aborted"]
    private var database: OpaquePointer?

    init(url: URL?) throws {
        let file: URL
        if let url { file = url }
        else {
            file = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                              appropriateFor: nil, create: true)
                .appendingPathComponent("Ceviz", isDirectory: true).appendingPathComponent("conversations.sqlite")
        }
        var directory = file.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                               attributes: [.posixPermissions: 0o700])
        var resources = URLResourceValues()
        resources.isExcludedFromBackup = true
        try directory.setResourceValues(resources)
        guard sqlite3_open_v2(file.path, &database, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil) == SQLITE_OK else {
            sqlite3_close(database); database = nil
            throw Failure.unavailable
        }
        do {
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
            #if os(iOS)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: file.path)
            #endif
            try execute("PRAGMA synchronous = FULL")
            let version = try execute("PRAGMA user_version").first?.first
            guard version == "0" || version == "1" else { throw Failure.unavailable }
            try execute("""
                CREATE TABLE IF NOT EXISTS deliveries (
                    pairing_id TEXT NOT NULL, session_key TEXT NOT NULL, session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('unconfirmed','running','queued','completed','failed','aborted','reviewed')),
                    PRIMARY KEY (pairing_id, session_key)
                )
                """)
            try execute("PRAGMA user_version = 1")
        } catch {
            sqlite3_close(database); database = nil
            throw error
        }
    }

    deinit { sqlite3_close(database) }

    @discardableResult
    func execute(_ sql: String, _ values: [String] = []) throws -> [[String]] {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else { throw Failure.unavailable }
        defer { sqlite3_finalize(statement) }
        for (index, value) in values.enumerated() {
            let result = value.withCString {
                sqlite3_bind_text(statement, Int32(index + 1), $0, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
            }
            guard result == SQLITE_OK else { throw Failure.unavailable }
        }
        var rows: [[String]] = []
        var result = sqlite3_step(statement)
        while result == SQLITE_ROW {
            rows.append((0..<sqlite3_column_count(statement)).map { index in
                sqlite3_column_text(statement, index).map { String(cString: $0) } ?? ""
            })
            result = sqlite3_step(statement)
        }
        guard result == SQLITE_DONE else { throw Failure.unavailable }
        return rows
    }
}
