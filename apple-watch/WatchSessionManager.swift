import Foundation
import WatchConnectivity
import Combine
import WatchKit
import UserNotifications

class WatchSessionManager: NSObject, ObservableObject, WCSessionDelegate, WKExtendedRuntimeSessionDelegate {
    static let shared = WatchSessionManager()

    @Published var isReachable = false
    @Published var responseText = ""
    @Published var handoffUrl: String? = nil
    @Published var handoffJobId: String? = nil
    @Published private var jobsTracking = WatchJobsTracking()
    var activeJobs: [ActiveJob] { jobsTracking.jobs }
    var jobsLoading: Bool { jobsTracking.isLoading }
    var jobsErrorKey: String? { jobsTracking.errorKey }
    var jobsHaveLoaded: Bool { jobsTracking.hasLoaded }
    var jobsHaveMore: Bool { jobsTracking.hasMore }
    @Published var pendingCommands: [QueuedCommand] = []
    @Published var transportStatus: String = "Disconnected"
    var isSending: Bool { deliveryTracking.isBusy }
    var isCheckingDelivery: Bool { deliveryTracking.isChecking }
    var isPresentingDelivery: Bool { deliveryTracking.isPresentingAttempt }
    var canStartCapture: Bool { deliveryTracking.canStartCapture }
    @Published private(set) var resultState: CVZJobState?
    @Published private(set) var resultPresentationRequest = UUID()
    @Published private var resultTracking = WatchResultTracking()
    var isCapturing = false
    @Published private var continuation = WatchContinuationSelection()
    private var captureParentJobID: String?
    @Published var handoffState: HandoffState = .idle
    @Published var handoffPreview: HandoffPreview? = nil

    private var extendedSession: WKExtendedRuntimeSession?
    private var resultPollTimer: Timer?
    private var resultPollDeadline: Date?
    private var pollingJobId: String? { resultTracking.jobID }
    private var pollErrorCount = 0
    @Published private var deliveryTracking = WatchDeliveryTracking()
    private let commandFiles = WatchCommandFiles()
    private static let pendingJobDefaultsKey = "cvz.pendingJobId"
    private static let pendingJobAtDefaultsKey = "cvz.pendingJobAt"
    private static let lastTerminalJobDefaultsKey = "cvz.lastTerminalJobId"
    private static let pendingCommandsDefaultsKey = "cvz.pendingCommands.v1"
    /// Sesli komutlar uzun süre sonra sürpriz biçimde çalıştırılmamalı.
    private static let pendingCommandMaxAge = WatchCommandTransport.maximumAge

    enum HandoffState: Equatable {
        case idle
        case ready
        case pendingOnPhone
        case openedOnPhone
    }

    func startExtendedSession() {
        if extendedSession == nil || extendedSession?.state == .invalid {
            extendedSession = WKExtendedRuntimeSession()
            extendedSession?.delegate = self
            extendedSession?.start()
            print("Extended runtime session started for data transfer.")
        }
    }

    func stopExtendedSession() {
        guard !isCapturing else { return }
        extendedSession?.invalidate()
        extendedSession = nil
        print("Extended runtime session stopped.")
    }

    // WKExtendedRuntimeSessionDelegate methods
    func extendedRuntimeSession(_ extendedRuntimeSession: WKExtendedRuntimeSession, didInvalidateWith reason: WKExtendedRuntimeSessionInvalidationReason, error: Error?) {
        print("Extended session invalidated: \(reason)")
        if extendedSession === extendedRuntimeSession { extendedSession = nil }
    }

    func extendedRuntimeSessionDidStart(_ extendedRuntimeSession: WKExtendedRuntimeSession) {
        print("Extended session did start")
    }

    func extendedRuntimeSessionWillExpire(_ extendedRuntimeSession: WKExtendedRuntimeSession) {
        print("Extended session will expire")
    }

    func handoffTitle(for handoffUrl: String? = nil) -> String {
        guard let url = handoffUrl ?? self.handoffUrl,
              let parsedUrl = URL(string: url),
              let route = parsedUrl.host,
              route == "job",
              parsedUrl.pathComponents.count > 1 else {
            return "Continue on Phone"
        }

        return "Open job \(parsedUrl.pathComponents[1]) on Phone"
    }

    var handoffSubtitle: String {
        switch handoffState {
        case .idle:
            return ""
        case .ready:
            return isReachable ? "Open the fuller phone view shown below." : "iPhone must be reachable first."
        case .pendingOnPhone:
            return "Queued on iPhone. Bring the app to the foreground to continue."
        case .openedOnPhone:
            return "The report is now open on iPhone."
        }
    }
    
    // Add reference to audio player to play tts immediately upon response
    var audioPlayerManager: AudioPlayerManager?

    private func reportMeta(from rawValue: Any?) -> ReportMeta? {
        guard let rawMeta = rawValue as? [String: Any],
              let data = try? JSONSerialization.data(withJSONObject: rawMeta),
              let decoded = try? JSONDecoder().decode(ReportMeta.self, from: data) else {
            return nil
        }
        return decoded
    }

    private func previewSections(from rawValue: Any?) -> [PreviewSectionPayload]? {
        guard let rawSections = rawValue as? [[String: Any]],
              let data = try? JSONSerialization.data(withJSONObject: rawSections),
              let decoded = try? JSONDecoder().decode([PreviewSectionPayload].self, from: data),
              !decoded.isEmpty else {
            return nil
        }
        return decoded
    }
    
