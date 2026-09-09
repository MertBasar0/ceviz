import Foundation

// swiftc job-state/CVZJobState.swift ios-bridge/Models.swift tests/swift/PhoneCommandTests.swift -o /tmp/phone-command-tests
@main
struct PhoneCommandTests {
    static func main() throws {
        func payload(_ command: PhoneJobCommand) throws -> [String: String] {
            try JSONDecoder().decode([String: String].self, from: JSONEncoder().encode(command))
        }
        let followUp = try payload(.followUp(jobId: "job-reviewed", text: "Explain the risk first", locale: "en_US"))
        precondition(followUp == [
            "intent": "follow_up", "continue_job_id": "job-reviewed",
            "text": "Explain the risk first", "locale": "en_US",
        ], "A free-form follow-up must never carry suggestion approval")
        let approval = try payload(.approveSuggestion(jobId: "job-reviewed", actionId: "suggested-next-action", locale: "tr_TR"))
        precondition(approval == [
            "intent": "approve_suggestion", "continue_job_id": "job-reviewed",
            "next_action_id": "suggested-next-action", "locale": "tr_TR",
        ], "Approval references the server-owned action and never supplies replacement text")

        let oldPayload = Data(#"{"audio_data":"YQ==","format":"m4a","client_timestamp":"2026-09-09T00:00:00Z"}"#.utf8)
        var request = try JSONDecoder().decode(WatchCommandRequest.self, from: oldPayload)
        precondition(request.continueJobId == nil, "Legacy captures must not gain an inferred target")
        request.continueJobId = "job-visible-on-watch"
        let forwarded = try JSONDecoder().decode(WatchCommandRequest.self, from: JSONEncoder().encode(request))
        precondition(forwarded.continueJobId == "job-visible-on-watch", "The phone preserves the Watch-selected continuation")
        print("PASS: follow-up/approval separation and unchanged Watch continuation forwarding")
    }
}
