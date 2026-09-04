import Foundation

// swiftc job-state/CVZJobState.swift ios-bridge/Models.swift tests/swift/JobStateTests.swift -o /tmp/ceviz-job-state-tests
@main
struct JobStateTests {
    static func main() throws {
        let cases: [(String, String?, CVZJobState)] = [
            ("completed", "done", .completed),
            ("completed", "blocked", .blocked),
            ("completed", "needs_input", .needsInput),
            ("completed", "unknown", .resultReady),
            ("completed", nil, .resultReady),
            ("completed", "success", .resultReady),
            ("running", "done", .running),
            ("processing", "needs_input", .running),
            ("queued", "blocked", .queued),
            ("failed", "done", .failed),
            ("error", "needs_input", .unknown),
            ("cancelled", "done", .unknown),
            ("unknown", "done", .unknown),
            (" COMPLETED ", " NEEDS_INPUT ", .needsInput),
        ]
        for (status, outcome, expected) in cases {
            precondition(CVZJobState.resolve(status: status, outcome: outcome) == expected,
                         "Wrong presentation for \(status)/\(outcome ?? "missing")")
        }
        precondition(CVZJobState.needsInput.needsAttention)
        precondition(CVZJobState.blocked.isReportedResult)
        precondition(!CVZJobState.failed.isReportedResult)
        precondition(!CVZJobState.running.needsAttention)

        // Upgrading the phone before the backend must keep old jobs readable.
        var payload: [String: Any] = [
            "id": "job-upgrade", "name": "Check a task", "status": "completed",
            "elapsed_seconds": 1, "summary_text": "An agent report, not execution proof.",
            "requires_phone_handoff": false, "transcript": "Check a task", "phone_report": "Report",
        ]
        func decode() throws -> ActiveJob {
            try JSONDecoder().decode(ActiveJob.self, from: JSONSerialization.data(withJSONObject: payload))
        }
        func expect(_ expected: CVZJobState) throws {
            let job = try decode()
            precondition(job.presentationState == expected)
        }
        try expect(.resultReady)
        payload["report_meta"] = [
            "category": "general", "watch_summary": "More detail needed",
            "requires_phone_handoff": true, "phone_report": "Report", "retry_count": 0,
            "outcome": "needs_input",
        ]
        try expect(.needsInput)
        payload["outcome"] = "blocked"
        try expect(.blocked)
        payload["status"] = "running"
        try expect(.running)
        payload["status"] = "failed"
        try expect(.failed)
        print("PASS: \(cases.count) state cases and 5 iOS payload upgrade/precedence cases")
    }
}