    private func reportSections(from rawValue: Any?) -> [ReportBodySectionPayload]? {
        guard let rawSections = rawValue as? [[String: Any]],
              let data = try? JSONSerialization.data(withJSONObject: rawSections),
              let decoded = try? JSONDecoder().decode([ReportBodySectionPayload].self, from: data),
              !decoded.isEmpty else {
            return nil
        }
        return decoded
    }

    override init() {
        super.init()
        restorePendingCommands()
        if WCSession.isSupported() {
            let session = WCSession.default
            session.delegate = self
            session.activate()
        }
    }

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async {
            self.isReachable = session.isReachable
            self.updateTransportStatus(session)
            self.pruneExpiredPendingCommands()
            self.cleanupCommandTransfers()
            self.processQueue(startNewPass: true)
            if session.isReachable {
                self.resumeResultPollingIfNeeded()
                self.fetchJobs()
            }
        }
    }

    private func updateTransportStatus(_ session: WCSession) { 
        let stateText: String 
        switch session.activationState { 
        case .notActivated: stateText = "Not Activated" 
        case .inactive: stateText = "Inactive" 
        case .activated: stateText = session.isReachable ? "Connected" : "Reconnecting..." 
        @unknown default: stateText = "Unknown" 
        } 
        DispatchQueue.main.async { 
            self.transportStatus = stateText 
        } 
    } 

    func sessionReachabilityDidChange(_ session: WCSession) {
        DispatchQueue.main.async {
            self.isReachable = session.isReachable
            self.updateTransportStatus(session)
            if session.isReachable {
                self.resumeResultPollingIfNeeded()
                self.processQueue(startNewPass: true)
                self.fetchJobs()
            }
        }
    }

    func session(
        _ session: WCSession,
        didReceiveMessage message: [String: Any],
        replyHandler: @escaping ([String: Any]) -> Void
    ) {
        let action = message["action"] as? String
        guard action == "reset_connection_state" || action == "connection_refreshed" else {
            replyHandler(["error": "Unknown action"])
            return
        }
        let configuredAt = (message["configured_at"] as? TimeInterval) ?? Date().timeIntervalSince1970
        DispatchQueue.main.async {
            if action == "connection_refreshed" {
                self.checkDelivery(allowConfirmedSubmission: false)
                replyHandler(["status": "refreshed"])
            } else {
                self.resetConnectionState(configuredAt: configuredAt)
                replyHandler(["status": "reset"])
            }
        }
    }

    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        handleBackgroundMessage(userInfo)
    }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        handleBackgroundMessage(message)
    }

    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        handleBackgroundMessage(applicationContext)
    }

    func session(_ session: WCSession, didFinish fileTransfer: WCSessionFileTransfer, error: Error?) {
        guard fileTransfer.file.metadata?["action"] as? String == WatchCommandTransport.fileAction,
              let commandID = fileTransfer.file.metadata?["command_id"] as? String else { return }
        DispatchQueue.main.async {
            // WC delivery is not a backend receipt. Keep the saved recording on
            // both success and error; only a matching job receipt retires it.
            if session.activationState == .activated, !session.outstandingFileTransfers.contains(where: {
                $0.file.metadata?["command_id"] as? String == commandID
            }) {
                self.commandFiles.remove(commandID: commandID)
            }
        }
    }

    private func handleBackgroundMessage(_ message: [String: Any]) {
        switch message["action"] as? String {
        case WatchCommandTransport.receiptAction:
            DispatchQueue.main.async {
                guard let commandID = message["command_id"] as? String,
                      let command = self.pendingCommands.first(where: { $0.id == commandID }) else { return }
                let identity = WatchCommandTransport.identity(commandID: commandID, request: self.request(for: command))
                guard let data = WatchCommandTransport.receivedReceipt(message, matching: identity) else { return }
                self.acceptCommandReceipt(data, commandID: commandID, digest: identity.digest)
            }
        case "reset_connection_state":
            let configuredAt = (message["configured_at"] as? TimeInterval) ?? Date().timeIntervalSince1970
            DispatchQueue.main.async {
                self.resetConnectionState(configuredAt: configuredAt)
            }
        case "connection_refreshed":
            DispatchQueue.main.async { self.checkDelivery(allowConfirmedSubmission: false) }
        case "terminal_job_result":
            DispatchQueue.main.async {
                self.applyTerminalPush(message)
            }
        default:
            break
        }
    }

    private func applyTerminalPush(_ message: [String: Any], allowUntrackedJob: Bool = false) {
        guard let jobId = message["job_id"] as? String, !jobId.isEmpty,
              let status = message["status"] as? String,
              status == "completed" || status == "failed" else { return }
        let persisted = UserDefaults.standard.string(forKey: Self.pendingJobDefaultsKey)
        // Background WCSession snapshots may arrive late, so they may only
        // replace the result for the job this screen is actually waiting on.
        // A notification the user explicitly tapped is different: its APNs
        // payload is the authoritative terminal result even if watchOS already
        // expired the polling window and cleared the pending-job record.
        guard allowUntrackedJob || (!deliveryTracking.blocksResultUpdates && (jobId == pollingJobId || jobId == persisted)) else { return }
        if UserDefaults.standard.string(forKey: Self.lastTerminalJobDefaultsKey) == jobId,
           pollingJobId != jobId, !allowUntrackedJob {
            return
        }

        let summary = (message["summary"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let deepLink = (message["deep_link"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let state = CVZJobState.resolve(status: status, outcome: message["outcome"] as? String)

        stopResultPolling()
        resultState = state
        responseText = (summary?.isEmpty == false)
            ? summary!
            : NSLocalizedString(state.titleKey, comment: "job state")
        continuation.observe(jobId)
        handoffUrl = deepLink?.isEmpty == false ? deepLink : "ceviz://job/\(jobId)"
        handoffJobId = jobId
        handoffState = .ready
        handoffPreview = nil
        UserDefaults.standard.set(jobId, forKey: Self.lastTerminalJobDefaultsKey)
        playResultHaptic(state)
        if WCSession.default.isReachable {
            fetchJobs()
            if !allowUntrackedJob { processQueue() }
        }
    }

    /// A tapped terminal notification already contains everything the compact
    /// Watch result needs. Apply it immediately instead of showing the pending
    /// state while iPhone wakes and performs another backend round trip.
    func consumeTerminalNotification(_ userInfo: [AnyHashable: Any]) {
        guard let jobId = userInfo["job_id"] as? String, !jobId.isEmpty else { return }
        let status = (userInfo["job_status"] as? String) ?? (userInfo["status"] as? String) ?? ""
        guard status == "completed" || status == "failed" else { return }

        let payload: [String: Any] = [
            "action": "terminal_job_result",
            "job_id": jobId,
            "status": status,
            "outcome": userInfo["outcome"] as? String ?? "unknown",
            "summary": userInfo["watch_summary"] as? String ?? "",
            "deep_link": userInfo["deep_link"] as? String ?? "",
            "requires_phone_handoff": userInfo["requires_phone_handoff"] as? Bool ?? false,
        ]
        DispatchQueue.main.async {
            self.applyTerminalPush(payload, allowUntrackedJob: true)
            self.resultPresentationRequest = UUID()
        }
    }

    private func resetConnectionState(configuredAt: TimeInterval) {
        guard deliveryTracking.receiveReset(at: configuredAt) else { return }
        jobsTracking.reset()
        continuation.reset()
        captureParentJobID = nil
        let removedIDs = Set(pendingCommands.filter { $0.timestamp.timeIntervalSince1970 <= configuredAt }.map(\.id))
        let invalidatedAttempt = deliveryTracking.invalidate(removedCommandIDs: removedIDs)
        if invalidatedAttempt {
            stopExtendedSession()
        }
        pendingCommands.removeAll {
            $0.timestamp.timeIntervalSince1970 <= configuredAt
        }
        persistPendingCommands()
        cleanupCommandTransfers()
        if invalidatedAttempt && !pendingCommands.isEmpty {
            resultState = .queued
            responseText = NSLocalizedString("Request saved on Watch. Waiting for iPhone.", comment: "")
        }
        let pendingJobAt = UserDefaults.standard.double(forKey: Self.pendingJobAtDefaultsKey)
        let hasNewerPendingJob = pendingJobAt > configuredAt

        if !hasNewerPendingJob && pendingCommands.isEmpty {
            deliveryTracking.reset()
            stopResultPolling()
            resultState = nil
            responseText = ""
            handoffState = .idle
            handoffUrl = nil
            handoffJobId = nil
            handoffPreview = nil
        }
        transportStatus = WCSession.default.isReachable ? "Connected" : "Reconnecting..."
        if WCSession.default.activationState != .activated {
            WCSession.default.activate()
        }
        processQueue(startNewPass: true)
    }

    func showCaptureError(_ message: String) {
        captureParentJobID = nil
        responseText = message
        resultState = nil
        handoffUrl = nil
        handoffJobId = nil
        handoffState = .idle
        handoffPreview = nil
    }

    private func playResultHaptic(_ state: CVZJobState) {
        switch state {
        case .completed: WKInterfaceDevice.current().play(.success)
        case .failed: WKInterfaceDevice.current().play(.failure)
        case .blocked, .needsInput: WKInterfaceDevice.current().play(.notification)
        default: WKInterfaceDevice.current().play(.click)
        }
    }

    func fetchJobs() {
        jobsTracking.expire()
        guard !jobsTracking.isLoading else { return }
        let generation = jobsTracking.begin()
        guard WCSession.default.activationState == .activated, WCSession.default.isReachable else {
            jobsTracking.fail("Jobs did not refresh. Check the iPhone connection and try again.", generation: generation)
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + WatchDeliveryTracking.attemptDuration) { [weak self] in
            self?.jobsTracking.expire()
        }
        WCSession.default.sendMessage(["action": "fetch_jobs"], replyHandler: { reply in
            DispatchQueue.main.async {
                self.jobsTracking.receive(reply, generation: generation)
            }
        }, errorHandler: { _ in
            DispatchQueue.main.async {
                self.jobsTracking.fail("Jobs did not refresh. Check the iPhone connection and try again.", generation: generation)
            }
        })
    }


    private func applySummarizeReply(
        _ reply: [String: Any],
        jobId: String
    ) {
        let summary = reply["summary"] as? String ?? "Unknown response"
        let requiresPhoneHandoff = reply["requires_phone_handoff"] as? Bool ?? false
        let handoffUrl = reply["handoff_url"] as? String ?? reply["deep_link"] as? String ?? "ceviz://job/\(jobId)"
        let transcript = reply["transcript"] as? String
        let phoneReport = reply["phone_report"] as? String
        let reportMeta = self.reportMeta(from: reply["report_meta"])
        let previewSections = self.previewSections(from: reply["preview_sections"])
        let reportSections = self.reportSections(from: reply["report_sections"])

        self.responseText = summary
        self.resultState = CVZJobState.resolve(
            status: reportMeta?.status ?? reply["status"] as? String ?? "",
            outcome: reply["outcome"] as? String ?? reportMeta?.outcome
        )
        if self.resultState != .running && self.resultState != .queued {
            self.continuation.observe(jobId)
        }
        self.handoffUrl = handoffUrl
        self.handoffJobId = jobId
        self.handoffState = .ready
        self.handoffPreview = requiresPhoneHandoff
            ? HandoffPreview(
                transcript: transcript,
                summaryText: reportMeta?.watchSummary ?? summary,
                phoneReport: reportMeta?.phoneReport ?? phoneReport,
                category: reportMeta?.category,
                nextAction: reportMeta?.nextAction,
                retryCount: reportMeta?.retryCount ?? 0,
                failureCode: reportMeta?.failureCode,
                failureMessage: reportMeta?.failureMessage,
                reportSections: reportSections,
                previewSections: previewSections
            )
            : nil
    }

    // MARK: - Result polling (PTT sonrasi is tamamlanana kadar)

    private func startResultPolling(jobId: String) {
        stopResultPolling()
        resultTracking.start(jobId)
        resultState = .running
        // watchOS uygulamayi tamamen oldurebilir; bekleyen isi diske yaz ki
        // yeniden acilista sonuc kurtarilabilsin.
        UserDefaults.standard.set(jobId, forKey: Self.pendingJobDefaultsKey)
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: Self.pendingJobAtDefaultsKey)
        pollErrorCount = 0
        resultPollDeadline = Date().addingTimeInterval(180)
        startExtendedSession()
        resultPollTimer = Timer.scheduledTimer(withTimeInterval: 4.0, repeats: true) { [weak self] _ in
            self?.pollJobResult(jobId: jobId)
        }
    }

    private func stopResultPolling() {
        resultPollTimer?.invalidate()
        resultPollTimer = nil
        resultPollDeadline = nil
        resultTracking.reset()
        pollErrorCount = 0
        // Diskteki kaydi da temizle. Aksi halde yarim kalan bir bekleme
        // sonraki her acilista "isleniyor" ekranini diriltiyor.
        clearPendingJob()
        stopExtendedSession()
    }

    private func clearPendingJob() {
        UserDefaults.standard.removeObject(forKey: Self.pendingJobDefaultsKey)
        UserDefaults.standard.removeObject(forKey: Self.pendingJobAtDefaultsKey)
    }

    private func pauseResultPolling() {
        resultPollTimer?.invalidate()
        resultPollTimer = nil
        resultPollDeadline = nil
        pollErrorCount = 0
        // A foreground polling budget is not the remote job's lifetime.
        // Keep its receipt so a late push or the next wake can reconcile it.
        resultTracking.pause()
        stopExtendedSession()
    }

    /// watchOS bilek indiginde uygulamayi askiya alip poll timer'ini
    /// oldurebiliyor, hatta uygulamayi tamamen sonlandirabiliyor.
    /// Aktiflesince (soguk baslangic dahil) diske yazilmis bekleyen isi
    /// hatirla, sonucu hemen sor ve timer'i tazele.
    func resumeResultPollingIfNeeded() {
        guard !deliveryTracking.blocksResultUpdates else { return }
        let persisted = UserDefaults.standard.string(forKey: Self.pendingJobDefaultsKey)
        guard let jobId = pollingJobId ?? persisted else { return }

        // updateApplicationContext keeps the newest terminal result even when
        // watchOS suspends the app before invoking the delegate. Consume that
        // durable snapshot synchronously on every foreground/wake transition.
        let context = WCSession.default.receivedApplicationContext
        if context["action"] as? String == "terminal_job_result",
           context["job_id"] as? String == jobId {
            applyTerminalPush(context)
            return
        }

        // A suspended timer keeps its old in-memory deadline. Refresh it before
        // the immediate recovery poll so wake-up never discards a finished job
        // merely because the device slept longer than the original window.
        resultPollDeadline = Date().addingTimeInterval(120)
        if resultState != .running {
            resultState = .running
            responseText = NSLocalizedString("Working… (checking for a pending result)", comment: "")
        }
        resultTracking.start(jobId)

        if resultPollTimer == nil || !(resultPollTimer?.isValid ?? false) {
            resultPollDeadline = Date().addingTimeInterval(120)
            resultPollTimer = Timer.scheduledTimer(withTimeInterval: 4.0, repeats: true) { [weak self] _ in
                self?.pollJobResult(jobId: jobId)
            }
        }
        pollJobResult(jobId: jobId)
    }

    private func pollJobResult(jobId: String) {
        guard jobId == pollingJobId, !deliveryTracking.blocksResultUpdates else { return }
        if let deadline = resultPollDeadline, Date() > deadline {
            pauseResultPolling()
            resultState = .unknown
            responseText = NSLocalizedString("Last known state: working. Reopen Ceviz to check the result.", comment: "")
            return
        }

        guard WCSession.default.isReachable else { return }

        WCSession.default.sendMessage(["action": "summarize_job", "job_id": jobId], replyHandler: { reply in
            // Backend "boyle bir is yok" diyorsa (servis yeniden basladi,
            // is listeden dustu) sonsuza kadar yoklamanin anlami yok.
            if let message = reply["error"] as? String {
                DispatchQueue.main.async {
                    guard self.pollingJobId == jobId, !self.deliveryTracking.blocksResultUpdates else { return }
                    self.pollErrorCount += 1
                    if self.pollErrorCount >= 3 {
                        self.pauseResultPolling()
                        self.resultState = .unknown
                        self.responseText = String(
                            format: NSLocalizedString("Result unavailable: %@", comment: ""), message)
                    }
                }
                return
            }
            DispatchQueue.main.async {
                if self.pollingJobId == jobId { self.pollErrorCount = 0 }
            }

            let reportMeta = self.reportMeta(from: reply["report_meta"])
            let jobStatus = reportMeta?.status ?? (reply["status"] as? String) ?? ""
            guard jobStatus == "completed" || jobStatus == "failed" else { return }

            DispatchQueue.main.async {
                // A late reply for an older job cannot clear a newer receipt.
                guard !self.deliveryTracking.blocksResultUpdates, self.resultTracking.finish(jobId) else { return }
                self.stopResultPolling()
                let state = CVZJobState.resolve(status: jobStatus, outcome: reply["outcome"] as? String ?? reportMeta?.outcome)
                self.playResultHaptic(state)
                UserDefaults.standard.set(jobId, forKey: Self.lastTerminalJobDefaultsKey)
                self.applySummarizeReply(reply, jobId: jobId)
                self.processQueue()
                self.fetchJobs()
            }
        }, errorHandler: { error in
            // Gecici baglanti hatasi olabilir; ama ust uste tekrarliyorsa
            // kullaniciya goster — sessiz sonsuz bekleme en kotu durum.
            DispatchQueue.main.async {
                guard self.pollingJobId == jobId, !self.deliveryTracking.blocksResultUpdates else { return }
                self.pollErrorCount += 1
                if self.pollErrorCount >= 3 {
                    self.pauseResultPolling()
                    self.resultState = .unknown
                    self.responseText = String(format: NSLocalizedString("Cannot receive result: %@", comment: ""), error.localizedDescription)
                }
            }
        })
    }

    func openHandoff(url explicitUrl: String? = nil, jobId: String? = nil) {
        guard let url = explicitUrl ?? handoffUrl else { return }
        let resolvedJobId = jobId ?? handoffJobId
        let payload: [String: Any] = [
            "action": "open_handoff",
            "url": url,
            "job_id": resolvedJobId ?? "",
        ]

        guard WCSession.default.isReachable else {
            WCSession.default.transferUserInfo(payload)
            DispatchQueue.main.async {
                if let resolvedJobId { self.handoffJobId = resolvedJobId }
                self.handoffState = .pendingOnPhone
            }
            return
        }

        WCSession.default.sendMessage(payload) { reply in
            DispatchQueue.main.async {
                if let resolvedJobId {
                    self.handoffJobId = resolvedJobId
                }
                if let error = reply["error"] as? String {
                    self.handoffState = .ready
                    print("Handoff error: \(error)")
                    return
                }

                let status = reply["status"] as? String ?? "opened"
                switch status {
                case "pending":
                    self.handoffState = .pendingOnPhone
                default:
                    self.handoffState = .openedOnPhone
                }
            }
        } errorHandler: { error in
            WCSession.default.transferUserInfo(payload)
            DispatchQueue.main.async {
                self.handoffState = .pendingOnPhone
                print("Immediate handoff unavailable; queued: \(error.localizedDescription)")
            }
        }
    }

    func sendAudioCommand(audioBase64: String) {
        // Persist before attempting delivery. Retries reuse the same audio and timestamp.
        queueCommand(audioBase64: audioBase64)
        processQueue()
    }

    func continuationJobID(for displayedJobID: String?, at date: Date = Date()) -> String? {
        guard !deliveryTracking.blocksResultUpdates else { return nil }
        return continuation.parent(for: displayedJobID, at: date)
    }

    func beginCaptureContinuation(displayedJobID: String?) {
        // A new deliberate capture may leave a read-only recovery check, never
        // cancel an audio submission or turn its late response into replay permission.
        if deliveryTracking.interruptCheck() { stopExtendedSession() }
        captureParentJobID = continuationJobID(for: displayedJobID)
    }

    func cancelCaptureContinuation() {
        captureParentJobID = nil
        continuation.reset()
    }

    private func request(for command: QueuedCommand) -> WatchCommandRequest {
        WatchCommandRequest(
            audioData: command.audioData,
            format: "m4a",
            clientTimestamp: ISO8601DateFormatter().string(from: command.timestamp),
            continueJobId: command.continueJobId
        )
    }

    private func sendQueuedCommand(_ command: QueuedCommand) {
        let session = WCSession.default
        guard session.activationState == .activated, session.isReachable else { return }
        let generation = beginDeliveryAttempt(command, operation: .submit)
        guard command.recoveryProtocol == 1 else {
            failQueueAttempt(commandID: command.id, generation: generation,
                message: NSLocalizedString("This older recording cannot be resent safely. Check Jobs on iPhone before recording it again.", comment: ""))
            return
        }
        let request = request(for: command)
        let identity = WatchCommandTransport.identity(commandID: command.id, request: request)

        // Even a small standalone command needs the phone's durable protocol;
        // an old phone would ignore its marker and use the unsafe legacy POST.
        session.sendMessage(["action": WatchCommandTransport.capabilitiesAction], replyHandler: { reply in
            DispatchQueue.main.async {
                self.expireDeliveryAttempt()
                guard self.deliveryTracking.isCurrentAttempt(command.id, generation: generation),
                      self.pendingCommands.contains(where: { $0.id == command.id }) else { return }
                guard session.activationState == .activated, WatchCommandTransport.isCurrent(request) else {
                    self.failQueueAttempt(commandID: command.id, generation: generation)
                    return
                }
                guard WatchCommandTransport.supportsRecovery(reply),
                      (request.continueJobId == nil || WatchCommandTransport.supportsContinuation(reply)) else {
                    self.failQueueAttempt(commandID: command.id, generation: generation,
                        message: (reply["error_reason"] as? String) ?? NSLocalizedString("Update Ceviz on iPhone to send this recording. It remains saved on Watch.", comment: ""))
                    return
                }
                guard let journalID = reply["delivery_journal_id"] as? String,
                      let index = self.pendingCommands.firstIndex(where: { $0.id == command.id }),
                      self.pendingCommands[index].pinDeliveryJournal(journalID) else {
                    self.failQueueAttempt(commandID: command.id, generation: generation,
                        message: NSLocalizedString("Delivery records changed on iPhone. This recording will not be resent. Check Jobs before recording it again.", comment: ""))
                    return
                }
                // Pin before crossing WCSession. A delayed file carries this
                // incarnation even if both phone and helper records are lost.
                self.persistPendingCommands()
                let pinned = self.pendingCommands[index]
                do {
                    let data = try WatchCommandTransport.encode(request, commandID: command.id,
                        recoveryProtocol: pinned.recoveryProtocol, deliveryJournalID: pinned.deliveryJournalID)
                    guard !WatchCommandTransport.needsFile(data) || WatchCommandTransport.supportsFiles(reply) else {
                        self.failQueueAttempt(commandID: command.id, generation: generation,
                            message: NSLocalizedString("Update Ceviz on iPhone to send this recording. It remains saved on Watch.", comment: ""))
                        return
                    }
                    self.deliverQueuedCommand(pinned, data: data, identity: identity, generation: generation)
                } catch {
                    self.failQueueAttempt(commandID: command.id, generation: generation,
                        message: NSLocalizedString("Request could not be prepared. Recording remains saved on Watch.", comment: ""))
                }
            }
        }, errorHandler: { _ in
            DispatchQueue.main.async { self.failQueueAttempt(commandID: command.id, generation: generation) }
        })
    }

    private func beginDeliveryAttempt(_ command: QueuedCommand, operation: WatchDeliveryTracking.Operation) -> Int {
        let presents = operation == .submit || deliveryTracking.presentsRecovery || deliveryTracking.isFocused(command.id)
            || (!deliveryTracking.hasUnconfirmedFocus && handoffJobId == nil && pollingJobId == nil)
        if presents {
            pauseResultPolling()
            startExtendedSession()
            resultState = nil
            responseText = NSLocalizedString(operation == .submit ? "Sending request…" : "Checking delivery…", comment: "")
            handoffUrl = nil
            handoffJobId = nil
            handoffState = .idle
            handoffPreview = nil
        }
        let generation = deliveryTracking.begin(command.id, operation: operation, presentsResult: presents)
        DispatchQueue.main.asyncAfter(deadline: .now() + WatchDeliveryTracking.attemptDuration) { [weak self] in
            self?.expireDeliveryAttempt()
        }
        return generation
    }

    private func reconcileQueuedCommand(_ command: QueuedCommand) {
        let identity = WatchCommandTransport.identity(commandID: command.id, request: request(for: command))
        let generation = beginDeliveryAttempt(command, operation: .reconcile)
        var message: [String: Any] = [
            "action": WatchCommandTransport.statusAction,
            "command_id": identity.commandID, "audio_digest": identity.digest,
        ]
        if let journalID = command.deliveryJournalID { message["delivery_journal_id"] = journalID }
        WCSession.default.sendMessage(message, replyHandler: { reply in
            DispatchQueue.main.async {
                self.expireDeliveryAttempt()
                guard self.deliveryTracking.isCurrentAttempt(command.id, generation: generation) else { return }
                switch WatchCommandTransport.deliveryStatus(reply, matching: identity) {
                case .accepted(let data):
                    self.acceptCommandReceipt(data, commandID: command.id, digest: identity.digest)
                case .notSubmitted:
                    guard command.canResumeDelivery else {
                        self.failQueueAttempt(commandID: command.id, generation: generation,
                            message: NSLocalizedString("This older recording cannot be resent safely. Check Jobs on iPhone before recording it again.", comment: ""))
                        return
                    }
                    let presents = self.deliveryTracking.isPresentingAttempt
                    guard self.deliveryTracking.confirmNotSubmitted(command.id, generation: generation) else { return }
                    if presents {
                        self.stopExtendedSession()
                        self.resultState = .queued
                        self.responseText = NSLocalizedString("Not submitted yet. Check delivery to send the saved request.", comment: "")
                    }
                    self.processQueue()
                case .inFlight:
                    self.failQueueAttempt(commandID: command.id, generation: generation,
                        message: NSLocalizedString("iPhone is checking this request. Check delivery again; do not record it again.", comment: ""))
                case .unknown:
                    self.failQueueAttempt(commandID: command.id, generation: generation,
                        message: (reply["error_reason"] as? String) ?? (command.recoveryProtocol == nil
                            ? NSLocalizedString("This older recording cannot be resent safely. Check Jobs on iPhone before recording it again.", comment: "") : nil))
                }
            }
        }, errorHandler: { _ in
            DispatchQueue.main.async { self.failQueueAttempt(commandID: command.id, generation: generation) }
        })
    }

    private func expireDeliveryAttempt() {
        guard let attempt = deliveryTracking.expiredAttempt() else { return }
        failQueueAttempt(commandID: attempt.commandID, generation: attempt.generation)
    }

    private func deliverQueuedCommand(_ command: QueuedCommand, data: Data,
                                      identity: WatchCommandTransport.Identity, generation: Int) {
        let session = WCSession.default
        expireDeliveryAttempt()
        guard deliveryTracking.isCurrentAttempt(command.id, generation: generation) else { return }
        if WatchCommandTransport.needsFile(data) {
            // A retry reuses an outstanding transfer and its immutable parent.
            let alreadyQueued = session.outstandingFileTransfers.contains {
                $0.file.metadata?["action"] as? String == WatchCommandTransport.fileAction &&
                $0.file.metadata?["command_id"] as? String == identity.commandID &&
                $0.file.metadata?["audio_digest"] as? String == identity.digest
            }
            do {
                if !alreadyQueued {
                    let file = try commandFiles.stage(data, commandID: command.id)
                    guard deliveryTracking.markDispatched(command.id, generation: generation) else { return }
                    session.transferFile(file, metadata: identity.fileMetadata)
                } else {
                    _ = deliveryTracking.markDispatched(command.id, generation: generation)
                }
                responseText = NSLocalizedString("Recording saved. Transferring to iPhone in the background…", comment: "")
            } catch { failQueueAttempt(commandID: command.id, generation: generation) }
            return
        }
        guard deliveryTracking.markDispatched(command.id, generation: generation) else { return }
        session.sendMessageData(data, replyHandler: { replyData in
            DispatchQueue.main.async {
                let response = try? JSONDecoder().decode(WatchCommandResponse.self, from: replyData)
                if let response, WatchCommandTransport.isReceipt(response) {
                    self.acceptCommandReceipt(replyData, commandID: command.id, digest: identity.digest)
                } else {
                    self.failQueueAttempt(commandID: command.id, generation: generation,
                                          message: response?.status == "error" ? response?.summaryText : nil)
                }
            }
        }, errorHandler: { _ in
            DispatchQueue.main.async {
                self.failQueueAttempt(commandID: command.id, generation: generation)
            }
        })
    }

    private func failQueueAttempt(commandID: String, generation: Int, message: String? = nil) {
        let presents = deliveryTracking.isPresentingAttempt
        guard deliveryTracking.deferAttempt(commandID, generation: generation) else { return }
        if presents {
            let neverSent = deliveryTracking.nextOperation(for: commandID) == .submit
            resultState = neverSent ? .queued : .unknown
            responseText = message ?? NSLocalizedString(neverSent
                ? "Request saved on Watch. Waiting for iPhone."
                : "Delivery is unconfirmed. Check delivery or Jobs before recording again.", comment: "")
            stopExtendedSession()
        }
        finishQueueAttempt(commandID: commandID, acknowledged: false)
    }

    private func acceptCommandReceipt(_ data: Data, commandID: String, digest: String) {
        guard let command = pendingCommands.first(where: { $0.id == commandID }),
              WatchCommandTransport.identity(commandID: commandID, request: request(for: command)).digest == digest,
              let response = try? JSONDecoder().decode(WatchCommandResponse.self, from: data),
              WatchCommandTransport.isReceipt(response), let jobId = response.jobId else { return }

        // Both immediate and background receipts retire only their matching
        // saved command. An older receipt cannot steal a newer command's focus.
        acknowledgeQueuedCommand(commandID: commandID, matchingAudioData: command.audioData)
        guard deliveryTracking.accept(commandID) else {
            fetchJobs()
            processQueue()
            return
        }
        stopExtendedSession()
        guard WatchResultTracking.receiptCanAdvance(
            jobID: jobId, status: response.status,
            lastTerminalJobID: UserDefaults.standard.string(forKey: Self.lastTerminalJobDefaultsKey)
        ) else {
            // The receipt is older than a known terminal result. It still ends
            // Sending, even if that terminal result is no longer on this screen.
            let presentation = WatchResultTracking.terminalReceiptPresentation(
                jobID: jobId, displayedJobID: handoffJobId, state: resultState, text: responseText)
            resultState = presentation.state
            responseText = presentation.text
            if handoffJobId != jobId {
                handoffJobId = jobId
                handoffUrl = "ceviz://job/\(jobId)"
                handoffState = .ready
            }
            fetchJobs()
            finishQueueAttempt(commandID: commandID, acknowledged: true)
            return
        }
        responseText = response.summaryText
        resultState = CVZJobState.resolve(status: response.status, outcome: response.outcome ?? response.reportMeta?.outcome)
        let terminal = response.status == "completed" || response.status == "failed"
        if terminal { continuation.observe(jobId) }
        let needsPhone = response.reportMeta?.requiresPhoneHandoff ?? response.requiresPhoneHandoff
        handoffUrl = response.handoffUrl ?? response.deepLink ?? "ceviz://job/\(jobId)"
        handoffJobId = jobId
        handoffState = .ready
        handoffPreview = needsPhone && response.handoffUrl != nil
            ? HandoffPreview(
                transcript: response.transcript,
                summaryText: response.reportMeta?.watchSummary ?? response.summaryText,
                phoneReport: response.reportMeta?.phoneReport ?? response.phoneReport,
                category: response.reportMeta?.category,
                nextAction: response.reportMeta?.nextAction,
                retryCount: response.reportMeta?.retryCount ?? 0,
                failureCode: response.reportMeta?.failureCode,
                failureMessage: response.reportMeta?.failureMessage,
                reportSections: response.reportSections,
                previewSections: response.previewSections
            ) : nil
        if terminal {
            stopResultPolling()
            playResultHaptic(resultState ?? .resultReady)
            UserDefaults.standard.set(jobId, forKey: Self.lastTerminalJobDefaultsKey)
        } else {
            startResultPolling(jobId: jobId)
            WKInterfaceDevice.current().play(.click)
        }
        if !isCapturing, let tts = response.ttsAudioData, let format = response.ttsFormat {
            audioPlayerManager?.play(base64Data: tts, format: format)
        }
        fetchJobs()
        finishQueueAttempt(commandID: commandID, acknowledged: true)
    }

    private func queueCommand(audioBase64: String) {
        pauseResultPolling()
        pruneExpiredPendingCommands()
        if !pendingCommands.contains(where: { $0.matchesCapture(audioData: audioBase64, continueJobId: captureParentJobID) }) {
            let commandID = UUID().uuidString
            pendingCommands.append(QueuedCommand(
                id: commandID,
                audioData: audioBase64,
                timestamp: Date(),
                retryCount: 0,
                continueJobId: captureParentJobID,
                recoveryProtocol: 1
            ))
            deliveryTracking.registerNew(commandID, precedingCommandIDs: pendingCommands.map(\.id))
            persistPendingCommands()
        }
        captureParentJobID = nil
        continuation.reset()
        resultState = .queued
        responseText = NSLocalizedString(pendingCommands.count > 1
            ? "New recording saved. Earlier unconfirmed recordings will not be resent."
            : "Request saved on Watch. Waiting for iPhone.", comment: "")
        stopExtendedSession()
    }

    private func restorePendingCommands() {
        guard let data = UserDefaults.standard.data(forKey: Self.pendingCommandsDefaultsKey),
              let decoded = try? JSONDecoder().decode([QueuedCommand].self, from: data) else {
            return
        }
        pendingCommands = decoded
        pruneExpiredPendingCommands()
        if let command = pendingCommands.first {
            let hasAcceptedJob = UserDefaults.standard.string(forKey: Self.pendingJobDefaultsKey) != nil
            let generation = deliveryTracking.begin(command.id, operation: .reconcile, presentsResult: !hasAcceptedJob)
            deliveryTracking.finishAttempt(command.id, generation: generation)
            resultState = .queued
            responseText = NSLocalizedString("Request saved on Watch. Waiting for iPhone.", comment: "")
        }
    }

    private func persistPendingCommands() {
        guard !pendingCommands.isEmpty else {
            UserDefaults.standard.removeObject(forKey: Self.pendingCommandsDefaultsKey)
            return
        }
        guard let data = try? JSONEncoder().encode(pendingCommands) else { return }
        UserDefaults.standard.set(data, forKey: Self.pendingCommandsDefaultsKey)
    }

    private func pruneExpiredPendingCommands() {
        let cutoff = Date().addingTimeInterval(-Self.pendingCommandMaxAge)
        let previousCount = pendingCommands.count
        let removedIDs = Set(pendingCommands.filter { $0.timestamp <= cutoff }.map(\.id))
        let removesFocus = removedIDs.contains { deliveryTracking.isFocused($0) }
        let wasPresenting = deliveryTracking.isPresentingAttempt
        if deliveryTracking.invalidate(removedCommandIDs: removedIDs), removesFocus || wasPresenting {
            stopExtendedSession()
        }
        pendingCommands.removeAll { $0.timestamp <= cutoff }
        if pendingCommands.count != previousCount {
            persistPendingCommands()
            cleanupCommandTransfers()
            if removesFocus || (!deliveryTracking.hasUnconfirmedFocus && handoffJobId == nil && pollingJobId == nil) {
                resultState = .unknown
                responseText = NSLocalizedString("A saved request expired and was not resent. Check Jobs before recording again.", comment: "")
            }
        }
    }

    private func acknowledgeQueuedCommand(commandID: String, matchingAudioData audioBase64: String) {
        let previousCount = pendingCommands.count
        pendingCommands.removeAll { command in
            command.id == commandID && command.audioData == audioBase64
        }
        if pendingCommands.count != previousCount {
            persistPendingCommands()
            cleanupCommandTransfers()
        }
    }

    private func cleanupCommandTransfers() {
        guard WCSession.default.activationState == .activated else { return }
        let pendingIDs = Set(pendingCommands.map(\.id))
        for transfer in WCSession.default.outstandingFileTransfers
        where transfer.file.metadata?["action"] as? String == WatchCommandTransport.fileAction {
            if let id = transfer.file.metadata?["command_id"] as? String, !pendingIDs.contains(id) {
                transfer.cancel()
            }
        }
        commandFiles.prune(keeping: pendingIDs)
    }

    private func finishQueueAttempt(commandID: String, acknowledged: Bool) {
        if !acknowledged,
           let index = pendingCommands.firstIndex(where: { $0.id == commandID }) {
            pendingCommands[index].retryCount += 1
            persistPendingCommands()
        }
        // Continue one bounded pass without recursively retrying an unknown
        // head. Deferral changes scheduling, never deletes its recording.
        DispatchQueue.main.async { self.processQueue() }
    }

    func processQueue(startNewPass: Bool = false) {
        expireDeliveryAttempt()
        pruneExpiredPendingCommands()
        if startNewPass { deliveryTracking.beginRecoveryPass() }
        guard WCSession.default.activationState == .activated,
              WCSession.default.isReachable,
              let command = deliveryTracking.nextCommand(in: pendingCommands),
              !isSending,
              !isCapturing else { return }
        switch deliveryTracking.nextOperation(for: command.id) {
        case .submit: sendQueuedCommand(command)
        case .reconcile: reconcileQueuedCommand(command)
        }
    }

    /// Same-pair refresh is read-only recovery; only an explicit check or queue
    /// recovery may submit after the phone proves this exact identity unsubmitted.
    func checkDelivery(allowConfirmedSubmission: Bool = true) {
        expireDeliveryAttempt()
        pruneExpiredPendingCommands()
        fetchJobs()
        guard !isSending, !isCapturing else { return }
        guard !pendingCommands.isEmpty else {
            resumeResultPollingIfNeeded()
            return
        }
        guard WCSession.default.activationState == .activated, WCSession.default.isReachable else {
            resultState = .unknown
            responseText = NSLocalizedString("Delivery is unconfirmed. Check delivery or Jobs before recording again.", comment: "")
            return
        }
        deliveryTracking.beginRecoveryPass(allowSubmission: allowConfirmedSubmission, presentChecks: allowConfirmedSubmission)
        processQueue()
    }

}
