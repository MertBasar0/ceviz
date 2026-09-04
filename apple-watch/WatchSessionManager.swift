import Foundation
import WatchConnectivity
import Combine
import WatchKit
import UserNotifications

struct QueuedCommand: Codable, Identifiable { 
    let id: String 
    let audioData: String 
    let timestamp: Date 
    var retryCount: Int 
} 

class WatchSessionManager: NSObject, ObservableObject, WCSessionDelegate, WKExtendedRuntimeSessionDelegate {
    static let shared = WatchSessionManager()

    @Published var isReachable = false
    @Published var responseText = ""
    @Published var handoffUrl: String? = nil
    @Published var handoffJobId: String? = nil
    @Published var activeJobs: [ActiveJob] = []
    @Published var pendingCommands: [QueuedCommand] = []
    @Published var transportStatus: String = "Disconnected"
    @Published private(set) var isSending = false
    @Published private(set) var resultState: CVZJobState?
    @Published private(set) var resultPresentationRequest = UUID()
    @Published private var resultTracking = WatchResultTracking()
    var isCapturing = false
    /// Son sonucun geldigi an. Backend, 180 sn icindeki yeni komutu ayni
    /// konusmanin devami sayiyor; saat bunu rozetle gosterir.
    @Published var lastResultAt: Date?

    static let continuationWindow: TimeInterval = 180
    @Published var handoffState: HandoffState = .idle
    private var isDrainingCommandQueue = false
    @Published var handoffPreview: HandoffPreview? = nil

