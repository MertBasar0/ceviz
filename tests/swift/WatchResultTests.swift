import Foundation

@main
struct WatchResultTests {
    static func main() {
        testCaptureRoutes()
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
}
