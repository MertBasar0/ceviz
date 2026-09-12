import Foundation

/// Watch list replies carry a bounded snapshot, never complete phone reports.
/// Details remain addressable by the unchanged job identity on the backend.
enum WatchJobSnapshot {
    static let maximumReplyBytes = 48_000
    enum SnapshotError: Error { case invalidIdentity, replyTooLarge }

    static func reply(from data: Data) throws -> [String: Any] {
        let source = try JSONDecoder().decode(ActiveJobsResponse.self, from: data)
        func shortened(_ value: String, bytes: Int) -> String {
            var used = 0
            return String(value.prefix { character in
                used += String(character).utf8.count
                return used <= bytes
            })
        }
        var rows: [[String: Any]] = try source.jobs.suffix(50).map { job in
            guard !job.id.isEmpty, job.id.utf8.count <= 256 else { throw SnapshotError.invalidIdentity }
            var row: [String: Any] = [
                "id": job.id,
                "name": shortened(job.name, bytes: 160),
                "status": shortened(job.status, bytes: 32),
                "elapsed_seconds": max(0, job.elapsedSeconds),
                "summary_text": shortened(job.reportMeta?.watchSummary ?? job.summaryText, bytes: 384),
                "requires_phone_handoff": job.reportMeta?.requiresPhoneHandoff ?? job.requiresPhoneHandoff,
                "transcript": "", "phone_report": "",
                "deep_link": "ceviz://job/\(job.id)",
            ]
            if let outcome = job.outcome ?? job.reportMeta?.outcome {
                row["outcome"] = shortened(outcome, bytes: 32)
            }
            return row
        }
        while true {
            let snapshot: [String: Any] = ["jobs": rows, "has_more": rows.count < source.jobs.count]
            if try PropertyListSerialization.data(fromPropertyList: snapshot, format: .binary, options: 0).count <= maximumReplyBytes {
                return snapshot
            }
            guard !rows.isEmpty else { throw SnapshotError.replyTooLarge }
            // Prefer the latest entries without disguising a truncated history
            // as the full list. Watch exposes has_more and keeps refresh visible.
            rows.removeFirst()
        }
    }
}
