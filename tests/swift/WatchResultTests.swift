import Foundation

@main
struct WatchResultTests {
    static func main() {
        testCaptureRoutes()
        testContinuationSelection()
        var tracking = WatchResultTracking()
        precondition(tracking.jobID == nil)

        var delivery = WatchDeliveryTracking()
        let first = delivery.begin("command-A")
        let retry = delivery.begin("command-A")
        precondition(!delivery.isCurrentAttempt("command-A", generation: first))
        precondition(delivery.accept("command-A"), "A late receipt still confirms the same retried command")
        tracking.start("job-A")
        precondition(!delivery.isCurrentAttempt("command-A", generation: retry), "Later retry errors cannot lose a confirmed receipt")
        let newer = delivery.begin("command-B")
        precondition(!delivery.accept("command-A"), "An older command cannot replace a newer submission")
        precondition(delivery.isCurrentAttempt("command-B", generation: newer))
        precondition(delivery.accept("command-B"))
        precondition(!delivery.accept("command-B"), "Duplicate receipts apply only once")
        let beforeReset = delivery.begin("command-A")
        precondition(delivery.invalidate(removedCommandIDs: ["command-A"]), "Reset invalidates active A even while newer B survives in the queue")
        precondition(!delivery.isCurrentAttempt("command-A", generation: beforeReset), "Late capability/file/error callbacks for removed A must do nothing")
        let afterReset = delivery.begin("command-B")
        precondition(!delivery.invalidate(removedCommandIDs: ["command-A"]), "A late older reset cannot invalidate newer B")
        precondition(delivery.isCurrentAttempt("command-B", generation: afterReset))
        precondition(!delivery.accept("command-A"))
        precondition(delivery.accept("command-B"), "The surviving command still accepts its own receipt")
        precondition(!WatchResultTracking.receiptCanAdvance(jobID: "job-A", status: "processing", lastTerminalJobID: "job-A"), "Terminal notification dominates an earlier in-flight receipt")
        precondition(WatchResultTracking.receiptCanAdvance(jobID: "job-B", status: "processing", lastTerminalJobID: "job-A"))
        precondition(WatchResultTracking.receiptCanAdvance(jobID: "job-A", status: "completed", lastTerminalJobID: "job-A"))
        tracking.reset()
        tracking.start("job-1")
        tracking.pause()
        precondition(tracking.phase == .paused("job-1"), "A polling deadline must not forget accepted work")
        tracking.start("job-1")
        precondition(tracking.phase == .polling("job-1"), "Wake resumes the same accepted job")
        tracking.start("job-2")
        precondition(!tracking.finish("job-1"), "A late older result cannot clear newer work")
        precondition(tracking.jobID == "job-2")
        precondition(tracking.finish("job-2"))
        precondition(!tracking.finish("job-2"), "A duplicate terminal result cannot finish twice")
        tracking.start("job-3")
        tracking.pause()
        precondition(tracking.finish("job-3"), "A terminal notification still resolves a paused result")
        tracking.start("job-4")
        tracking.reset()
        precondition(tracking.jobID == nil)

        let legacy = Data("""
        {"id":"legacy","name":"Legacy run","status":"completed","elapsed_seconds":2,
         "summary_text":"Response available","requires_phone_handoff":false,"transcript":"check",
         "phone_report":""}
        """.utf8)
        let decoded = try! JSONDecoder().decode(ActiveJob.self, from: legacy)
        precondition(decoded.presentationState == .resultReady, "Legacy completion is not verified success")
        print("Watch capture routing, focus lifecycle and legacy model decoding passed")
    }

    private static func testCaptureRoutes() {
        let captureStates: [(Bool, Bool, WatchCaptureRoute)] = [
            (false, false, .ready),
            (true, false, .preserveCapture),
            (false, true, .preserveCapture),
            (true, true, .preserveCapture)
        ]
        for link in ["ceviz-watch://capture", "ceviz-watch://capture?source=complication#microphone"] {
            let url = URL(string: link)!
            for (recording, preparing, expected) in captureStates {
                precondition(WatchCaptureRoute(url: url, isRecording: recording, preparingCapture: preparing) == expected,
                             "Capture navigation must be ready only when idle; an existing capture stays untouched")
            }
        }
        for link in ["https://capture", "ceviz://capture", "ceviz-watch://jobs", "ceviz-watch:/capture", "capture"] {
            let url = URL(string: link)!
            for (recording, preparing, _) in captureStates {
                precondition(WatchCaptureRoute(url: url, isRecording: recording, preparingCapture: preparing) == nil,
                             "Unrelated or malformed capture links must not navigate: \(link)")
            }
        }
    }

    private static func testContinuationSelection() {
        let observed = Date(timeIntervalSince1970: 10_000)
        var selection = WatchContinuationSelection()
        precondition(selection.parent(for: "long-job", at: observed) == nil)
        selection.observe("long-job", at: observed)
        precondition(selection.parent(for: "long-job", at: observed) == "long-job",
                     "A long-running job can be continued when its result first becomes visible")
        precondition(selection.parent(for: "another-job", at: observed) == nil,
                     "A caption cannot advertise another displayed job's context")
        let frozenParent = selection.parent(for: "long-job", at: observed.addingTimeInterval(179))
        let captured = QueuedCommand(id: "command", audioData: "YXVkaW8=", timestamp: observed,
                                     retryCount: 0, continueJobId: frozenParent)
        let restored = try! JSONDecoder().decode(QueuedCommand.self, from: JSONEncoder().encode(captured))
        precondition(restored.continueJobId == "long-job", "Queue restoration must retain the captured parent")
        let legacyQueue = Data(#"{"id":"old","audioData":"YXVkaW8=","timestamp":0,"retryCount":1}"#.utf8)
        let old = try! JSONDecoder().decode(QueuedCommand.self, from: legacyQueue)
        precondition(old.continueJobId == nil, "Old queued commands remain standalone, never guess a new parent")
        selection.observe("long-job", at: observed.addingTimeInterval(179))
        precondition(selection.parent(for: "long-job", at: observed.addingTimeInterval(180)) == nil,
                     "Repeated push/poll replies must not extend the selection window")
        selection.observe("newer-job", at: observed.addingTimeInterval(181))
        precondition(frozenParent == "long-job", "A newer result cannot retarget an already captured request")
        precondition(selection.parent(for: "newer-job", at: observed.addingTimeInterval(181)) == "newer-job")
        selection.reset()
        precondition(selection.parent(for: "newer-job", at: observed.addingTimeInterval(182)) == nil)
    }
}
