import Foundation
import SQLite3

// swiftc ios-bridge/ConversationModels.swift ios-bridge/ConversationSessionStore.swift tests/swift/ConversationTests.swift -lsqlite3 -o /tmp/conversation-tests
@main
struct ConversationTests {
    @MainActor
    static func main() throws {
        let response = try JSONDecoder().decode(OpenClawConversationsResponse.self, from: Data(#"""
        {
          "sessions": [
            {"session_key":"agent:research:main","session_id":"session-a","agent_id":"research","title":"Release comparison","preview":"Review the test results","updated_at_ms":1788900000000,"is_running":true,"archived":false,"status":"running","active_leaf_entry_id":"leaf-a","can_send":false},
            {"session_key":"agent:personal:main","session_id":"session-b","agent_id":"personal","title":"Travel notes","preview":null,"updated_at_ms":null,"is_running":false,"archived":true,"status":null,"active_leaf_entry_id":null,"can_send":false}
          ],
          "agents":[{"id":"research","name":"Research"},{"id":"personal","name":"Personal"}],
          "has_more":true,"next_offset":50
        }
        """#.utf8))
        precondition(response.sessions.map(\.sessionKey) == ["agent:research:main", "agent:personal:main"])
        precondition(response.nextOffset == 50 && response.hasMore)
        precondition(response.sessions[0].updatedAt?.timeIntervalSince1970 == 1788900000)
        precondition(response.sessions[1].updatedAt == nil && response.sessions[1].archived)

        let history = try JSONDecoder().decode(OpenClawConversationHistory.self, from: Data(#"""
        {
          "session":{"session_key":"agent:research:main","session_id":"session-a","agent_id":"research","title":"Release comparison","preview":null,"updated_at_ms":null,"is_running":false,"archived":false,"status":null,"active_leaf_entry_id":null,"can_send":true},
          "messages":[{"id":"message-a","role":"user","text":"","timestamp_ms":null,"has_other_content":true}],
          "has_more":true,"next_offset":100,"active_run_ids":[],"pending_count":0
        }
        """#.utf8))
        precondition(history.session.canSend && history.session.activeLeafEntryId == nil)
        precondition(history.messages[0].text.isEmpty && history.messages[0].hasOtherContent,
                     "An attachment-only message remains visible through its content placeholder")

        let payload = OpenClawConversationRequest(
            sessionKey: history.session.sessionKey, sessionId: history.session.sessionId!,
            text: "Explain the next step", requestId: "A54760AC-237A-4E53-8C84-C1ECB1200FE8", expectedLeafEntryId: nil
        )
        let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(payload)) as! [String: Any]
        precondition(encoded["session_key"] as? String == "agent:research:main")
        precondition(encoded["session_id"] as? String == "session-a")
        precondition(encoded["expected_leaf_entry_id"] is NSNull,
                     "A known empty leaf must be sent as explicit JSON null, not omitted")
        precondition(encoded["request_id"] as? String == payload.requestId)
        precondition(encoded["continue_job_id"] == nil && encoded["agent_id"] == nil,
                     "Actual OpenClaw conversations never become Ceviz job continuations or implicit-agent requests")

        let delivery = payload.delivery
        precondition(delivery.sessionKey == payload.sessionKey && delivery.sessionId == payload.sessionId && delivery.requestId == payload.requestId)
        precondition(!ConversationSubmission.idle.preventsNewMessage)
        precondition(ConversationSubmission.sending(delivery).isSending)
        precondition(ConversationSubmission.sending(delivery).preventsNewMessage)
        precondition(ConversationSubmission.tracking(delivery, run: nil).preventsNewMessage,
                     "An unconfirmed send must not turn into a new request")
        for status in ["running", "queued", "unconfirmed", "new-unrecognized-status"] {
            let run = OpenClawConversationRun(runId: payload.requestId, status: status, detail: nil)
            precondition(!run.isTerminal)
            precondition(ConversationSubmission.tracking(delivery, run: run).preventsNewMessage)
        }
        for status in ["completed", "failed", "aborted"] {
            let run = OpenClawConversationRun(runId: payload.requestId, status: status, detail: nil)
            precondition(run.isTerminal)
            precondition(!ConversationSubmission.tracking(delivery, run: run).preventsNewMessage)
            precondition(run.statusKey != "Completed", "Run completion must not claim the user's task succeeded")
            if status == "completed" {
                precondition(run.statusKey == "Run finished — review the conversation.",
                             "A terminal run alone does not prove a visible response exists")
            }
        }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("ceviz-delivery-tests-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try verifyRestartRecovery(payload, directory: directory)
        verifyTerminalAndPairing(delivery, directory: directory)
        verifyExplicitReview(delivery, directory: directory)
        try verifyStorageFaults(delivery, directory: directory)
        print("PASS: conversation routing, durable recovery without message/credential persistence, explicit review, and fail-closed SQLite faults")
    }

    private static let baseURL = "https://ceviz-test-private.example"
    private static let token = "ceviz-test-private-token"

    @MainActor
    private static func store(_ file: URL) -> ConversationSessionStore {
        ConversationSessionStore(baseURL: baseURL, token: token, databaseURL: file)
    }

    @MainActor
    private static func tracking(_ owner: ConversationSessionStore, _ delivery: ConversationDelivery, status: String?) {
        let state = owner.state(for: owner.scope(for: delivery.sessionKey))
        guard case let .tracking(saved, run) = state.submission else { preconditionFailure("Expected a tracked delivery") }
        precondition(saved == delivery && run?.status == status, "The exact target, request identity and known outcome survive")
    }

    private static func run(_ delivery: ConversationDelivery, _ status: String) -> OpenClawConversationRun {
        OpenClawConversationRun(runId: delivery.requestId, status: status, detail: nil)
    }

    private static func receipt(_ delivery: ConversationDelivery, _ status: String, confirmed: Bool = true) -> OpenClawConversationReceipt {
        OpenClawConversationReceipt(runId: delivery.requestId, status: status, deliveryConfirmed: confirmed)
    }

    @MainActor
    private static func verifyRestartRecovery(_ payload: OpenClawConversationRequest, directory: URL) throws {
        for scenario in ["during-send", "uncertain-receipt", "uncertain-error"] {
            let file = directory.appendingPathComponent(scenario + ".sqlite")
            let delivery = payload.delivery
            do {
                let owner = store(file)
                precondition(owner.storageError == nil)
                let scope = owner.scope(for: delivery.sessionKey)
                owner.updateDraft(payload.text, in: scope)
                precondition(owner.beginSend(delivery, in: scope))
                precondition(owner.state(for: scope).submission.isSending)
                precondition(!owner.beginSend(delivery, in: scope) && !owner.finishReview(delivery, in: scope))
                if scenario == "uncertain-receipt" {
                    precondition(owner.acknowledge(receipt(delivery, "unconfirmed", confirmed: false), delivery: delivery, in: scope))
                } else if scenario == "uncertain-error" {
                    owner.rejectSend("Fixture connection ended", delivery: delivery, definitelyNotSent: false, in: scope)
                }
                let revisited = owner.state(for: owner.scope(for: delivery.sessionKey))
                precondition(revisited.draft == payload.text && revisited.submission.preventsNewMessage,
                             "Navigation preserves the draft and lock while the current process lives")
            }
            let restarted = store(file)
            precondition(restarted.storageError == nil)
            tracking(restarted, delivery, status: "unconfirmed")
            let recovered = restarted.state(for: restarted.scope(for: delivery.sessionKey))
            precondition(recovered.draft.isEmpty && recovered.submission.preventsNewMessage,
                         "Restart recovers the delivery guard, never a stored message body")
            let bytes = try Data(contentsOf: file)
            for privateValue in [payload.text, baseURL, token] {
                precondition(bytes.range(of: Data(privateValue.utf8)) == nil, "The SQLite file must not contain message, URL or credential text")
            }
        }
    }

    @MainActor
    private static func verifyTerminalAndPairing(_ delivery: ConversationDelivery, directory: URL) {
        for status in ["completed", "failed", "aborted"] {
            let file = directory.appendingPathComponent(status + ".sqlite")
            let owner = store(file)
            let scope = owner.scope(for: delivery.sessionKey)
            owner.updateDraft("Transient draft", in: scope)
            precondition(owner.beginSend(delivery, in: scope))
            precondition(owner.acknowledge(receipt(delivery, "started"), delivery: delivery, in: scope))
            precondition(owner.state(for: scope).draft.isEmpty)
            precondition(!owner.finishReview(delivery, in: scope), "An active run cannot be dismissed as merely unconfirmed")
            precondition(owner.recordRun(run(delivery, status), delivery: delivery, in: scope))
            precondition(!owner.recordRun(run(delivery, "queued"), delivery: delivery, in: scope))
            owner.rejectSend("Stale rejection", delivery: delivery, definitelyNotSent: true, in: scope)
            precondition(!owner.acknowledge(receipt(delivery, "pending"), delivery: delivery, in: scope))
            tracking(owner, delivery, status: status)
            precondition(owner.state(for: scope).error == nil, "Late send callbacks cannot damage a terminal result")
            let restarted = store(file)
            tracking(restarted, delivery, status: status)
            precondition(!restarted.recordRun(run(delivery, "queued"), delivery: delivery, in: restarted.scope(for: delivery.sessionKey)))
        }

        let owner = store(directory.appendingPathComponent("pairings.sqlite"))
        let firstScope = owner.scope(for: delivery.sessionKey)
        precondition(owner.beginSend(delivery, in: firstScope))
        owner.rejectSend("Unknown", delivery: delivery, definitelyNotSent: false, in: firstScope)
        owner.synchronizeConnection(baseURL: baseURL, token: token)
        precondition(owner.isCurrent(firstScope), "Saving unchanged settings preserves the delivery generation")
        owner.synchronizeConnection(baseURL: baseURL, token: "a-different-test-token")
        let otherScope = owner.scope(for: delivery.sessionKey)
        precondition(!owner.isCurrent(firstScope) && !owner.state(for: otherScope).submission.preventsNewMessage)
        owner.updateDraft("Stale draft", in: firstScope)
        owner.recordError("Stale error", in: firstScope)
        owner.rejectSend("Stale rejection", delivery: delivery, definitelyNotSent: true, in: firstScope)
        precondition(!owner.acknowledge(receipt(delivery, "started"), delivery: delivery, in: firstScope))
        precondition(!owner.recordRun(run(delivery, "completed"), delivery: delivery, in: firstScope))
        precondition(owner.state(for: otherScope).draft.isEmpty && owner.state(for: otherScope).error == nil)
        owner.synchronizeConnection(baseURL: baseURL, token: token)
        tracking(owner, delivery, status: "unconfirmed")
        precondition(!owner.isCurrent(firstScope) && !owner.isCurrent(otherScope), "Returning to a pairing restores data, not old callback authority")
        precondition(!owner.recordRun(run(delivery, "completed"), delivery: delivery, in: firstScope))
    }

    @MainActor
    private static func verifyExplicitReview(_ delivery: ConversationDelivery, directory: URL) {
        let file = directory.appendingPathComponent("reviewed.sqlite")
        let owner = store(file)
        let scope = owner.scope(for: delivery.sessionKey)
        owner.updateDraft("Do not restore or resubmit this draft", in: scope)
        precondition(owner.beginSend(delivery, in: scope))
        precondition(owner.acknowledge(receipt(delivery, "pending"), delivery: delivery, in: scope))
        precondition(!owner.finishReview(delivery, in: scope), "Queued work cannot be dismissed as an unknown send")
        precondition(owner.recordRun(run(delivery, "unconfirmed"), delivery: delivery, in: scope))
        owner.updateDraft("Transient draft before explicit review", in: scope)
        precondition(owner.finishReview(delivery, in: scope))
        guard case let .reviewed(reviewed) = owner.state(for: scope).submission else { preconditionFailure() }
        precondition(reviewed == delivery && owner.state(for: scope).draft.isEmpty)
        precondition(!owner.recordRun(run(delivery, "completed"), delivery: delivery, in: scope))
        owner.rejectSend("Late rejection", delivery: delivery, definitelyNotSent: false, in: scope)
        precondition(!owner.acknowledge(receipt(delivery, "started"), delivery: delivery, in: scope))
        precondition(!owner.state(for: scope).submission.preventsNewMessage && owner.state(for: scope).error == nil)
        let restarted = store(file)
        let restoredScope = restarted.scope(for: delivery.sessionKey)
        guard case let .reviewed(restored) = restarted.state(for: restoredScope).submission else { preconditionFailure() }
        precondition(restored == delivery && restarted.state(for: restoredScope).draft.isEmpty,
                     "Review persists as an operator decision while retaining the original identity")
        let next = ConversationDelivery(sessionKey: delivery.sessionKey, sessionId: delivery.sessionId, requestId: UUID().uuidString)
        precondition(restarted.beginSend(next, in: restoredScope))
        restarted.rejectSend("An old response cannot clear the new request", delivery: delivery, definitelyNotSent: true, in: restoredScope)
        precondition(restarted.state(for: restoredScope).submission.delivery == next && restarted.state(for: restoredScope).submission.isSending)
        restarted.rejectSend("Definitely not dispatched", delivery: next, definitelyNotSent: true, in: restoredScope)
        precondition(!restarted.state(for: restoredScope).submission.preventsNewMessage)
        let afterRejection = store(file)
        precondition(afterRejection.state(for: afterRejection.scope(for: delivery.sessionKey)).submission.delivery == nil,
                     "A definite non-send may clear its own durable reservation")
    }

    @MainActor
    private static func verifyStorageFaults(_ delivery: ConversationDelivery, directory: URL) throws {
        for afterDispatch in [false, true] {
            let file = directory.appendingPathComponent(afterDispatch ? "ack-write-fault.sqlite" : "reservation-write-fault.sqlite")
            let owner = store(file)
            let scope = owner.scope(for: delivery.sessionKey)
            owner.updateDraft("Transient unsent text", in: scope)
            if afterDispatch { precondition(owner.beginSend(delivery, in: scope)) }
            withDatabase(file) { database in
                sql("BEGIN IMMEDIATE", on: database)
                defer { sql("ROLLBACK", on: database) }
                if afterDispatch {
                    precondition(!owner.acknowledge(receipt(delivery, "started"), delivery: delivery, in: scope))
                    tracking(owner, delivery, status: nil)
                    precondition(owner.state(for: scope).submission.preventsNewMessage)
                } else {
                    precondition(!owner.beginSend(delivery, in: scope), "A failed reservation must prevent the HTTP send")
                    precondition(owner.state(for: scope).submission.delivery == nil)
                }
                precondition(owner.storageError != nil && !owner.finishReview(delivery, in: scope))
                precondition(!owner.beginSend(delivery, in: scope))
            }
            let restarted = store(file)
            precondition(restarted.storageError == nil)
            if afterDispatch { tracking(restarted, delivery, status: "unconfirmed") }
            else { precondition(restarted.state(for: restarted.scope(for: delivery.sessionKey)).submission.delivery == nil) }
        }
        let corrupt = directory.appendingPathComponent("corrupt.sqlite")
        try Data("This is not a SQLite database".utf8).write(to: corrupt)
        let future = directory.appendingPathComponent("future.sqlite")
        withDatabase(future) { sql("PRAGMA user_version = 99", on: $0) }
        let cannotOpen = directory.appendingPathComponent("directory-not-database", isDirectory: true)
        try FileManager.default.createDirectory(at: cannotOpen, withIntermediateDirectories: true)
        for file in [corrupt, future, cannotOpen] {
            let owner = store(file)
            precondition(owner.storageError != nil && !owner.beginSend(delivery, in: owner.scope(for: delivery.sessionKey)),
                         "Corrupt, unsupported and unavailable stores must never become empty writable history")
        }
        withDatabase(future) { database in
            var statement: OpaquePointer?
            precondition(sqlite3_prepare_v2(database, "PRAGMA user_version", -1, &statement, nil) == SQLITE_OK)
            defer { sqlite3_finalize(statement) }
            precondition(sqlite3_step(statement) == SQLITE_ROW && sqlite3_column_int(statement, 0) == 99,
                         "An unsupported future schema must not be silently downgraded")
        }
    }

    private static func withDatabase(_ file: URL, _ body: (OpaquePointer) -> Void) {
        var database: OpaquePointer?
        precondition(sqlite3_open_v2(file.path, &database, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nil) == SQLITE_OK)
        guard let database else { preconditionFailure("SQLite fixture did not open") }
        defer { sqlite3_close(database) }
        body(database)
    }

    private static func sql(_ statement: String, on database: OpaquePointer) {
        precondition(sqlite3_exec(database, statement, nil, nil, nil) == SQLITE_OK, "SQLite fixture setup failed")
    }
}
