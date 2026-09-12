import Foundation
import SQLite3

// swiftc job-state/CVZJobState.swift ios-bridge/Models.swift watch-transport/WatchCommandTransport.swift
// ios-bridge/CevizDeliveryDatabase.swift ios-bridge/WatchDeliveryStore.swift
// ios-bridge/WatchDeliveryCoordinator.swift tests/swift/WatchDeliveryTests.swift -lsqlite3 -o build/tests/watch-delivery-tests
// Real native SQLite and production delivery owners; only the HTTP peer is injected.
// Reopening a committed file models process recovery, not a physical power-loss test.
@main
@MainActor
struct WatchDeliveryTests {
    private static let baseURL = "https://ceviz-delivery-fixture.invalid"
    private static let token = "fixture-token-must-never-be-persisted"
    private static let audio = Data("fixture-audio-must-never-be-persisted".utf8).base64EncodedString()

    private enum ReplyLoss: Equatable { case beforeAcceptance, afterAcceptance }

    @MainActor
    private final class Peer {
        var ledger = UUID().uuidString.lowercased()
        var calls: [String] = []
        var submissions: [[String: Any]] = []
        var records: [String: [String: Any]] = [:]
        var loss: ReplyLoss?
        var beforeRequest: ((URLRequest) throws -> Void)?
        var duringSubmit: (() async throws -> Void)?
        var transformReceipt: (([String: Any]) -> [String: Any])?

        func load(_ request: URLRequest) async throws -> (Data, URLResponse) {
            precondition(request.url?.host == "ceviz-delivery-fixture.invalid", "Never contact a configured backend")
            precondition(request.value(forHTTPHeaderField: "Authorization") == "Bearer " + WatchDeliveryTests.token)
            let action = request.url!.lastPathComponent
            calls.append(action)
            try beforeRequest?(request)
            let response: [String: Any]
            if action == "capabilities" {
                precondition(request.httpMethod == "GET" && request.httpBody == nil)
                response = ["watch_command_recovery_v1": true, "watch_command_ledger_id": ledger]
            } else {
                precondition(request.httpMethod == "POST")
                let body = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
                let command = body["command_id"] as! String
                var metadata = body.filter { ["command_id", "audio_digest", "client_timestamp", "ledger_id", "continue_job_id"].contains($0.key) }
                if action == "status" {
                    precondition(body["audio_data"] == nil && body["format"] == nil, "Recovery queries carry metadata only")
                    metadata["delivery_state"] = body["ledger_id"] as? String == ledger ? "not_submitted" : "unknown"
                    response = body["ledger_id"] as? String == ledger ? (records[command] ?? metadata) : metadata
                } else {
                    precondition(action == "submit" && body["audio_data"] as? String == WatchDeliveryTests.audio)
                    submissions.append(body)
                    if let duringSubmit {
                        self.duringSubmit = nil
                        try await duringSubmit()
                    }
                    if loss == .beforeAcceptance {
                        loss = nil
                        throw URLError(.networkConnectionLost)
                    }
                    precondition(body["ledger_id"] as? String == ledger, "A changed ledger must never receive a rebound POST")
                    metadata["delivery_state"] = "accepted"
                    metadata["job_id"] = "job-" + command
                    let accepted = records[command] ?? metadata
                    records[command] = accepted
                    if loss == .afterAcceptance {
                        loss = nil
                        throw URLError(.networkConnectionLost)
                    }
                    response = transformReceipt?(accepted) ?? accepted
                }
            }
            return (try JSONSerialization.data(withJSONObject: response),
                    HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!)
        }
    }

    private static func owner(_ file: URL, isCurrent: @escaping () -> Bool = { true }) throws -> WatchDeliveryCoordinator {
        try WatchDeliveryCoordinator(baseURL: baseURL, token: token, databaseURL: file, isCurrent: isCurrent)
    }

