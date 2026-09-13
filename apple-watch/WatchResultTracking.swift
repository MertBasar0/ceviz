import Foundation

struct QueuedCommand: Codable, Identifiable {
    let id: String
    let audioData: String
    let timestamp: Date
    var retryCount: Int
    var continueJobId: String? = nil
    // Only new captures opt in. Decoding an older queue must not turn a
    // possibly delivered legacy request into a first durable submission.
    var recoveryProtocol: Int? = nil
    var deliveryJournalID: String? = nil
    var canResumeDelivery: Bool {
        recoveryProtocol == 1 && deliveryJournalID.flatMap { UUID(uuidString: $0) } != nil
    }

    mutating func pinDeliveryJournal(_ journalID: String) -> Bool {
        guard UUID(uuidString: journalID) != nil else { return false }
        if let deliveryJournalID { return deliveryJournalID == journalID }
        deliveryJournalID = journalID
        return true
    }

    func matchesCapture(audioData: String, continueJobId: String?) -> Bool {
        self.audioData == audioData && self.continueJobId == continueJobId
    }
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
    static let attemptDuration: TimeInterval = 30
    enum Operation { case submit, reconcile }
    struct Attempt {
        let commandID: String
        let generation: Int
        let operation: Operation
        let deadline: Date
        let presentsResult: Bool
    }
    private var generation = 0
    private var commandID: String?
    private(set) var attempt: Attempt?
    // Only this process can know a capture has never crossed WCSession. A
    // restored queue always reconciles, including retryCount == 0 after a crash.
    private var unsubmitted: Set<String> = []
    private var deferred: Set<String> = []
    private(set) var allowsSubmission = true
    private(set) var presentsRecovery = false
    private var resetCutoff: TimeInterval?

    var isBusy: Bool { attempt != nil }
    var isChecking: Bool { attempt?.operation == .reconcile }
    var hasUnconfirmedFocus: Bool { commandID != nil }
    var canStartCapture: Bool { !isBusy || isChecking }
    var isPresentingAttempt: Bool { attempt?.presentsResult == true }
    var blocksResultUpdates: Bool { isPresentingAttempt || hasUnconfirmedFocus }

    mutating func registerNew(_ commandID: String, precedingCommandIDs: [String] = []) {
        // Queueing already presents this capture, even before WC is reachable.
        self.commandID = commandID
        deferred.formUnion(precedingCommandIDs.filter { $0 != commandID && !unsubmitted.contains($0) })
        unsubmitted.insert(commandID)
        allowsSubmission = true
        presentsRecovery = false
    }

    mutating func beginRecoveryPass(allowSubmission: Bool = true, presentChecks: Bool = false) {
        guard !isBusy else { return }
        deferred.removeAll()
        allowsSubmission = allowSubmission
        presentsRecovery = presentChecks
    }

    func isFocused(_ commandID: String) -> Bool { self.commandID == commandID }

    func nextCommand(in commands: [QueuedCommand]) -> QueuedCommand? {
        guard !isBusy else { return nil }
        // Ambiguous A stays saved, but must not hold a genuinely new B hostage.
        // Every other saved identity is checked at most once in this pass.
        if allowsSubmission, let fresh = commands.first(where: { unsubmitted.contains($0.id) && !deferred.contains($0.id) }) {
            return fresh
        }
        return commands.first { !deferred.contains($0.id) }
    }

    func nextOperation(for commandID: String) -> Operation {
        allowsSubmission && unsubmitted.contains(commandID) ? .submit : .reconcile
    }

    mutating func begin(_ commandID: String, operation: Operation = .submit,
                        presentsResult: Bool = true, now: Date = Date()) -> Int {
        generation += 1
        if presentsResult { self.commandID = commandID }
        attempt = Attempt(commandID: commandID, generation: generation, operation: operation,
                          deadline: now.addingTimeInterval(Self.attemptDuration), presentsResult: presentsResult)
        return generation
    }

    func isCurrentAttempt(_ commandID: String, generation: Int) -> Bool {
        attempt?.commandID == commandID && attempt?.generation == generation
    }

    mutating func markDispatched(_ commandID: String, generation: Int) -> Bool {
        guard isCurrentAttempt(commandID, generation: generation), attempt?.operation == .submit else { return false }
        unsubmitted.remove(commandID)
        return true
    }

    mutating func confirmNotSubmitted(_ commandID: String, generation: Int) -> Bool {
        guard isCurrentAttempt(commandID, generation: generation), attempt?.operation == .reconcile else { return false }
        if allowsSubmission { unsubmitted.insert(commandID) }
        else { deferred.insert(commandID) }
        return finishAttempt(commandID, generation: generation)
    }

