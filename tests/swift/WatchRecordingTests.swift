import Foundation

@main
struct WatchRecordingTests {
    static func main() {
        var capture = WatchRecordingLifecycle()
        let first = capture.prepare()
        precondition(capture.elapsed(at: 100) == 0)
        precondition(capture.begin(first, at: 100))
        precondition(capture.elapsed(at: 99) == 0)
        precondition(capture.elapsed(at: 114.75) == 14.75)
        precondition(capture.elapsed(at: 115) == 15)
        // Native finish resets AVAudioRecorder.currentTime to zero; our owner retains 15.
        precondition(capture.finish(first, at: 115.01))
        precondition(capture.elapsed(at: 116) == 15, "Automatic finish must not reset the countdown")
        precondition(!capture.finish(first, at: 117), "No duplicate auto-completion")
        precondition(!capture.requestStop(at: 117), "A late UI stop cannot send again")

        let manual = capture.prepare()
        precondition(capture.begin(manual, at: 200))
        precondition(capture.requestStop(at: 209))
        precondition(!capture.requestStop(at: 209.5), "Manual stop is idempotent")
        precondition(capture.elapsed(at: 210) == 9, "Six seconds remaining means a nine-second manual capture")
        precondition(capture.finish(manual, at: 211))
        precondition(capture.elapsed(at: 212) == 9, "Finalization cannot advance manual elapsed time")
        precondition(!capture.finish(manual, at: 215), "Late native finish cannot send twice")

        let cancelled = capture.prepare()
        precondition(capture.begin(cancelled, at: 300))
        precondition(capture.requestStop(at: 305))
        capture.cancel()
        precondition(!capture.finish(cancelled, at: 315), "Cancellation during finalization never submits")
        let permission = capture.prepare()
        precondition(!capture.finish(permission, at: 319), "Preparing is not a finished recording")
        capture.cancel()
        precondition(!capture.begin(permission, at: 320), "Permission granted after cancellation cannot start")
        let newer = capture.prepare()
        precondition(!capture.isPreparing(permission), "Old permission callback cannot start the newer capture")
        precondition(!capture.begin(permission, at: 321))
        precondition(capture.begin(newer, at: 400))
        precondition(!capture.finish(cancelled, at: 405), "Stale recorder callback cannot finish newer capture")
        precondition(capture.elapsed(at: 406) == 6)
        precondition(capture.finish(newer, at: 407))
        precondition(capture.elapsed(at: 408) == 7, "Interruption preserves actual elapsed, not the time limit")
        precondition(!capture.finish(newer, at: 409), "Repeated error callback is consumed once")
        let short = capture.prepare()
        precondition(capture.begin(short, at: 500))
        precondition(capture.finish(short, at: 502.5))
        precondition(capture.elapsed(at: 520) == 2.5, "Early native finish is not evidence of a full 15-second recording")
        print("Watch recording countdown, finish-once, cancellation and stale callback tests passed")
    }
}