    private static func incoming(_ owner: WatchDeliveryCoordinator, parent: String? = "job-parent") throws -> WatchCommandTransport.Incoming {
        let request = WatchCommandRequest(audioData: audio, format: "m4a",
            clientTimestamp: ISO8601DateFormatter().string(from: Date()), continueJobId: parent)
        return try WatchCommandTransport.decode(WatchCommandTransport.encode(request, commandID: UUID().uuidString,
            recoveryProtocol: 1, deliveryJournalID: owner.deliveryJournalID))
    }

    private static func mustFail(_ reason: String, _ operation: () async throws -> Void) async {
        do { try await operation(); preconditionFailure(reason) }
        catch { /* The caller separately asserts the persisted state and external call boundary. */ }
    }

    private static func rows(_ file: URL, _ query: String) -> [[String]] {
        var database: OpaquePointer?
        precondition(sqlite3_open_v2(file.path, &database, SQLITE_OPEN_READONLY, nil) == SQLITE_OK)
        defer { sqlite3_close(database) }
        var statement: OpaquePointer?
        precondition(sqlite3_prepare_v2(database, query, -1, &statement, nil) == SQLITE_OK)
        defer { sqlite3_finalize(statement) }
        var result: [[String]] = []
        var status = sqlite3_step(statement)
        while status == SQLITE_ROW {
            result.append((0..<sqlite3_column_count(statement)).map {
                sqlite3_column_text(statement, $0).map { String(cString: $0) } ?? ""
            })
            status = sqlite3_step(statement)
        }
        precondition(status == SQLITE_DONE)
        return result
    }

    private static func phase(_ file: URL) -> String? {
        rows(file, "SELECT phase FROM watch_deliveries").first?.first
    }

    static func main() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("ceviz-watch-delivery-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try await commitAndConcurrentDelivery(directory.appendingPathComponent("commit.sqlite"))
        try await lostReplyRecovery(directory.appendingPathComponent("lost-reply.sqlite"))
        try await failedAcknowledgementCommit(directory.appendingPathComponent("ack-locked.sqlite"))
        try await confirmedMissingRecovery(directory.appendingPathComponent("missing-on-helper.sqlite"))
        try await unknownRemainsReadOnly(directory.appendingPathComponent("unknown-on-helper.sqlite"))
        try await changedLedgerRecovery(directory.appendingPathComponent("changed-helper.sqlite"))
        try await missingStores(directory)
        try await invalidReceipts(directory)
        try await storageFaults(directory)
        try await corruptJournalIdentity(directory.appendingPathComponent("corrupt-journal-id.sqlite"))
        try await connectionReset(directory.appendingPathComponent("connection-reset.sqlite"))
        print("PASS: native Watch delivery commits, restart/ledger fencing, no-replay recovery, receipt identity, storage faults and metadata privacy")
    }

    private static func commitAndConcurrentDelivery(_ file: URL) async throws {
        let coordinator = try owner(file)
        let message = try incoming(coordinator)
        let peer = Peer()
        let ledger = peer.ledger
        peer.beforeRequest = { request in
            if request.url!.lastPathComponent == "capabilities" {
                precondition(phase(file) == "prepared", "Reservation must be externally readable before the first GET")
            } else if request.url!.lastPathComponent == "submit" {
                precondition(rows(file, "SELECT phase, ledger_id, job_id FROM watch_deliveries") == [["unconfirmed", ledger, ""]],
                             "The original helper ledger must commit before any POST")
            }
        }
        peer.duringSubmit = {
            let duplicate = try await coordinator.submit(message, load: { try await peer.load($0) })
            precondition(duplicate["status"] as? String == "in_flight", "Reentrant duplicate must not start another POST")
            let status = try await coordinator.status(message.identity!, load: { try await peer.load($0) })
            precondition(status["status"] as? String == "in_flight")
        }
        let result = try await coordinator.submit(message, load: { try await peer.load($0) })
        guard case .accepted(let data) = WatchCommandTransport.deliveryStatus(result, matching: message.identity!) else {
            preconditionFailure("The durable acknowledgement must satisfy the actual Watch reply decoder")
        }
        let receipt = try JSONDecoder().decode(WatchCommandResponse.self, from: data)
        precondition(receipt.status == "processing" && receipt.outcome == "unknown", "Acceptance is not task completion")
        precondition(peer.calls == ["capabilities", "submit"] && peer.submissions.count == 1)
        precondition(peer.submissions[0]["continue_job_id"] as? String == "job-parent")
        precondition(phase(file) == "accepted")
        let bytes = try Data(contentsOf: file)
        for privateValue in [baseURL, token, audio, "fixture-audio-must-never-be-persisted"] {
            precondition(bytes.range(of: Data(privateValue.utf8)) == nil, "No audio, credential or endpoint text belongs in SQLite")
        }
    }