    private var extendedSession: WKExtendedRuntimeSession?
    private var resultPollTimer: Timer?
    private var resultPollDeadline: Date?
    private var pollingJobId: String? { resultTracking.jobID }
    private var pollErrorCount = 0
    private var deliveryTracking = WatchDeliveryTracking()
    private static let pendingJobDefaultsKey = "cvz.pendingJobId"
    private static let pendingJobAtDefaultsKey = "cvz.pendingJobAt"
    private static let lastTerminalJobDefaultsKey = "cvz.lastTerminalJobId"
    private static let pendingCommandsDefaultsKey = "cvz.pendingCommands.v1"
    /// Sesli komutlar uzun süre sonra sürpriz biçimde çalıştırılmamalı.
    private static let pendingCommandMaxAge: TimeInterval = 15 * 60

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
            if session.isReachable {
                self.resumeResultPollingIfNeeded()
                self.processQueue()
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
                self.processQueue()
            }
        }
    }

    func session(
        _ session: WCSession,
        didReceiveMessage message: [String: Any],
        replyHandler: @escaping ([String: Any]) -> Void
    ) {
        guard message["action"] as? String == "reset_connection_state" else {
            replyHandler(["error": "Unknown action"])
            return
        }
        let configuredAt = (message["configured_at"] as? TimeInterval) ?? Date().timeIntervalSince1970
        DispatchQueue.main.async {
            self.resetConnectionState(configuredAt: configuredAt)
            replyHandler(["status": "reset"])
        }
    }

    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        handleBackgroundMessage(userInfo)
    }

    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        handleBackgroundMessage(applicationContext)
    }

    private func handleBackgroundMessage(_ message: [String: Any]) {
        switch message["action"] as? String {
        case "reset_connection_state":
            let configuredAt = (message["configured_at"] as? TimeInterval) ?? Date().timeIntervalSince1970
            DispatchQueue.main.async {
                self.resetConnectionState(configuredAt: configuredAt)
            }
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
        guard allowUntrackedJob || (!isSending && pendingCommands.isEmpty && (jobId == pollingJobId || jobId == persisted)) else { return }
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
        lastResultAt = Date()
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
        pendingCommands.removeAll {
            $0.timestamp.timeIntervalSince1970 <= configuredAt
        }
        persistPendingCommands()
        let pendingJobAt = UserDefaults.standard.double(forKey: Self.pendingJobAtDefaultsKey)
        let hasNewerPendingJob = pendingJobAt > configuredAt

        if !hasNewerPendingJob && pendingCommands.isEmpty {
            deliveryTracking.reset()
            isSending = false
            isDrainingCommandQueue = false
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
    }

    func showCaptureError(_ message: String) {
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
        guard WCSession.default.isReachable else {
            print("Cannot fetch jobs: Session not reachable")
            return
        }
        
        WCSession.default.sendMessage(["action": "fetch_jobs"], replyHandler: { reply in
            if let jobsData = reply["jobs"] as? [[String: Any]] {
                do {
                    let data = try JSONSerialization.data(withJSONObject: jobsData)
                    let decodedJobs = try JSONDecoder().decode([ActiveJob].self, from: data)
                    DispatchQueue.main.async {
                        self.activeJobs = decodedJobs
                    }
                } catch {
                    print("Failed to decode jobs: \(error)")
                }
            }
        }, errorHandler: { error in
            print("Fetch jobs error: \(error.localizedDescription)")
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
            self.lastResultAt = Date()
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
        guard !isSending, pendingCommands.isEmpty else { return }
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
        guard jobId == pollingJobId, !isSending, pendingCommands.isEmpty else { return }
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
                    guard self.pollingJobId == jobId, !self.isSending, self.pendingCommands.isEmpty else { return }
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
                guard !self.isSending, self.pendingCommands.isEmpty, self.resultTracking.finish(jobId) else { return }
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
                guard self.pollingJobId == jobId, !self.isSending, self.pendingCommands.isEmpty else { return }
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

    private func sendQueuedCommand(_ command: QueuedCommand) {
        let request = WatchCommandRequest(
            audioData: command.audioData,
            format: "m4a",
            clientTimestamp: ISO8601DateFormatter().string(from: command.timestamp)
        )
        guard let data = try? JSONEncoder().encode(request), data.count <= 60_000 else {
            acknowledgeQueuedCommand(commandID: command.id, matchingAudioData: command.audioData)
            isDrainingCommandQueue = false
            showCaptureError(NSLocalizedString("Recording too long. Please record a shorter request.", comment: ""))
            return
        }
        guard WCSession.default.isReachable else {
            finishQueueAttempt(commandID: command.id, acknowledged: false)
            return
        }

        pauseResultPolling()
        startExtendedSession()
        isSending = true
        resultState = nil
        responseText = NSLocalizedString("Sending request…", comment: "")
        handoffUrl = nil
        handoffJobId = nil
        handoffState = .idle
        handoffPreview = nil
        let generation = deliveryTracking.begin(command.id)

        DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
            guard let self, self.deliveryTracking.isCurrentAttempt(command.id, generation: generation), self.isSending else { return }
            self.isSending = false
            self.resultState = .queued
            self.responseText = NSLocalizedString("Receipt not confirmed. Request saved; reconnect to check before retrying.", comment: "")
            self.stopExtendedSession()
            self.finishQueueAttempt(commandID: command.id, acknowledged: false)
        }

        WCSession.default.sendMessageData(data, replyHandler: { replyData in
            DispatchQueue.main.async {
                guard let response = try? JSONDecoder().decode(WatchCommandResponse.self, from: replyData),
                      let jobId = response.jobId, !jobId.isEmpty,
                      ["processing", "running", "queued", "completed", "failed"].contains(response.status) else {
                    guard self.deliveryTracking.isCurrentAttempt(command.id, generation: generation), self.isSending else { return }
                    self.isSending = false
                    self.resultState = .queued
                    self.responseText = NSLocalizedString("Receipt not confirmed. Request saved; reconnect to check before retrying.", comment: "")
                    self.stopExtendedSession()
                    self.finishQueueAttempt(commandID: command.id, acknowledged: false)
                    return
                }

                // Even a late receipt retires its persisted copy. Only the newest
                // submission may replace the focused result on the voice screen.
                self.acknowledgeQueuedCommand(commandID: command.id, matchingAudioData: command.audioData)
                guard self.deliveryTracking.accept(command.id) else { return }
                self.isSending = false
                self.stopExtendedSession()
                // APNs can beat the original HTTP receipt. Retire the queue copy
                // without turning a result the user has already opened back into work.
                guard WatchResultTracking.receiptCanAdvance(
                    jobID: jobId, status: response.status,
                    lastTerminalJobID: UserDefaults.standard.string(forKey: Self.lastTerminalJobDefaultsKey)
                ) else {
                    self.fetchJobs()
                    self.finishQueueAttempt(commandID: command.id, acknowledged: true)
                    return
                }
                self.responseText = response.summaryText
                self.resultState = CVZJobState.resolve(
                    status: response.status,
                    outcome: response.outcome ?? response.reportMeta?.outcome
                )
                let terminal = response.status == "completed" || response.status == "failed"
                if terminal { self.lastResultAt = Date() }
                let needsPhone = response.reportMeta?.requiresPhoneHandoff ?? response.requiresPhoneHandoff
                self.handoffUrl = response.handoffUrl ?? response.deepLink ?? "ceviz://job/\(jobId)"
                self.handoffJobId = jobId
                self.handoffState = .ready
                self.handoffPreview = needsPhone && response.handoffUrl != nil
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
                    )
                    : nil

                if terminal {
                    self.stopResultPolling()
                    self.playResultHaptic(self.resultState ?? .resultReady)
                    UserDefaults.standard.set(jobId, forKey: Self.lastTerminalJobDefaultsKey)
                } else {
                    self.startResultPolling(jobId: jobId)
                    WKInterfaceDevice.current().play(.click)
                }
                if !self.isCapturing, let tts = response.ttsAudioData, let format = response.ttsFormat {
                    self.audioPlayerManager?.play(base64Data: tts, format: format)
                }
                self.fetchJobs()
                self.finishQueueAttempt(commandID: command.id, acknowledged: true)
            }
        }, errorHandler: { _ in
            DispatchQueue.main.async {
                guard self.deliveryTracking.isCurrentAttempt(command.id, generation: generation), self.isSending else { return }
                self.isSending = false
                self.resultState = .queued
                self.responseText = NSLocalizedString("Connection interrupted. Request saved; its receipt is not confirmed yet.", comment: "")
                self.stopExtendedSession()
                self.finishQueueAttempt(commandID: command.id, acknowledged: false)
            }
        })
    }

    private func queueCommand(audioBase64: String) {
        pauseResultPolling()
        pruneExpiredPendingCommands()
        if !pendingCommands.contains(where: { $0.audioData == audioBase64 }) {
            pendingCommands.append(QueuedCommand(
                id: UUID().uuidString,
                audioData: audioBase64,
                timestamp: Date(),
                retryCount: 0
            ))
            persistPendingCommands()
        }
        resultState = .queued
        responseText = NSLocalizedString("Request saved on Watch. Waiting for iPhone.", comment: "")
        stopExtendedSession()
    }

    private func restorePendingCommands() {
        guard let data = UserDefaults.standard.data(forKey: Self.pendingCommandsDefaultsKey),
              let decoded = try? JSONDecoder().decode([QueuedCommand].self, from: data) else {
            return
        }
        pendingCommands = decoded
        pruneExpiredPendingCommands()
        if !pendingCommands.isEmpty {
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
        pendingCommands.removeAll { $0.timestamp < cutoff }
        if pendingCommands.count != previousCount {
            persistPendingCommands()
            resultState = .unknown
            responseText = NSLocalizedString("A saved request expired and was not resent. Check Jobs before recording again.", comment: "")
        }
    }

    private func acknowledgeQueuedCommand(commandID: String?, matchingAudioData audioBase64: String) {
        let previousCount = pendingCommands.count
        pendingCommands.removeAll { command in
            if let commandID, command.id == commandID { return true }
            return command.audioData == audioBase64
        }
        if pendingCommands.count != previousCount {
            persistPendingCommands()
        }
    }

    private func finishQueueAttempt(commandID: String, acknowledged: Bool) {
        if !acknowledged,
           let index = pendingCommands.firstIndex(where: { $0.id == commandID }) {
            pendingCommands[index].retryCount += 1
            persistPendingCommands()
        }
        isDrainingCommandQueue = false
        if acknowledged {
            processQueue()
        }
    }

    func processQueue() {
        pruneExpiredPendingCommands()
        guard WCSession.default.isReachable,
              let command = pendingCommands.first,
              !isSending,
              !isCapturing,
              !isDrainingCommandQueue else { return }
        isDrainingCommandQueue = true
        sendQueuedCommand(command)
    }

}
