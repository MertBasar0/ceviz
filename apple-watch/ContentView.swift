import SwiftUI
import WatchKit

struct ContentView: View {
    @StateObject private var sessionManager = WatchSessionManager.shared
    @StateObject private var recorder = AudioRecorderManager()
    @StateObject private var player = AudioPlayerManager()
    @Environment(\.scenePhase) private var scenePhase
    @State private var selectedTab = 0
    @State private var preparingCapture = false
    @State private var captureReady = false
    @State private var recordingSeconds: TimeInterval = 0
    @State private var recordingTimer: Timer?
    @State private var recordingWasCancelled = false
    @State private var requestedResult: RequestedResult?

    private struct RequestedResult {
        let state: CVZJobState
        let text: String
        let url: String?
        let jobID: String?
    }

    private var displayedState: CVZJobState? { requestedResult?.state ?? sessionManager.resultState }
    private var displayedText: String { requestedResult?.text ?? sessionManager.responseText }
    private var displayedURL: String? {
        if let requestedResult { return requestedResult.url }
        return sessionManager.handoffUrl
    }
    private var displayedJobID: String? {
        if let requestedResult { return requestedResult.jobID }
        return sessionManager.handoffJobId
    }
    private var handoffRequested: Bool {
        displayedJobID == sessionManager.handoffJobId &&
            (sessionManager.handoffState == .pendingOnPhone || sessionManager.handoffState == .openedOnPhone)
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            voiceTab.tag(0).tabItem { Label("Voice", systemImage: "mic") }
            NavigationView { JobsListView(sessionManager: sessionManager) }
                .tag(1).tabItem { Label("Jobs", systemImage: "list.bullet") }
        }
        .background(CVZ.bg)
        .onAppear {
            sessionManager.audioPlayerManager = player
            sessionManager.resumeResultPollingIfNeeded()
            sessionManager.processQueue()
        }
        .onOpenURL { url in
            guard url.scheme == "ceviz-watch", url.host == "capture" else { return }
            selectedTab = 0
            requestedResult = nil
            captureReady = !recorder.isRecording && !preparingCapture
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active {
                sessionManager.resumeResultPollingIfNeeded()
                sessionManager.processQueue()
            }
            if phase == .background && preparingCapture { cancelRecording() }
        }
        .onChange(of: selectedTab) { tab in
            if tab != 0 && (recorder.isRecording || preparingCapture) { cancelRecording() }
        }
        .onChange(of: recorder.isRecording) { recording in
            if !recording && recordingTimer != nil { stop() }
        }
        .onChange(of: sessionManager.resultState) { state in
            if !recorder.isRecording && !preparingCapture,
               state?.isReportedResult == true || state == .failed {
                captureReady = false
            }
        }
        .onReceive(sessionManager.$resultPresentationRequest.dropFirst()) { _ in
            guard let state = sessionManager.resultState else { return }
            // Keep the explicitly opened result readable while another submission
            // finishes in the background; this does not change delivery ownership.
            requestedResult = RequestedResult(state: state, text: sessionManager.responseText,
                                              url: sessionManager.handoffUrl, jobID: sessionManager.handoffJobId)
            if recorder.isRecording || preparingCapture { cancelRecording(resumeQueue: false) }
            selectedTab = 0
            captureReady = false
            recordingWasCancelled = false
        }
    }

    private var voiceTab: some View {
        VStack(spacing: 6) {
            HStack {
                Label(LocalizedStringKey(sessionManager.isReachable ? "Phone connected" : "Phone offline"), systemImage: "iphone")
                    .font(.caption2)
                    .foregroundColor(sessionManager.isReachable ? CVZ.accent : CVZ.textSub)
                    .lineLimit(1)
                Spacer(minLength: 2)
                Button { selectedTab = 1 } label: {
                    Image(systemName: "list.bullet").frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                    .buttonStyle(.plain).accessibilityLabel(Text("Jobs"))
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if recorder.isRecording {
                        recordingArea
                    } else if requestedResult != nil {
                        resultCard
                    } else if preparingCapture || sessionManager.isSending {
                        ProgressView(LocalizedStringKey(preparingCapture ? "Preparing microphone…" : "Sending request…"))
                            .font(.caption).tint(CVZ.accent)
                    } else if captureReady || (sessionManager.responseText.isEmpty && sessionManager.resultState == nil) {
                        Text("Ready to listen").font(.headline).foregroundColor(CVZ.text)
                        Text("Up to 15 seconds")
                            .font(.caption).foregroundColor(CVZ.textSub)
                    } else {
                        resultCard
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            micButton
            TimelineView(.periodic(from: .now, by: 10)) { context in
                if recordingWasCancelled {
                    Text("Recording discarded").font(.caption2).foregroundColor(CVZ.textSub)
                } else if !recorder.isRecording && !preparingCapture && !sessionManager.isSending,
                          let last = sessionManager.lastResultAt,
                          context.date.timeIntervalSince(last) < WatchSessionManager.continuationWindow {
                    Text("↩ follow-up").font(.caption2).foregroundColor(CVZ.accent)
                }
            }
        }
        .padding(.horizontal, 4)
        .background(CVZ.bg.ignoresSafeArea())
    }

    private var resultCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let state = displayedState {
                CVZStatusChip(state: state)
                if state.isReportedResult {
                    Text("Agent-reported result").font(.caption2).foregroundColor(CVZ.textSub)
                }
            }
            Text(displayedText)
                .font(.body).foregroundColor(CVZ.text).lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            if displayedState == .running || displayedState == .queued {
                Text("You can start another request. Earlier jobs stay in Jobs.")
                    .font(.caption2).foregroundColor(CVZ.textSub)
            } else if displayedState?.needsAttention == true {
                Text("Review the next step on iPhone.")
                    .font(.caption).foregroundColor(CVZ.warn)
            }
            if let url = displayedURL {
                Button { sessionManager.openHandoff(url: url, jobId: displayedJobID) } label: {
                    Label(LocalizedStringKey(handoffRequested ? "SENT TO IPHONE" : "Open on iPhone"), systemImage: "iphone.and.arrow.forward")
                        .font(.caption.weight(.semibold))
                }
                .tint(CVZ.accent).disabled(handoffRequested)
            }
        }
    }

    private var recordingArea: some View {
        VStack(spacing: 6) {
            Label("● REC", systemImage: "mic.fill").font(.caption).foregroundColor(CVZ.err)
            Text(String(format: NSLocalizedString("%d seconds left", comment: "capture countdown"), max(0, Int(ceil(AudioRecorderManager.maximumDuration - recordingSeconds)))))
                .font(.title3.weight(.semibold)).monospacedDigit().foregroundColor(CVZ.text)
            ProgressView(value: recordingSeconds, total: AudioRecorderManager.maximumDuration).tint(CVZ.err)
            Text("Tap send when you finish.").font(.caption2).foregroundColor(CVZ.textSub)
        }
        .frame(maxWidth: .infinity)
    }

    private var micButton: some View {
        HStack(spacing: 18) {
            if recorder.isRecording || preparingCapture {
                Button(action: { cancelRecording() }) {
                    Image(systemName: "xmark").font(.title3).foregroundColor(CVZ.err)
                        .frame(width: 44, height: 44).background(CVZ.errBg, in: Circle())
                }
                .buttonStyle(.plain).accessibilityLabel(Text("Discard recording"))
            }
            Button { recorder.isRecording ? stop() : start() } label: {
                Image(systemName: recorder.isRecording ? "arrow.up" : "mic")
                    .font(.title2.weight(.semibold)).foregroundColor(CVZ.accent)
                    .frame(width: 54, height: 54).background(CVZ.panel, in: Circle())
                    .overlay(Circle().stroke(CVZ.accent, lineWidth: 1.5))
            }
            .buttonStyle(.plain)
            .disabled(sessionManager.isSending || preparingCapture)
            .accessibilityLabel(Text(LocalizedStringKey(recorder.isRecording ? "Send recording" : "Start recording")))
        }
    }

    private func start() {
        guard !preparingCapture && !sessionManager.isSending && !recorder.isRecording else { return }
        recordingWasCancelled = false
        requestedResult = nil
        captureReady = false
        preparingCapture = true
        sessionManager.isCapturing = true
        player.audioPlayer?.stop()
        recorder.startRecording { started in
            preparingCapture = false
            guard started else {
                sessionManager.isCapturing = false
                sessionManager.stopExtendedSession()
                sessionManager.showCaptureError(recorder.lastError ?? NSLocalizedString("Could not capture audio", comment: ""))
                return
            }
            sessionManager.startExtendedSession()
            WKInterfaceDevice.current().play(.start)
            recordingSeconds = 0
            recordingTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { _ in
                recordingSeconds = recorder.elapsedSeconds
                if recordingSeconds >= AudioRecorderManager.maximumDuration { stop() }
            }
        }
    }

    private func stop() {
        recordingTimer?.invalidate()
        recordingTimer = nil
        let audio = recorder.stopRecording()
        sessionManager.isCapturing = false
        if let audio {
            WKInterfaceDevice.current().play(.stop)
            sessionManager.sendAudioCommand(audioBase64: audio)
        } else {
            sessionManager.stopExtendedSession()
            sessionManager.showCaptureError(recorder.lastError ?? NSLocalizedString("Could not capture audio", comment: ""))
        }
    }

    private func cancelRecording(resumeQueue: Bool = true) {
        recordingTimer?.invalidate()
        recordingTimer = nil
        preparingCapture = false
        recorder.cancelRecording()
        sessionManager.isCapturing = false
        sessionManager.stopExtendedSession()
        recordingWasCancelled = true
        WKInterfaceDevice.current().play(.click)
        if resumeQueue { sessionManager.processQueue() }
    }
}
