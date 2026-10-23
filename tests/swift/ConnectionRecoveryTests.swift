import Foundation

@main
struct ConnectionRecoveryTests {
    static func main() throws {
        let current = "https://host.example/ceviz"
        for equivalent in [current, "  https://HOST.example:443/ceviz/  ", current + "/"] {
            precondition(BackendEndpointPolicy.isSameConnection(current, token: "token", as: equivalent, token: " token\n"),
                         "Same-pair refresh must not discard queued Watch audio")
        }
        for different in ["https://other.example/ceviz", "https://host.example/other", "http://host.example/ceviz",
                          "https://host.example:444/ceviz", "https://host.example/Ceviz"] {
            precondition(!BackendEndpointPolicy.isSameConnection(current, token: "token", as: different, token: "token"))
        }
        precondition(!BackendEndpointPolicy.isSameConnection(current, token: "old", as: current, token: "new"),
                     "An actual credential/backend change still invalidates old delivery authority")
        let relay = "http://192.168.1.2:8080"
        precondition(BackendEndpointPolicy.isAllowed(relay, connectionMethod: "relay"))
        for method in ["manual", "tailscale"] {
            precondition(!BackendEndpointPolicy.isAllowed(relay, connectionMethod: method),
                         "Changing mode cannot persist an invalid effective endpoint during a same-URL refresh")
        }

        let source: [[String: Any]] = (0..<50).map { index in
            ["id": "job-\(index)", "name": String(repeating: "界", count: 100), "status": "completed", "outcome": "done",
             "elapsed_seconds": index, "summary_text": String(repeating: "\(index)\u{301}", count: 5000),
             "requires_phone_handoff": true, "transcript": String(repeating: "voice", count: 10000),
             "phone_report": String(repeating: "private phone report", count: 10000)]
        }
        let original: [String: Any] = ["jobs": source]
        let originalBytes = try PropertyListSerialization.data(fromPropertyList: original, format: .binary, options: 0)
        precondition(originalBytes.count > WatchJobSnapshot.maximumReplyBytes, "Fixture must exercise the oversized full-report reply")
        let reply = try WatchJobSnapshot.reply(from: JSONSerialization.data(withJSONObject: original))
        let encoded = try JSONSerialization.data(withJSONObject: reply)
        let decoded = try JSONDecoder().decode(ActiveJobsResponse.self, from: encoded)
        precondition(decoded.jobs.map(\.id) == source.map { $0["id"] as! String }, "All 50 normal job identities remain discoverable")
        precondition(decoded.jobs.last?.outcome == "done" && decoded.jobs.last?.requiresPhoneHandoff == true)
        precondition(decoded.jobs.allSatisfy { $0.transcript.isEmpty && $0.phoneReport.isEmpty && $0.reportMeta == nil })
        precondition(decoded.jobs.allSatisfy { $0.name.utf8.count <= 160 && !$0.name.contains("\u{FFFD}") },
                     "Byte limits must preserve readable Unicode, not split a character into replacement glyphs")
        let bytes = try PropertyListSerialization.data(fromPropertyList: reply, format: .binary, options: 0)
        precondition(bytes.count <= WatchJobSnapshot.maximumReplyBytes)
        precondition(reply["has_more"] as? Bool == false)
        let later = source.enumerated().map { index, row -> [String: Any] in
            var row = row
            row["id"] = "job-later-\(index)"
            return row
        }
        let expanded = try WatchJobSnapshot.reply(from: JSONSerialization.data(withJSONObject: ["jobs": source + later]))
        precondition(expanded["has_more"] as? Bool == true, "A bounded history must disclose truncation")
        let newest = try JSONDecoder().decode(ActiveJobsResponse.self, from: JSONSerialization.data(withJSONObject: expanded))
        precondition(newest.jobs.map(\.id) == later.map { $0["id"] as! String })

        var malformed = source
        malformed[3].removeValue(forKey: "status")
        do {
            _ = try WatchJobSnapshot.reply(from: JSONSerialization.data(withJSONObject: ["jobs": malformed]))
            preconditionFailure("Malformed jobs must produce an explicit error, not a misleading empty/success reply")
        } catch {}
        // A question carries its answers to Watch; every other action stays on iPhone.
        let question: [String: Any] = [
            "id": "job-question", "name": "Logs", "status": "completed", "outcome": "needs_input",
            "elapsed_seconds": 1, "summary_text": "Delete the old logs?", "requires_phone_handoff": false,
            "transcript": "", "phone_report": "",
            "next_actions": [
                ["id": "open-on-phone", "label": "Open on Phone", "kind": "deeplink", "target": "ceviz://job/job-question"],
                ["id": "choice-1", "label": "Yes, delete", "kind": "choice", "target": NSNull()],
                ["id": "choice-2", "label": "No, keep them", "kind": "choice", "target": NSNull()],
                ["id": "suggested-next-action", "label": "Archive first", "kind": "agent_command", "target": NSNull()],
            ],
        ]
        let answers = try WatchJobSnapshot.reply(from: JSONSerialization.data(withJSONObject: ["jobs": [question]]))
        _ = try PropertyListSerialization.data(fromPropertyList: answers, format: .binary, options: 0)
        let asked = try JSONDecoder().decode(ActiveJobsResponse.self, from: JSONSerialization.data(withJSONObject: answers))
        precondition(asked.jobs.first?.nextActions?.map(\.id) == ["choice-1", "choice-2"]
                     && asked.jobs.first?.nextActions?.allSatisfy { $0.kind == "choice" && $0.target == nil } == true,
                     "Only the answers reach Watch, as plist-safe rows")
        print("PASS: same-pair identity, bounded Watch snapshots, answers in snapshots, visible malformed/truncated history")
    }
}
