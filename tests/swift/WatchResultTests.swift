import Foundation

@main
struct WatchResultTests {
    static func main() {
        testCaptureRoutes()
        testContinuationSelection()
        testDeliveryRecovery()
        testQueuePasses()
        testQueuedFocusBeforeTransport()
        testJobsRecovery()
        testLateTerminalReceiptPresentation()
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

    private static func testDeliveryRecovery() {
        let start = Date(timeIntervalSince1970: 10_000)
        var delivery = WatchDeliveryTracking()
        delivery.registerNew("A")
        delivery.registerNew("B", precedingCommandIDs: ["A"])
        precondition(delivery.nextOperation(for: "A") == .submit)
        let prepare = delivery.begin("A", now: start)
        precondition(delivery.isBusy && !delivery.isChecking)
        precondition(delivery.expiredAttempt(at: start.addingTimeInterval(29.99)) == nil)
        let afterSleep = delivery.expiredAttempt(at: start.addingTimeInterval(14 * 60))!
        precondition(afterSleep.commandID == "A" && afterSleep.generation == prepare,
                     "Foreground recovery observes wall-clock expiry even when the dispatch timer slept")
        delivery.finishAttempt("A", generation: prepare)
        precondition(!delivery.isBusy && delivery.nextOperation(for: "A") == .submit,
                     "A capability check failure before audio delivery still permits its first submission")
        precondition(!delivery.markDispatched("A", generation: prepare), "A stale preflight callback cannot send audio")

        let send = delivery.begin("A", now: start)
        precondition(delivery.markDispatched("A", generation: send))
        delivery.finishAttempt("A", generation: send)
        precondition(delivery.nextOperation(for: "A") == .reconcile,
                     "Transport timeout after send cannot authorize audio retry")
        precondition(delivery.nextOperation(for: "B") == .submit,
                     "The next FIFO recording retains its own never-submitted fact")

        let restoredCommand = try! JSONDecoder().decode(QueuedCommand.self, from: JSONEncoder().encode(
            QueuedCommand(id: "A", audioData: "YXVkaW8=", timestamp: start, retryCount: 0)))
        var restored = WatchDeliveryTracking()
        precondition(restored.nextOperation(for: restoredCommand.id) == .reconcile,
                     "Process restart with retryCount zero is not proof that a saved command was never sent")
        let check = restored.begin("A", operation: .reconcile, now: start)
        precondition(restored.isChecking)
        restored.finishAttempt("A", generation: check) // unavailable / in-flight / unknown
        precondition(!restored.isBusy && restored.nextOperation(for: "A") == .reconcile)
        precondition(!restored.confirmNotSubmitted("A", generation: check),
                     "A late status callback from a timed-out check cannot authorize a resend")
        let currentCheck = restored.begin("A", operation: .reconcile, now: start)
        precondition(restored.confirmNotSubmitted("A", generation: currentCheck))
        precondition(!restored.isBusy && restored.nextOperation(for: "A") == .submit,
                     "Only a current authoritative not_submitted response allows the original identity to be sent")
        let retry = restored.begin("A", now: start)
        precondition(restored.markDispatched("A", generation: retry))
        restored.finishAttempt("A", generation: retry)
        precondition(restored.accept("A"), "A valid receipt after UI timeout still acknowledges saved work")
        precondition(!restored.accept("A") && !restored.finishAttempt("A", generation: retry))
        precondition(!restored.isBusy)
        precondition(delivery.invalidate(removedCommandIDs: ["A"]))
        precondition(delivery.nextOperation(for: "B") == .submit,
                     "Expiry/reset of an older command cannot invalidate a newer recording")
        delivery.reset()
        precondition(delivery.nextOperation(for: "B") == .reconcile,
                     "An actual connection scope reset cannot carry submission authority into another pairing")
        delivery.registerNew("old")
        delivery.registerNew("new")
        let focused = delivery.begin("new", now: start)
        precondition(!delivery.accept("old"), "An older receipt cannot replace the focused request")
        precondition(delivery.nextOperation(for: "old") == .reconcile,
                     "An older receipt still retires its never-submitted marker")
        precondition(delivery.isCurrentAttempt("new", generation: focused))
    }

    private static func testLateTerminalReceiptPresentation() {
        // Original order: send clears presentation, a terminal notification is
        // known, then an older processing receipt finally retires the recording.
        let sending = WatchResultTracking.terminalReceiptPresentation(
            jobID: "done", displayedJobID: nil, state: nil, text: "Sending request…")
        precondition(sending.state == .resultReady && sending.text != "Sending request…",
                     "Suppressing a stale processing receipt must not leave the Sending text on screen")
        for state in [CVZJobState.completed, .blocked, .needsInput, .failed, .resultReady] {
            let visible = WatchResultTracking.terminalReceiptPresentation(
                jobID: "done", displayedJobID: "done", state: state, text: "Actual terminal summary")
            precondition(visible.state == state && visible.text == "Actual terminal summary")
        }
        let uncertain = WatchResultTracking.terminalReceiptPresentation(
            jobID: "done", displayedJobID: "done", state: .unknown, text: "Delivery unconfirmed")
        precondition(uncertain.state == .resultReady && uncertain.text != "Delivery unconfirmed")
        let other = WatchResultTracking.terminalReceiptPresentation(
            jobID: "done", displayedJobID: "different", state: .completed, text: "Other job succeeded")
        precondition(other.state == .resultReady && other.text != "Other job succeeded",
                     "A terminal fact for another job cannot invent this job's success")
    }

    private static func testQueuePasses() {
        let date = Date(timeIntervalSince1970: 30_000)
        func command(_ id: String) -> QueuedCommand {
            QueuedCommand(id: id, audioData: "YXVkaW8=", timestamp: date, retryCount: 0, recoveryProtocol: 1)
        }
        let journalA = "DD8F2A1C-2345-4567-ABCD-0123456789AB"
        let journalB = "EE8F2A1C-2345-4567-ABCD-0123456789AB"
        var pinned = command("pinned")
        precondition(!pinned.canResumeDelivery, "A restored recording without a pinned phone incarnation cannot become a retry")
        precondition(!pinned.pinDeliveryJournal("invalid") && pinned.deliveryJournalID == nil)
        precondition(pinned.pinDeliveryJournal(journalA) && pinned.canResumeDelivery)
        let restoredPin = try! JSONDecoder().decode(QueuedCommand.self, from: JSONEncoder().encode(pinned))
        precondition(restoredPin.deliveryJournalID == journalA && restoredPin.canResumeDelivery)
        precondition(pinned.pinDeliveryJournal(journalA))
        precondition(!pinned.pinDeliveryJournal(journalB) && pinned.deliveryJournalID == journalA,
                     "Phone metadata loss cannot rebind an old recording to the new phone journal")
        var queue = [command("A")]
        var delivery = WatchDeliveryTracking()
        delivery.registerNew("A")
        let first = delivery.begin("A", now: date)
        precondition(!delivery.canStartCapture && !delivery.interruptCheck(), "A capture cannot cancel an audio submission")
        precondition(delivery.markDispatched("A", generation: first))
        precondition(delivery.deferAttempt("A", generation: first))
        precondition(delivery.nextCommand(in: queue) == nil, "Unknown delivery ends this pass, not another automatic replay")
        queue.append(command("B"))
        delivery.registerNew("B")
        precondition(delivery.nextCommand(in: queue)?.id == "B", "A new capture must not wait behind uncertain A")
        precondition(delivery.nextOperation(for: "B") == .submit && delivery.nextOperation(for: "A") == .reconcile)
        let next = delivery.begin("B", now: date)
        precondition(delivery.markDispatched("B", generation: next))
        precondition(delivery.accept("B"))
        queue.removeAll { $0.id == "B" }
        precondition(!delivery.hasUnconfirmedFocus && queue.map(\.id) == ["A"],
                     "Accepted B can track its result even while deferred A remains saved")
        precondition(delivery.nextCommand(in: queue) == nil)
        precondition(!delivery.accept("A"), "A late older ACK cannot steal B's result focus")

        // An older record can also be unknown because it was restored, not
        // because this process already observed a failed attempt.
        var recovered = WatchDeliveryTracking()
        recovered.registerNew("B", precedingCommandIDs: ["A"])
        _ = recovered.begin("B", now: date)
        precondition(recovered.accept("B"))
        precondition(recovered.nextCommand(in: [command("A")]) == nil)
        recovered.beginRecoveryPass()
        let background = recovered.begin("A", operation: .reconcile, presentsResult: false, now: date)
        precondition(recovered.isBusy && !recovered.isPresentingAttempt && !recovered.blocksResultUpdates,
                     "Automatic checking of old A cannot hide accepted B or stop its result polling")
        precondition(!recovered.accept("A"), "A background receipt only retires its own saved identity")
        precondition(!recovered.isBusy && !recovered.isCurrentAttempt("A", generation: background))
        let focused = recovered.begin("newer", now: date)
        recovered.finishAttempt("newer", generation: focused)
        _ = recovered.begin("older", operation: .reconcile, presentsResult: false, now: date)
        precondition(!recovered.accept("older") && !recovered.isBusy && recovered.isFocused("newer"),
                     "A background ACK cannot clear a different unconfirmed focus")
        precondition(recovered.blocksResultUpdates)

        // Restart loses transient first-send knowledge but not protocol/capture
        // metadata. Check each retained identity once rather than stalling at A.
        let saved = try! JSONEncoder().encode([command("C"), command("D")])
        queue = try! JSONDecoder().decode([QueuedCommand].self, from: saved)
        delivery = WatchDeliveryTracking()
        delivery.beginRecoveryPass()
        precondition(queue.allSatisfy { $0.recoveryProtocol == 1 && $0.audioData == "YXVkaW8=" && $0.timestamp == date })
        for id in ["C", "D"] {
            precondition(delivery.nextCommand(in: queue)?.id == id && delivery.nextOperation(for: id) == .reconcile)
            let check = delivery.begin(id, operation: .reconcile, now: date)
            precondition(delivery.deferAttempt(id, generation: check))
        }
        precondition(delivery.nextCommand(in: queue) == nil && queue.count == 2)

        delivery.beginRecoveryPass(allowSubmission: false)
        let readOnly = delivery.begin("C", operation: .reconcile, now: date)
        precondition(delivery.confirmNotSubmitted("C", generation: readOnly))
        precondition(delivery.nextOperation(for: "C") == .reconcile && delivery.nextCommand(in: queue)?.id == "D")
        delivery.beginRecoveryPass()
        precondition(delivery.nextOperation(for: "C") == .reconcile,
                     "A same-pair status-only refresh must not cache replay permission for a later event")
        let interrupted = delivery.begin("C", operation: .reconcile, now: date)
        precondition(delivery.canStartCapture && delivery.interruptCheck())
        precondition(!delivery.isCurrentAttempt("C", generation: interrupted))
        precondition(!delivery.confirmNotSubmitted("C", generation: interrupted),
                     "A late status reply after starting a new capture cannot authorize replay")
        queue.append(command("E"))
        delivery.registerNew("E")
        precondition(delivery.nextCommand(in: queue)?.id == "E")

        precondition(delivery.receiveReset(at: 10))
        delivery.invalidate(removedCommandIDs: ["C", "D"])
        let fresh = delivery.begin("E", now: date)
        precondition(!delivery.receiveReset(at: 10) && !delivery.receiveReset(at: 9))
        precondition(!delivery.receiveReset(at: .nan))
        precondition(delivery.isCurrentAttempt("E", generation: fresh), "Duplicate/older resets cannot interrupt the new capture's delivery")
        delivery.reset()
        precondition(!delivery.receiveReset(at: 10), "Clearing delivery state must retain the monotonic reset cutoff")
        precondition(delivery.receiveReset(at: 11))
    }

    private static func testQueuedFocusBeforeTransport() {
        let date = Date(timeIntervalSince1970: 40_000)
        let queue = ["A", "B"].map {
            QueuedCommand(id: $0, audioData: "YXVkaW8=", timestamp: date, retryCount: 0, recoveryProtocol: 1)
        }
        var delivery = WatchDeliveryTracking()
        delivery.registerNew("A")
        let first = delivery.begin("A", now: date)
        precondition(delivery.markDispatched("A", generation: first))
        precondition(delivery.deferAttempt("A", generation: first))
        precondition(delivery.isFocused("A"))

        // queueCommand presents B immediately, but an unreachable iPhone means
        // processQueue cannot begin B before A's delayed receipt arrives.
        delivery.registerNew("B", precedingCommandIDs: queue.map(\.id))
        precondition(!delivery.isBusy)
        precondition(!delivery.accept("A"), "An old receipt cannot replace a newer queued capture before its first transport attempt")
        precondition(delivery.isFocused("B") && delivery.blocksResultUpdates)
        precondition(delivery.nextCommand(in: [queue[1]])?.id == "B")
        precondition(delivery.nextOperation(for: "B") == .submit && delivery.nextOperation(for: "A") == .reconcile,
                     "Changing presentation focus cannot grant a replay or consume B's first-send authority")
        let second = delivery.begin("B", now: date)
        precondition(delivery.markDispatched("B", generation: second))
        precondition(delivery.accept("B") && !delivery.hasUnconfirmedFocus)
    }

    private static func testJobsRecovery() {
        let start = Date(timeIntervalSince1970: 20_000)
        func job(_ id: String) -> [String: Any] {
            ["id": id, "name": "Job \(id)", "status": "completed", "elapsed_seconds": 2,
             "summary_text": "A result", "requires_phone_handoff": false,
             "transcript": "", "phone_report": ""]
        }
        var jobs = WatchJobsTracking()
        let first = jobs.begin(now: start)
        precondition(jobs.isLoading && !jobs.hasLoaded)
        jobs.receive(["jobs": [job("old"), job("new")], "has_more": true], generation: first)
        precondition(jobs.jobs.map(\.id) == ["new", "old"] && jobs.hasMore && jobs.hasLoaded)
        precondition(!jobs.isLoading && jobs.errorKey == nil)
        let refresh = jobs.begin(now: start)
        jobs.expire(at: start.addingTimeInterval(31))
        precondition(!jobs.isLoading && jobs.errorKey != nil && jobs.jobs.count == 2,
                     "A refresh timeout keeps stale jobs visible instead of a misleading empty list")
        jobs.receive(["jobs": []], generation: refresh)
        precondition(jobs.jobs.count == 2, "An expired response cannot replace the last known list")
        let next = jobs.begin(now: start)
        jobs.fail("late old transport failure", generation: refresh)
        precondition(jobs.isLoading && jobs.errorKey == nil)
        var malformed = job("bad")
        malformed.removeValue(forKey: "summary_text")
        jobs.receive(["jobs": [job("valid"), malformed]], generation: next)
        precondition(jobs.errorKey != nil && jobs.jobs.map(\.id) == ["new", "old"],
                     "One malformed row fails the whole batch visibly, without silently discarding jobs")
        let duplicate = jobs.begin(now: start)
        jobs.receive(["jobs": [job("same"), job("same")]], generation: duplicate)
        precondition(jobs.errorKey != nil && jobs.jobs.count == 2, "Duplicate SwiftUI identities are rejected as a batch")
        let backendError = jobs.begin(now: start)
        jobs.receive(["error": "backend unavailable"], generation: backendError)
        precondition(jobs.errorKey != nil && jobs.jobs.count == 2)
        let beforeReset = jobs.begin(now: start)
        jobs.reset()
        jobs.receive(["jobs": [job("old-pairing")]], generation: beforeReset)
        precondition(jobs.jobs.isEmpty && !jobs.hasLoaded && !jobs.isLoading,
                     "A late response cannot leak jobs from the prior pairing after reset")
        let empty = jobs.begin(now: start)
        jobs.receive(["jobs": []], generation: empty)
        precondition(jobs.jobs.isEmpty && jobs.hasLoaded && jobs.errorKey == nil && !jobs.hasMore,
                     "Only a successful empty response presents no jobs yet")
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
        precondition(restored.matchesCapture(audioData: "YXVkaW8=", continueJobId: "long-job"))
        precondition(!restored.matchesCapture(audioData: "YXVkaW8=", continueJobId: "other-job"),
                     "Identical audio targeting another continuation is a distinct capture intent")
        precondition(!restored.matchesCapture(audioData: "YXVkaW8=", continueJobId: nil))
        precondition(!restored.matchesCapture(audioData: "bmV3", continueJobId: "long-job"))
        let legacyQueue = Data(#"{"id":"old","audioData":"YXVkaW8=","timestamp":0,"retryCount":1}"#.utf8)
        let old = try! JSONDecoder().decode(QueuedCommand.self, from: legacyQueue)
        precondition(old.continueJobId == nil && old.recoveryProtocol == nil,
                     "Old queued commands remain legacy and standalone, never guess a new parent or protocol")
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