    private static func lostReplyRecovery(_ file: URL) async throws {
        let peer = Peer()
        peer.loss = .afterAcceptance
        var first: WatchDeliveryCoordinator? = try owner(file)
        let message = try incoming(first!)
        let journalID = first!.deliveryJournalID
        await mustFail("Lost HTTP response must remain unconfirmed") { _ = try await first!.submit(message, load: { try await peer.load($0) }) }
        precondition(phase(file) == "unconfirmed" && peer.records.count == 1)
        first = nil
        let restarted = try owner(file)
        precondition(restarted.deliveryJournalID == journalID, "The phone journal epoch must survive owner restart")
        let response = try await restarted.status(message.identity!, load: { try await peer.load($0) })
        precondition(response["status"] as? String == "accepted" && phase(file) == "accepted")
        _ = try await restarted.submit(message, load: { try await peer.load($0) })
        precondition(peer.calls == ["capabilities", "submit", "status"] && peer.submissions.count == 1,
                     "Lost reply recovery must not send audio twice or refetch a new ledger")
    }

    private static func confirmedMissingRecovery(_ file: URL) async throws {
        let peer = Peer()
        peer.loss = .beforeAcceptance
        var first: WatchDeliveryCoordinator? = try owner(file)
        let message = try incoming(first!)
        await mustFail("A dropped POST does not prove non-delivery") { _ = try await first!.submit(message, load: { try await peer.load($0) }) }
        first = nil
        let restarted = try owner(file)
        let response = try await restarted.submit(message, load: { try await peer.load($0) })
        precondition(response["status"] as? String == "accepted")
        precondition(peer.calls == ["capabilities", "submit", "status", "submit"] && peer.records.count == 1)
        let firstBody = try JSONSerialization.data(withJSONObject: peer.submissions[0], options: [.sortedKeys])
        let replayBody = try JSONSerialization.data(withJSONObject: peer.submissions[1], options: [.sortedKeys])
        precondition(firstBody == replayBody, "Authoritative missing-row recovery must keep the exact identity, audio, parent and ORIGINAL ledger")
    }

