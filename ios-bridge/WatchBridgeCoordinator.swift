import Foundation
import UIKit
import UserNotifications
import WatchConnectivity
import os

/// File receipt wakes the phone in the background. Keep a bounded execution
/// lease while submitting it; expiration is not a job acknowledgement.
@MainActor
private final class CommandBackgroundLease {
    private var identifier: UIBackgroundTaskIdentifier = .invalid

    init() {
        identifier = UIApplication.shared.beginBackgroundTask(withName: "Ceviz command receipt") { [weak self] in
            self?.finish()
        }
    }

    func finish() {
        guard identifier != .invalid else { return }
        UIApplication.shared.endBackgroundTask(identifier)
        identifier = .invalid
    }
}

/// The iPhone Companion Bridge that sits between the Apple Watch (WCSession)
/// and the OpenClaw Backend (URLSession).
class WatchBridgeCoordinator: NSObject, WCSessionDelegate, UNUserNotificationCenterDelegate {
    static let shared = WatchBridgeCoordinator()
    private let logger = Logger(subsystem: "com.mertbasar.ceviz.ios", category: "WatchBridge")
    private var backendURL: URL { BackendConfig.url("/api/v1/watch/command") }
    private let notificationCenter = UNUserNotificationCenter.current()
    private let handoffNotificationPrefix = "watch-ceviz.handoff."
    private let handoffNudgeDefaultsKey = "watch-ceviz.last-handoff-nudge"
    @MainActor private var latestContinuationJobId: String?
    @MainActor private var latestContinuationDetails: ContinuationDetails?
    private var pendingCommandReceipts: [String: (message: [String: Any], createdAt: Date)] = [:]
    private var commandConfigurationGeneration = 0
    private let commandResetDefaultsKey = "cvz.watchCommandResetAt"

