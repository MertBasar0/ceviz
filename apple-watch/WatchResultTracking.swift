import Foundation

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