    private static func failedAcknowledgementCommit(_ file: URL) async throws {
        var first: WatchDeliveryCoordinator? = try owner(file)
        let message = try incoming(first!)
        let peer = Peer()
        var lock: OpaquePointer?
        precondition(sqlite3_open_v2(file.path, &lock, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK)
        defer { sqlite3_close(lock) }
        peer.duringSubmit = {
            precondition(phase(file) == "unconfirmed")
            precondition(sqlite3_exec(lock, "BEGIN IMMEDIATE", nil, nil, nil) == SQLITE_OK)
        }
        await mustFail("An accepted response cannot retire audio until its SQLite receipt commits") {
            _ = try await first!.submit(message, load: { try await peer.load($0) })
        }
        precondition(peer.submissions.count == 1 && peer.records.count == 1 && phase(file) == "unconfirmed")
        precondition(sqlite3_exec(lock, "ROLLBACK", nil, nil, nil) == SQLITE_OK)
        first = nil
        let restarted = try owner(file)
        let response = try await restarted.status(message.identity!, load: { try await peer.load($0) })
        precondition(response["status"] as? String == "accepted" && phase(file) == "accepted")
        precondition(peer.calls == ["capabilities", "submit", "status"] && peer.submissions.count == 1,
                     "A failed local ACK commit must recover by identity lookup, never another POST")
    }

    private static func changedLedgerRecovery(_ file: URL) async throws {
        let peer = Peer()
        peer.loss = .beforeAcceptance
        var first: WatchDeliveryCoordinator? = try owner(file)
        let message = try incoming(first!)
        await mustFail("A failed POST must remain tracked") { _ = try await first!.submit(message, load: { try await peer.load($0) }) }
        first = nil
        peer.ledger = UUID().uuidString.lowercased()
        let restarted = try owner(file)
        let result = try await restarted.submit(message, load: { try await peer.load($0) })
        precondition(result["status"] as? String == "unknown" && phase(file) == "unconfirmed")
        precondition(peer.calls == ["capabilities", "submit", "status"] && peer.submissions.count == 1,
                     "Helper replacement cannot rebind an existing unconfirmed recording")
    }

    private static func unknownRemainsReadOnly(_ file: URL) async throws {
        let coordinator = try owner(file)
        let message = try incoming(coordinator)
        let peer = Peer()
        peer.loss = .beforeAcceptance
        await mustFail("A failed POST must remain tracked") { _ = try await coordinator.submit(message, load: { try await peer.load($0) }) }
        var uncertain = peer.submissions[0].filter { ["command_id", "audio_digest", "client_timestamp", "ledger_id", "continue_job_id"].contains($0.key) }
        uncertain["delivery_state"] = "unknown"
        peer.records[message.identity!.commandID] = uncertain
        let response = try await coordinator.submit(message, load: { try await peer.load($0) })
        precondition(response["status"] as? String == "unknown" && phase(file) == "unconfirmed")
        precondition(peer.calls == ["capabilities", "submit", "status"] && peer.submissions.count == 1,
                     "Even the original ledger cannot authorize replay without an explicit not_submitted result")
    }

    private static func missingStores(_ directory: URL) async throws {
        let peer = Peer()
        peer.loss = .afterAcceptance
        var first: WatchDeliveryCoordinator? = try owner(directory.appendingPathComponent("old-phone.sqlite"))
        let message = try incoming(first!)
        let oldJournalID = first!.deliveryJournalID
        await mustFail("Simulate an accepted command whose receipt was lost") { _ = try await first!.submit(message, load: { try await peer.load($0) }) }
        first = nil
        let replacement = try owner(directory.appendingPathComponent("replacement-phone.sqlite"))
        precondition(replacement.deliveryJournalID != oldJournalID)
        peer.ledger = UUID().uuidString.lowercased()
        peer.records.removeAll()
        peer.calls.removeAll()
        let status = try await replacement.status(message.identity!, load: { try await peer.load($0) })
        precondition(status["status"] as? String == "unknown" && peer.calls.isEmpty)
        await mustFail("A delayed old WC envelope must not bind to two replacement stores") {
            _ = try await replacement.submit(message, load: { try await peer.load($0) })
        }
        precondition(peer.calls.isEmpty && phase(directory.appendingPathComponent("replacement-phone.sqlite")) == nil,
                     "Wrong phone journal epoch must refuse BEFORE reserve, capability GET or POST")
        for protocolVersion in [nil, 1] as [Int?] {
            let legacy = WatchCommandTransport.Incoming(request: message.request, identity: message.identity,
                recoveryProtocol: protocolVersion, deliveryJournalID: nil)
            await mustFail("An old or unpinned queue is not a newly authorized capture") {
                _ = try await replacement.submit(legacy, load: { try await peer.load($0) })
            }
        }
        precondition(peer.calls.isEmpty)
    }

    private static func invalidReceipts(_ directory: URL) async throws {
        let changes: [(String, Any)] = [("command_id", UUID().uuidString), ("audio_digest", String(repeating: "0", count: 64)),
            ("ledger_id", UUID().uuidString), ("client_timestamp", "2001-01-01T00:00:00Z"),
            ("continue_job_id", "job-other-parent"), ("job_id", ""), ("delivery_state", "unexpected")]
        for (index, change) in changes.enumerated() {
            let file = directory.appendingPathComponent("invalid-\(index).sqlite")
            let coordinator = try owner(file)
            let message = try incoming(coordinator)
            let peer = Peer()
            peer.transformReceipt = { var result = $0; result[change.0] = change.1; return result }
            await mustFail("A mismatched or malformed receipt must never acknowledge audio") {
                _ = try await coordinator.submit(message, load: { try await peer.load($0) })
            }
            precondition(phase(file) == "unconfirmed" && peer.submissions.count == 1)
        }
    }

    private static func storageFaults(_ directory: URL) async throws {
        let corrupt = directory.appendingPathComponent("corrupt.sqlite")
        let original = Data("not a SQLite database".utf8)
        try original.write(to: corrupt)
        await mustFail("Corrupt storage must not become an empty ledger") { _ = try owner(corrupt) }
        let unchanged = try Data(contentsOf: corrupt)
        precondition(unchanged == original)

        for beforeReservation in [true, false] {
            let file = directory.appendingPathComponent(beforeReservation ? "reserve-locked.sqlite" : "bind-locked.sqlite")
            let coordinator = try owner(file)
            let message = try incoming(coordinator)
            let peer = Peer()
            var lock: OpaquePointer?
            precondition(sqlite3_open_v2(file.path, &lock, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK)
            defer { sqlite3_exec(lock, "ROLLBACK", nil, nil, nil); sqlite3_close(lock) }
            if beforeReservation { precondition(sqlite3_exec(lock, "BEGIN IMMEDIATE", nil, nil, nil) == SQLITE_OK) }
            else {
                peer.beforeRequest = { request in
                    precondition(request.url?.lastPathComponent == "capabilities")
                    precondition(sqlite3_exec(lock, "BEGIN IMMEDIATE", nil, nil, nil) == SQLITE_OK)
                }
            }
            await mustFail("A failed reservation/ledger commit must stop before POST") {
                _ = try await coordinator.submit(message, load: { try await peer.load($0) })
            }
            precondition(peer.calls == (beforeReservation ? [] : ["capabilities"]) && peer.submissions.isEmpty)
            precondition(phase(file) == (beforeReservation ? nil : "prepared"))
        }
    }

    private static func connectionReset(_ file: URL) async throws {
        var current = true
        let coordinator = try owner(file, isCurrent: { current })
        let message = try incoming(coordinator)
        let peer = Peer()
        peer.beforeRequest = { request in
            precondition(request.url?.lastPathComponent == "capabilities")
            current = false
        }
        await mustFail("A pairing reset after GET must not bind or submit") {
            _ = try await coordinator.submit(message, load: { try await peer.load($0) })
        }
        precondition(peer.calls == ["capabilities"] && phase(file) == "prepared")
    }

    private static func corruptJournalIdentity(_ file: URL) async throws {
        var first: WatchDeliveryCoordinator? = try owner(file)
        precondition(UUID(uuidString: first!.deliveryJournalID) != nil)
        first = nil
        var database: OpaquePointer?
        precondition(sqlite3_open_v2(file.path, &database, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK)
        precondition(sqlite3_exec(database, "UPDATE watch_delivery_metadata SET journal_id = 'invalid-existing-epoch'", nil, nil, nil) == SQLITE_OK)
        precondition(sqlite3_close(database) == SQLITE_OK)
        await mustFail("A corrupt existing phone epoch must never be silently regenerated") { _ = try owner(file) }
        precondition(rows(file, "SELECT journal_id FROM watch_delivery_metadata") == [["invalid-existing-epoch"]])
    }
}