    private override init() {
        super.init()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(connectionConfigurationDidChange),
            name: BackendConfig.connectionDidChange,
            object: nil
        )
        notificationCenter.delegate = self
        // Bildirim izni acilista DEGIL, ilk gercek handoff bildiriminden
        // hemen once istenir: kullanici daha hicbir sey yapmadan izin
        // sormak hem kotu bir ilk izlenim hem de Apple'in onerdigi
        // baglamsal isteme yaklasimina aykiri.
        if WCSession.isSupported() {
            let session = WCSession.default
            session.delegate = self
            session.activate()
        }
    }

    @objc private func connectionConfigurationDidChange() {
        resetConnectionState()
    }

    func resetConnectionState() {
        commandConfigurationGeneration += 1
        let configuredAt = Date().timeIntervalSince1970
        UserDefaults.standard.set(configuredAt, forKey: commandResetDefaultsKey)
        pendingCommandReceipts.removeAll()
        BackendTransport.shared.reset()
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        session.delegate = self
        session.activate()

        if session.activationState == .activated {
            for transfer in session.outstandingUserInfoTransfers
            where transfer.userInfo["action"] as? String == WatchCommandTransport.receiptAction {
                transfer.cancel()
            }
        }
        let resetMessage: [String: Any] = [
            "action": "reset_connection_state",
            "configured_at": configuredAt
        ]
        if session.isReachable {
            session.sendMessage(resetMessage, replyHandler: nil) { [weak self] error in
                self?.logger.warning("Watch connection reset message failed: \(error.localizedDescription)")
            }
        } else {
            session.transferUserInfo(resetMessage)
        }
    }

    // MARK: - WCSessionDelegate
    
    func sessionDidBecomeInactive(_ session: WCSession) { }
    func sessionDidDeactivate(_ session: WCSession) {
        WCSession.default.activate()
    }
    /// WCSession reply sozlukleri yalnizca property-list tiplerini kabul
    /// eder; backend JSON'undaki null'lar (NSNull) aktarimi sessizce
    /// dusurur. Reply'a girecek her sozlugu ozyinelemeli temizle.
    private func plistSafe(_ value: Any) -> Any? {
        if value is NSNull { return nil }
        if let dict = value as? [String: Any] {
            var out: [String: Any] = [:]
            for (key, inner) in dict {
                if let safe = plistSafe(inner) { out[key] = safe }
            }
            return out
        }
        if let array = value as? [Any] {
            return array.compactMap { plistSafe($0) }
        }
        return value
    }

    private func safeReply(_ dict: [String: Any]) -> [String: Any] {
        (plistSafe(dict) as? [String: Any]) ?? dict
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        DispatchQueue.main.async {
            WatchLinkStatus.shared.isReachable = session.isReachable
            self.flushCommandReceipts()
        }
    }

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async {
            WatchLinkStatus.shared.isReachable = session.isReachable
            if activationState == .activated { self.flushCommandReceipts() }
        }
        if let error = error {
            logger.error("WCSession activation failed: \(error.localizedDescription)")
        } else {
            logger.info("WCSession activated with state: \(activationState.rawValue)")
        }
    }

    /// Handles messages from the Apple Watch and proxies them to the backend.
    func session(_ session: WCSession, didReceiveMessageData messageData: Data, replyHandler: @escaping (Data) -> Void) {
        logger.info("Received audio command payload from Watch")
        do {
            let incoming = try WatchCommandTransport.decode(messageData)
            handleCommand(incoming, replyHandler: replyHandler)
        } catch {
            logger.error("Rejected invalid or expired Watch command")
            replyWithError(message: "Invalid or expired payload", replyHandler: replyHandler)
        }
    }

    func session(_ session: WCSession, didReceive file: WCSessionFile) {
        guard file.metadata?["action"] as? String == WatchCommandTransport.fileAction else { return }
        do {
            // Apple deletes this URL when the delegate returns. Read and validate
            // now, before handing the owned request bytes to asynchronous HTTP.
            let incoming = try WatchCommandTransport.receiveFile(at: file.fileURL, metadata: file.metadata)
            handleCommand(incoming, replyHandler: nil)
        } catch {
            // No receipt means no retirement on Watch. Expired files must never
            // start a job, even if WC delivers them after its app was suspended.
            logger.error("Rejected unreadable, invalid or expired Watch command file")
        }
    }

    private func handleCommand(_ incoming: WatchCommandTransport.Incoming, replyHandler: ((Data) -> Void)?) {
        Task { @MainActor in
            let resetTime = UserDefaults.standard.double(forKey: self.commandResetDefaultsKey)
            let resetAt = resetTime > 0 ? Date(timeIntervalSince1970: resetTime) : nil
            // Recheck after the main-queue hop: a configuration reset or expiry
            // may have occurred since the WC delegate read this delayed file.
            if (incoming.identity != nil || resetAt != nil),
               !WatchCommandTransport.isCurrent(incoming.request, after: resetAt) {
                if let replyHandler { self.replyWithError(message: "Expired request", replyHandler: replyHandler) }
                return
            }
            let generation = self.commandConfigurationGeneration
            let lease = CommandBackgroundLease()
            let completion: (Data) -> Void = { data in
                Task { @MainActor in
                    defer { lease.finish() }
                    guard self.commandConfigurationGeneration == generation else { return }
                    replyHandler?(data)
                    if let identity = incoming.identity,
                       let receipt = try? WatchCommandTransport.receipt(responseData: data, identity: identity) {
                        self.queueCommandReceipt(receipt)
                    }
                }
            }
            if DemoMode.isActive {
                var payload = DemoMode.watchReply(for: DemoMode.jobs.first?.id)
                payload["status"] = "completed"
                payload["summary_text"] = payload["summary"] ?? ""
                if let data = try? JSONSerialization.data(withJSONObject: payload) {
                    completion(data)
                } else {
                    self.replyWithError(message: "demo", replyHandler: completion)
                }
                return
            }
            self.forwardToBackend(request: incoming.request, configurationGeneration: generation, replyHandler: completion)
        }
    }

    @MainActor private func queueCommandReceipt(_ message: [String: Any]) {
        guard let commandID = message["command_id"] as? String else { return }
        var stamped = message
        stamped["connection_reset_at"] = UserDefaults.standard.double(forKey: commandResetDefaultsKey)
        let createdAt = Date()
        stamped["receipt_created_at"] = createdAt.timeIntervalSince1970
        pendingCommandReceipts[commandID] = (stamped, createdAt)
        flushCommandReceipts()
    }

    private func flushCommandReceipts() {
        let cutoff = Date().addingTimeInterval(-WatchCommandTransport.maximumAge)
        pendingCommandReceipts = pendingCommandReceipts.filter { $0.value.createdAt >= cutoff }
        guard !pendingCommandReceipts.isEmpty else { return }
        let session = WCSession.default
        guard session.activationState == .activated else {
            session.activate()
            return
        }
        for entry in pendingCommandReceipts.values {
            let message = entry.message
            let alreadyQueued = session.outstandingUserInfoTransfers.contains {
                $0.userInfo["action"] as? String == WatchCommandTransport.receiptAction &&
                $0.userInfo["command_id"] as? String == message["command_id"] as? String &&
                $0.userInfo["audio_digest"] as? String == message["audio_digest"] as? String
            }
            if !alreadyQueued { session.transferUserInfo(message) }
        }
        pendingCommandReceipts.removeAll()
    }

    func session(_ session: WCSession, didFinish userInfoTransfer: WCSessionUserInfoTransfer, error: Error?) {
        guard error != nil,
              userInfoTransfer.userInfo["action"] as? String == WatchCommandTransport.receiptAction,
              let id = userInfoTransfer.userInfo["command_id"] as? String else { return }
        DispatchQueue.main.async {
            // Do not recursively retry an error. The next activation/reachability
            // change can requeue this small receipt; the Watch still owns its audio.
            guard userInfoTransfer.userInfo["connection_reset_at"] as? Double ==
                UserDefaults.standard.double(forKey: self.commandResetDefaultsKey),
                  let createdAt = userInfoTransfer.userInfo["receipt_created_at"] as? Double,
                  Date().timeIntervalSince1970 - createdAt < WatchCommandTransport.maximumAge else { return }
            self.pendingCommandReceipts[id] = (userInfoTransfer.userInfo, Date(timeIntervalSince1970: createdAt))
        }
    }
    
    /// Handles dictionary messages for fetching data like active jobs.
    func session(_ session: WCSession, didReceiveMessage message: [String : Any], replyHandler: @escaping ([String : Any]) -> Void) {
        if message["action"] as? String == WatchCommandTransport.capabilitiesAction {
            replyHandler(["audio_file_v1": true])
            return
        }
        if message["action"] as? String == "register_watch_push",
           let token = message["apns_token"] as? String,
           let bundleId = message["bundle_id"] as? String {
            registerWatchPushToken(token, bundleId: bundleId, completion: replyHandler)
            return
        }

        // Demo modunda saat de ornek veriyle calissin (App Review esli
        // cihazda denerse bos ekran gormesin).
        if DemoMode.isActive {
            let action = message["action"] as? String
            if action == "fetch_jobs" {
                replyHandler(safeReply(DemoMode.jobsReplyForWatch))
                return
            }
            if action == "summarize_job" || action == "cancel_job" {
                replyHandler(safeReply(DemoMode.watchReply(for: message["job_id"] as? String)))
                return
            }
        }
        if message["action"] as? String == "fetch_jobs" {
            fetchActiveJobs(replyHandler: replyHandler)
        } else if message["action"] as? String == "cancel_job", let jobId = message["job_id"] as? String {
            performJobAction(jobId: jobId, actionPath: "cancel", replyHandler: replyHandler)
        } else if message["action"] as? String == "summarize_job", let jobId = message["job_id"] as? String {
            performJobAction(jobId: jobId, actionPath: "summarize", replyHandler: replyHandler)
        } else if message["action"] as? String == "open_handoff", let urlString = message["url"] as? String {
            logger.info("Handoff requested from Watch to continue deep-link URL: \(urlString)")

            guard let url = URL(string: urlString) else {
                replyHandler(["error": "Invalid handoff URL"])
                return
            }

            Task { @MainActor in
                let isAppActive = UIApplication.shared.applicationState == .active
                let details = self.continuationDetails(for: url)
                let opened = AppRouter.shared.open(
                    url: url,
                    source: .watch,
                    presentImmediately: isAppActive,
                    details: details
                )

                if opened {
                    let status = isAppActive ? "opened" : "pending"
                    replyHandler(["status": status])
                } else {
                    replyHandler(["error": "Unsupported handoff URL"])
                }
            }
        } else {
            replyHandler(["error": "Unknown action"])

        }
    }
    

    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        if userInfo["action"] as? String == "register_watch_push",
           let token = userInfo["apns_token"] as? String,
           let bundleId = userInfo["bundle_id"] as? String {
            registerWatchPushToken(token, bundleId: bundleId, completion: nil)
            return
        }

        guard userInfo["action"] as? String == "open_handoff",
              let urlValue = userInfo["url"] as? String,
              let url = URL(string: urlValue) else { return }

        let jobId = (userInfo["job_id"] as? String).flatMap { $0.isEmpty ? nil : $0 }
            ?? url.pathComponents.dropFirst().first
            ?? "handoff"

        Task { @MainActor in
            let details = self.continuationDetails(for: url)
            _ = AppRouter.shared.open(
                url: url,
                source: .watch,
                presentImmediately: UIApplication.shared.applicationState == .active,
                details: details
            )
        }

        configureNotificationAuthorization()
        scheduleHandoffNotificationIfNeeded(
            jobId: jobId,
            requiresPhoneHandoff: true,
            deepLinkValue: url.absoluteString,
            title: NSLocalizedString("Ceviz report ready", comment: "notification title"),
            summaryText: "Open the report requested from your Apple Watch.",
            handoffReason: nil,
            nextAction: nil,
            signatureSeed: "watch-button"
        )
    }

    private func registerWatchPushToken(
        _ token: String,
        bundleId: String,
        completion: (([String: Any]) -> Void)?
    ) {
        let cleanedToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanedToken.isEmpty, !bundleId.isEmpty else {
            completion?(["error": "Invalid Watch push registration"])
            return
        }

        let defaults = UserDefaults.standard
        let installationKey = "cvz.pushInstallationId"
        let installationId: String
        if let existing = defaults.string(forKey: installationKey), !existing.isEmpty {
            installationId = existing
        } else {
            installationId = UUID().uuidString
            defaults.set(installationId, forKey: installationKey)
        }

        let payload: [String: String] = [
            "apns_token": cleanedToken,
            "bundle_id": bundleId,
            "installation_id": installationId,
            "environment": "production",
        ]
        var request = BackendConfig.request("/api/v1/push/register", method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        request.timeoutInterval = 20
        BackendTransport.shared.dataTask(with: request) { _, response, error in
            if let error {
                self.logger.error("Watch push registration failed: \(error.localizedDescription)")
                completion?(["error": error.localizedDescription])
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200..<300).contains(status) else {
                completion?(["error": "Backend returned HTTP \(status)"])
                return
            }
            self.logger.info("Registered direct Watch push token")
            completion?(["status": "registered"])
        }.resume()
    }

    private func performJobAction(jobId: String, actionPath: String, replyHandler: @escaping ([String : Any]) -> Void) {
        let actionURL = BackendConfig.url("/api/v1/jobs/\(jobId)/\(actionPath)")
        var request = URLRequest(url: actionURL)
        request.httpMethod = "POST"
        BackendConfig.applyAuth(&request)
        
        let task = BackendTransport.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                self.logger.error("Backend request failed: \(error.localizedDescription)")
                replyHandler(["error": "Backend unavailable"])
                return
            }
            guard let data = data, let resultObj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                replyHandler(["error": "Failed to parse action response"])
                return
            }

            if actionPath == "summarize",
               let decodedResponse = try? JSONDecoder().decode(JobSummaryResponse.self, from: data) {
                Task { @MainActor in
                    self.storeLatestContinuation(
                        jobId: jobId,
                        summaryText: decodedResponse.reportMeta?.watchSummary ?? decodedResponse.summary,
                        transcript: decodedResponse.transcript,
                        phoneReport: decodedResponse.reportMeta?.phoneReport ?? decodedResponse.phoneReport,
                        reportMeta: decodedResponse.reportMeta,
                        previewSections: decodedResponse.previewSections
                    )
                }
                // Terminal completion is already delivered by remote APNs.
                // Scheduling another local handoff alert here produces a delayed
                // duplicate sound when Watch polling resumes.
                self.logger.info("Stored terminal summary for \(jobId); remote APNs owns user notification")
            }

            replyHandler(self.safeReply(resultObj))
        }
        task.resume()
    }

    private func fetchActiveJobs(replyHandler: @escaping ([String : Any]) -> Void) {
        let jobsURL = BackendConfig.url("/api/v1/jobs/active")
        var request = URLRequest(url: jobsURL)
        request.httpMethod = "GET"
        BackendConfig.applyAuth(&request)
        
        let task = BackendTransport.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                self.logger.error("Backend request failed: \(error.localizedDescription)")
                replyHandler(["error": "Backend unavailable"])
                return
            }
            guard let data = data, let jobsObj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                replyHandler(["error": "Failed to parse jobs response"])
                return
            }
            replyHandler(self.safeReply(jobsObj))
        }
        task.resume()
    }
    
    private func forwardToBackend(request: WatchCommandRequest, configurationGeneration: Int, replyHandler: @escaping (Data) -> Void) {
        var urlRequest = URLRequest(url: backendURL)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        BackendConfig.applyAuth(&urlRequest)
        
        do {
            urlRequest.httpBody = try JSONEncoder().encode(request)
        } catch {
            logger.error("Failed to encode backend request: \(error.localizedDescription)")
            replyWithError(message: "Failed to encode request", replyHandler: replyHandler)
            return
        }
        
        let task = BackendTransport.shared.dataTask(with: urlRequest) { [weak self] data, response, error in
            guard let self = self else { return }
            
            if let error = error {
                self.logger.error("Backend request failed: \(error.localizedDescription)")
                self.replyWithError(message: "Backend unavailable", replyHandler: replyHandler)
                return
            }
            
            guard let httpResponse = response as? HTTPURLResponse,
                  let responseData = data,
                  (200...299).contains(httpResponse.statusCode) else {
                self.logger.error("Backend returned non-200 response")
                self.replyWithError(message: "Backend error", replyHandler: replyHandler)
                return
            }
            
            if let decodedResponse = try? JSONDecoder().decode(WatchCommandResponse.self, from: responseData) {
                Task { @MainActor in
                    guard self.commandConfigurationGeneration == configurationGeneration else { return }
                    self.storeLatestContinuation(
                        jobId: decodedResponse.jobId,
                        summaryText: decodedResponse.reportMeta?.watchSummary ?? decodedResponse.summaryText,
                        transcript: decodedResponse.transcript,
                        phoneReport: decodedResponse.reportMeta?.phoneReport ?? decodedResponse.phoneReport,
                        reportMeta: decodedResponse.reportMeta,
                        previewSections: decodedResponse.previewSections
                    )
                }
                // APNs owns automatic terminal alerts, including an idempotent
                // command replay that returns an already completed result.
            }

            self.logger.info("Successfully received backend response, forwarding to Watch")
            replyHandler(responseData)
        }
        
        task.resume()
    }
    
    @MainActor
    private func continuationDetails(for url: URL) -> ContinuationDetails? {
        guard url.host == "job",
              url.pathComponents.count > 1 else {
            return latestContinuationDetails
        }

        let requestedJobId = url.pathComponents[1]
        guard requestedJobId == latestContinuationJobId else {
            return nil
        }
        return latestContinuationDetails
    }

    @MainActor
    private func storeLatestContinuation(
        jobId: String?,
        summaryText: String,
        transcript: String?,
        phoneReport: String?,
        reportMeta: ReportMeta?,
        previewSections: [PreviewSectionPayload]?
    ) {
        latestContinuationJobId = jobId
        latestContinuationDetails = ContinuationDetails(
            summaryText: reportMeta?.watchSummary ?? summaryText,
            transcript: transcript,
            phoneReport: reportMeta?.phoneReport ?? phoneReport,
            category: reportMeta?.category,
            nextAction: reportMeta?.nextAction,
            previewSections: previewSections
        )
    }

    private func replyWithError(message: String, replyHandler: @escaping (Data) -> Void) {
        // Construct an error response using the contract
        let errorResponse = WatchCommandResponse(
            status: "error",
            transcript: "",
            summaryText: message,
            ttsAudioData: nil,
            ttsFormat: nil,
            requiresPhoneHandoff: false,
            handoffUrl: nil,
            deepLink: nil,
            handoffReason: nil,
            jobId: nil,
            phoneReport: nil,
            reportMeta: nil,
            reportSections: nil,
            previewSections: nil,
            nextActions: nil
        )
        if let encoded = try? JSONEncoder().encode(errorResponse) {
            replyHandler(encoded)
        } else {
            replyHandler(Data())
        }
    }

    @discardableResult
    func forwardTerminalPushToWatch(_ userInfo: [AnyHashable: Any]) -> Bool {
        guard let jobId = userInfo["job_id"] as? String, !jobId.isEmpty,
              let status = userInfo["job_status"] as? String,
              status == "completed" || status == "failed" else {
            return false
        }

        var payload: [String: Any] = [
            "action": "terminal_job_result",
            "job_id": jobId,
            "status": status,
            "summary": userInfo["watch_summary"] as? String ?? "",
            "deep_link": userInfo["deep_link"] as? String ?? "",
            "requires_phone_handoff": userInfo["requires_phone_handoff"] as? Bool ?? false,
        ]
        if let outcome = userInfo["outcome"] as? String {
            payload["outcome"] = outcome
        }
        let session = WCSession.default
        if session.activationState != .activated {
            session.activate()
        }
        session.transferUserInfo(payload)
        do {
            try session.updateApplicationContext(payload)
        } catch {
            logger.warning("Could not update Watch terminal context: \(error.localizedDescription)")
        }
        logger.info("Forwarded terminal push for \(jobId) to Watch")
        return true
    }

    private func configureNotificationAuthorization() {
        notificationCenter.getNotificationSettings { settings in
            guard settings.authorizationStatus == .notDetermined else { return }

            self.notificationCenter.requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
                if let error {
                    self.logger.error("Notification authorization request failed: \(error.localizedDescription)")
                    return
                }

                self.logger.info("Notification authorization result: \(granted)")
            }
        }
    }

    private func scheduleHandoffNotificationIfNeeded(
        jobId: String,
        requiresPhoneHandoff: Bool,
        deepLinkValue: String?,
        title: String?,
        summaryText: String,
        handoffReason: String?,
        nextAction: String?,
        signatureSeed: String
    ) {
        guard requiresPhoneHandoff else { return }
        guard UIApplication.shared.applicationState != .active else { return }

        let resolvedDeepLinkValue = deepLinkValue ?? "ceviz://job/\(jobId)"
        guard let deepLink = URL(string: resolvedDeepLinkValue) else { return }

        let signature = [
            signatureSeed,
            summaryText,
            handoffReason ?? "",
            nextAction ?? "",
        ].joined(separator: "|")

        if lastNotificationSignature(for: jobId) == signature {
            logger.info("Skipping duplicate handoff nudge for job \(jobId)")
            return
        }

        notificationCenter.getNotificationSettings { settings in
            guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
                self.logger.info("Notification permission unavailable, skipping handoff nudge for job \(jobId)")
                return
            }

            let content = UNMutableNotificationContent()
            content.title = title ?? NSLocalizedString("Continue on iPhone", comment: "notification title")
            content.body = self.notificationBody(summaryText: summaryText, handoffReason: handoffReason)
            content.sound = UNNotificationSound(named: UNNotificationSoundName(rawValue: "ceviz-complete.caf"))
            content.userInfo = [
                "deep_link": deepLink.absoluteString,
                "job_id": jobId,
            ]

            let request = UNNotificationRequest(
                identifier: "\(self.handoffNotificationPrefix)\(jobId)",
                content: content,
                trigger: UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
            )

            self.notificationCenter.add(request) { error in
                if let error {
                    self.logger.error("Failed to schedule handoff nudge for job \(jobId): \(error.localizedDescription)")
                    return
                }

                self.storeNotificationSignature(signature, for: jobId)
                self.logger.info("Scheduled handoff nudge for job \(jobId)")
            }
        }
    }

    private func notificationBody(summaryText: String, handoffReason: String?) -> String {
        let summary = summaryText.trimmingCharacters(in: .whitespacesAndNewlines)
        let reason = (handoffReason ?? "")
            .replacingOccurrences(of: "_", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        if !summary.isEmpty && !reason.isEmpty {
            return "\(summary) • \(reason.capitalized)"
        }

        if !summary.isEmpty {
            return summary
        }

        if !reason.isEmpty {
            return reason.capitalized
        }

        return "The watch summary needs the phone for full context."
    }

    private func lastNotificationSignature(for jobId: String) -> String? {
        let signatures = UserDefaults.standard.dictionary(forKey: handoffNudgeDefaultsKey) as? [String: String]
        return signatures?[jobId]
    }

    private func storeNotificationSignature(_ signature: String, for jobId: String) {
        var signatures = UserDefaults.standard.dictionary(forKey: handoffNudgeDefaultsKey) as? [String: String] ?? [:]
        signatures[jobId] = signature
        UserDefaults.standard.set(signatures, forKey: handoffNudgeDefaultsKey)
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        let identifier = notification.request.identifier
        if identifier.hasPrefix(handoffNotificationPrefix) {
            completionHandler([.banner, .sound])
            return
        }

        // Keep remote terminal notifications visible while the companion app
        // is foregrounded. Empty presentation options silently consume APNs.
        let userInfo = notification.request.content.userInfo
        _ = forwardTerminalPushToWatch(userInfo)
        if userInfo["job_id"] != nil || userInfo["deep_link"] != nil {
            completionHandler([.banner, .list, .sound])
            return
        }

        completionHandler([])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        defer { completionHandler() }

        let userInfo = response.notification.request.content.userInfo
        guard let deepLinkValue = userInfo["deep_link"] as? String,
              let url = URL(string: deepLinkValue) else {
            return
        }

        Task { @MainActor in
            let details = self.continuationDetails(for: url)
            _ = AppRouter.shared.open(url: url, source: .deepLink, presentImmediately: true, details: details)
        }
    }
}