    @discardableResult
    mutating func deferAttempt(_ commandID: String, generation: Int) -> Bool {
        guard finishAttempt(commandID, generation: generation) else { return false }
        deferred.insert(commandID)
        return true
    }

    mutating func interruptCheck() -> Bool {
        guard let attempt, attempt.operation == .reconcile else { return false }
        return deferAttempt(attempt.commandID, generation: attempt.generation)
    }

    @discardableResult
    mutating func finishAttempt(_ commandID: String, generation: Int) -> Bool {
        guard isCurrentAttempt(commandID, generation: generation) else { return false }
        attempt = nil
        return true
    }

    func expiredAttempt(at now: Date = Date()) -> Attempt? {
        guard let attempt, now >= attempt.deadline else { return nil }
        return attempt
    }

    mutating func accept(_ commandID: String) -> Bool {
        unsubmitted.remove(commandID)
        deferred.remove(commandID)
        if attempt?.commandID == commandID {
            generation += 1
            attempt = nil
        }
        guard self.commandID == commandID else { return false }
        self.commandID = nil
        return true
    }

    mutating func invalidate(removedCommandIDs: Set<String>) -> Bool {
        unsubmitted.subtract(removedCommandIDs)
        deferred.subtract(removedCommandIDs)
        let removesAttempt = attempt.map { removedCommandIDs.contains($0.commandID) } ?? false
        let removesFocus = commandID.map { removedCommandIDs.contains($0) } ?? false
        guard removesAttempt || removesFocus else { return false }
        generation += 1
        if removesFocus { commandID = nil }
        if removesAttempt { attempt = nil }
        return true
    }

    mutating func reset() {
        generation += 1
        commandID = nil
        attempt = nil
        unsubmitted.removeAll()
        deferred.removeAll()
        allowsSubmission = true
        presentsRecovery = false
    }

    mutating func receiveReset(at cutoff: TimeInterval) -> Bool {
        guard cutoff.isFinite else { return false }
        if let resetCutoff, cutoff <= resetCutoff { return false }
        resetCutoff = cutoff
        return true
    }
}

/// A failed or stale refresh never replaces the last known list with empty data.
struct WatchJobsTracking {
    private(set) var jobs: [ActiveJob] = []
    private(set) var errorKey: String?
    private(set) var hasLoaded = false
    private(set) var hasMore = false
    private(set) var deadline: Date?
    private var generation = 0
    var isLoading: Bool { deadline != nil }

    mutating func begin(now: Date = Date()) -> Int {
        generation += 1
        deadline = now.addingTimeInterval(WatchDeliveryTracking.attemptDuration)
        errorKey = nil
        return generation
    }

    mutating func receive(_ reply: [String: Any], generation: Int) {
        guard self.generation == generation, isLoading else { return }
        guard let raw = reply["jobs"] as? [[String: Any]],
              let data = try? JSONSerialization.data(withJSONObject: raw),
              let decoded = try? JSONDecoder().decode([ActiveJob].self, from: data),
              Set(decoded.map(\.id)).count == decoded.count else {
            fail("Jobs could not be read. Refresh to try again.", generation: generation)
            return
        }
        jobs = Array(decoded.reversed())
        hasMore = reply["has_more"] as? Bool ?? false
        hasLoaded = true
        deadline = nil
        errorKey = nil
    }

    mutating func fail(_ key: String, generation: Int) {
        guard self.generation == generation, isLoading else { return }
        deadline = nil
        errorKey = key
    }

    mutating func expire(at now: Date = Date()) {
        guard let deadline, now >= deadline else { return }
        fail("Jobs did not refresh. Check the iPhone connection and try again.", generation: generation)
    }

    mutating func reset() {
        let next = generation + 1
        self = Self()
        generation = next
    }
}

/// One focused result on the Watch; the backend remains the owner of the full job list.
struct WatchResultTracking: Equatable {
    static func receiptCanAdvance(jobID: String, status: String, lastTerminalJobID: String?) -> Bool {
        status == "completed" || status == "failed" || jobID != lastTerminalJobID
    }

    static func terminalReceiptPresentation(jobID: String, displayedJobID: String?,
                                            state: CVZJobState?, text: String) -> (state: CVZJobState, text: String) {
        if displayedJobID == jobID, let state, state.isReportedResult || state == .failed {
            return (state, text)
        }
        return (.resultReady, NSLocalizedString("This job already has a result. Check Jobs.", comment: ""))
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
