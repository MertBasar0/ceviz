import Foundation

struct QueuedCommand: Codable, Identifiable {
    let id: String
    let audioData: String
    let timestamp: Date
    var retryCount: Int
    var continueJobId: String? = nil
}

/// The selection window starts when a result is first shown, not when its job
/// started. Captures freeze this parent so delayed delivery cannot retarget it.
struct WatchContinuationSelection {
    static let window: TimeInterval = 180
    private var jobID: String?
    private var observedAt: Date?

    mutating func observe(_ jobID: String, at date: Date = Date()) {
        guard self.jobID != jobID else { return }
        self.jobID = jobID
        observedAt = date
    }

    func parent(for displayedJobID: String?, at date: Date = Date()) -> String? {
        guard let jobID, jobID == displayedJobID, let observedAt,
              (0..<Self.window).contains(date.timeIntervalSince(observedAt)) else { return nil }
        return jobID
    }

    mutating func reset() { self = Self() }
}

/// A capture link only navigates; recording remains owned by the mic action.
enum WatchCaptureRoute: Equatable {
    case ready
    case preserveCapture

    init?(url: URL, isRecording: Bool, preparingCapture: Bool) {
        guard url.scheme == "ceviz-watch", url.host == "capture" else { return nil }
        self = isRecording || preparingCapture ? .preserveCapture : .ready
    }
}

/// Retries share a command identity. A valid older receipt still owns that
/// command, while transport failures only belong to the newest attempt.
struct WatchDeliveryTracking {
    private var generation = 0
    private var commandID: String?

    mutating func begin(_ commandID: String) -> Int {
        generation += 1
        self.commandID = commandID
        return generation
    }

    func isCurrentAttempt(_ commandID: String, generation: Int) -> Bool {
        self.commandID == commandID && self.generation == generation
    }

    mutating func accept(_ commandID: String) -> Bool {
        guard self.commandID == commandID else { return false }
        reset()
        return true
    }

    mutating func invalidate(removedCommandIDs: Set<String>) -> Bool {
        guard let commandID, removedCommandIDs.contains(commandID) else { return false }
        reset()
        return true
    }

    mutating func reset() {
        generation += 1
        commandID = nil
    }
}

/// One focused result on the Watch; the backend remains the owner of the full job list.
struct WatchResultTracking: Equatable {
    static func receiptCanAdvance(jobID: String, status: String, lastTerminalJobID: String?) -> Bool {
        status == "completed" || status == "failed" || jobID != lastTerminalJobID
    }

    enum Phase: Equatable {
        case idle
        case polling(String)
        case paused(String)
    }

    private(set) var phase: Phase = .idle

    var jobID: String? {
        switch phase {
        case .idle: return nil
        case .polling(let id), .paused(let id): return id
        }
    }

    mutating func start(_ jobID: String) {
        phase = .polling(jobID)
    }

    mutating func pause() {
        if let jobID { phase = .paused(jobID) }
    }

    @discardableResult
    mutating func finish(_ jobID: String) -> Bool {
        guard self.jobID == jobID else { return false }
        phase = .idle
        return true
    }

    mutating func reset() {
        phase = .idle
    }
}
