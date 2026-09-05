import Foundation

/// Owns capture identity and elapsed time independently of AVAudioRecorder.currentTime,
/// which becomes zero as soon as the native recorder stops.
struct WatchRecordingLifecycle {
    static let maximumDuration: TimeInterval = 15
    private enum Phase {
        case idle
        case preparing(UUID)
        case recording(UUID, startedAt: TimeInterval)
        case stopping(UUID, elapsed: TimeInterval)
    }
    private var phase: Phase = .idle
    private var finishedElapsed: TimeInterval = 0

    var id: UUID? {
        switch phase {
        case .idle: return nil
        case .preparing(let id), .recording(let id, _), .stopping(let id, _): return id
        }
    }

    mutating func prepare() -> UUID {
        let id = UUID()
        phase = .preparing(id)
        finishedElapsed = 0
        return id
    }

    func isPreparing(_ id: UUID) -> Bool {
        if case .preparing(let current) = phase { return current == id }
        return false
    }

    @discardableResult
    mutating func begin(_ id: UUID, at time: TimeInterval) -> Bool {
        guard isPreparing(id) else { return false }
        phase = .recording(id, startedAt: time)
        return true
    }

    func elapsed(at time: TimeInterval) -> TimeInterval {
        switch phase {
        case .recording(_, let startedAt): return min(Self.maximumDuration, max(0, time - startedAt))
        case .stopping(_, let elapsed): return elapsed
        case .preparing: return 0
        case .idle: return finishedElapsed
        }
    }

    /// Freeze manual-stop time before AVAudioRecorder resets its clock.
    mutating func requestStop(at time: TimeInterval) -> Bool {
        guard case .recording(let id, _) = phase else { return false }
        phase = .stopping(id, elapsed: elapsed(at: time))
        return true
    }

    /// Freeze observed elapsed time. A successful native finish is not proof of duration.
    mutating func finish(_ id: UUID, at time: TimeInterval) -> Bool {
        guard self.id == id else { return false }
        switch phase {
        case .recording, .stopping: finishedElapsed = elapsed(at: time)
        default: return false
        }
        phase = .idle
        return true
    }

    mutating func cancel() {
        phase = .idle
        finishedElapsed = 0
    }
}
