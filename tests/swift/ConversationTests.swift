import Foundation

// swiftc ios-bridge/ConversationModels.swift ios-bridge/ConversationSessionStore.swift tests/swift/ConversationTests.swift -o /tmp/conversation-tests
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

        precondition(!ConversationSubmission.idle.preventsNewMessage)
        precondition(ConversationSubmission.sending(payload).isSending)
        precondition(ConversationSubmission.sending(payload).preventsNewMessage)
        precondition(ConversationSubmission.tracking(payload, runId: payload.requestId, run: nil).preventsNewMessage,
                     "An unconfirmed send must not turn into a new request")
        for status in ["running", "queued", "unconfirmed", "new-unrecognized-status"] {
            let run = OpenClawConversationRun(runId: payload.requestId, status: status, detail: nil)
            precondition(!run.isTerminal)
            precondition(ConversationSubmission.tracking(payload, runId: payload.requestId, run: run).preventsNewMessage)
        }
        for status in ["completed", "failed", "aborted"] {
            let run = OpenClawConversationRun(runId: payload.requestId, status: status, detail: nil)
            precondition(run.isTerminal)
            precondition(!ConversationSubmission.tracking(payload, runId: payload.requestId, run: run).preventsNewMessage)
            precondition(run.statusKey != "Completed", "Run completion must not claim the user's task succeeded")
            if status == "completed" {
                precondition(run.statusKey == "Run finished — review the conversation.",
                             "A terminal run alone does not prove a visible response exists")
            }
        }
        let store = ConversationSessionStore(baseURL: "https://ceviz.example", token: "fixture-only")
        let scope = store.scope(for: payload.sessionKey)
        store.update(scope) {
            $0.draft = payload.text
            $0.submission = .tracking(payload, runId: payload.requestId, run: nil)
        }
        let reopened = store.state(for: store.scope(for: payload.sessionKey))
        precondition(reopened.draft == payload.text && reopened.submission.preventsNewMessage,
                     "Back and reopen must retain the unconfirmed identity, draft and send lock")
        guard case let .tracking(retained, _, _) = reopened.submission else { preconditionFailure() }
        precondition(retained.requestId == payload.requestId)
        precondition(store.state(for: store.scope(for: "agent:personal:main")).draft.isEmpty)
        store.synchronizeConnection(baseURL: "https://ceviz.example", token: "fixture-only")
        precondition(store.isCurrent(scope) && store.state(for: scope).submission.preventsNewMessage,
                     "Saving unchanged pairing settings is not a new delivery context")
        let terminal = OpenClawConversationRun(runId: payload.requestId, status: "completed", detail: nil)
        precondition(store.recordRun(terminal, request: payload, in: scope))
        let stalePoll = OpenClawConversationRun(runId: payload.requestId, status: "queued", detail: nil)
        precondition(!store.recordRun(stalePoll, request: payload, in: scope),
                     "A slower poll from a previous screen cannot regress terminal state")
        store.synchronizeConnection(baseURL: "https://ceviz.example", token: "changed-fixture")
        precondition(!store.isCurrent(scope))
        store.update(scope) { $0.draft = "stale receipt from previous pairing" }
        let newPairingState = store.state(for: store.scope(for: payload.sessionKey))
        precondition(newPairingState.draft.isEmpty && !newPairingState.submission.preventsNewMessage,
                     "Pairing changes clear state and reject late callbacks from the prior connection")
        print("PASS: conversation discovery/history decoding, canonical routing, null leaf guard, and conservative delivery state")
    }
}
