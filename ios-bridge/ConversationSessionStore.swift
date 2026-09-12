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
    private var journal: CevizDeliveryDatabase?
    private static let statuses: Set<String> = ["unconfirmed", "running", "queued", "completed", "failed", "aborted"]
    @Published private var entries: [String: ConversationSessionState] = [:]
    @Published private(set) var storageError: String?

    init(baseURL: String, token: String, databaseURL: URL? = nil) {
        pairing = CevizDeliveryDatabase.pairingIdentity(baseURL: baseURL, token: token)
        do {
            journal = try CevizDeliveryDatabase(url: databaseURL)
            try restore()
        } catch { storageFailed() }
    }

    func synchronizeConnection(baseURL: String, token: String) {
        let updated = CevizDeliveryDatabase.pairingIdentity(baseURL: baseURL, token: token)
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
                guard let journal else { throw CevizDeliveryDatabase.Failure.unavailable }
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
        let status = Self.statuses.contains(run.status) ? run.status : "unconfirmed"
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
        guard let journal else { throw CevizDeliveryDatabase.Failure.unavailable }
        try journal.execute("""
            INSERT INTO deliveries (pairing_id, session_key, session_id, request_id, status) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pairing_id, session_key) DO UPDATE SET
                session_id = excluded.session_id, request_id = excluded.request_id, status = excluded.status
            """, [pairing, delivery.sessionKey, delivery.sessionId, delivery.requestId, status])
    }

    private func restore() throws {
        guard let journal else { throw CevizDeliveryDatabase.Failure.unavailable }
        let rows = try journal.execute("SELECT session_key, session_id, request_id, status FROM deliveries WHERE pairing_id = ?", [pairing])
        var recovered: [String: ConversationSessionState] = [:]
        for row in rows {
            guard row.count == 4, !row[0].isEmpty, !row[1].isEmpty, UUID(uuidString: row[2]) != nil,
                  Self.statuses.contains(row[3]) || row[3] == "reviewed" else {
                throw CevizDeliveryDatabase.Failure.unavailable
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
