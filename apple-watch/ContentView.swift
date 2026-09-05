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
    @State private var recordingWasCancelled = false
    @State private var requestedResult: RequestedResult?

    private struct RequestedResult {
        let state: CVZJobState
        let text: String
        let url: String?
        let jobID: String?
    }

    private enum VoicePhase: Equatable {
        case idle, preparing, recording, finalizing, sending, result
    }

    private var voicePhase: VoicePhase {
        if recorder.isRecording { return .recording }
        if preparingCapture { return .preparing }
        if sessionManager.isCapturing { return .finalizing }
        if requestedResult != nil { return .result }
        if sessionManager.isSending { return .sending }
        if captureReady || (sessionManager.responseText.isEmpty && sessionManager.resultState == nil) { return .idle }
        return .result
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
            // The recorder owns finalization; both manual and timed stops submit here once.
            recorder.onRecordingFinished = { [weak manager = sessionManager] result in
                guard let manager else { return }
                manager.isCapturing = false
                switch result {
                case .success(let audio):
                    WKInterfaceDevice.current().play(.stop)
                    manager.sendAudioCommand(audioBase64: audio)
                case .failure(let error):
                    manager.stopExtendedSession()
                    manager.showCaptureError(error.localizedDescription)
                }
            }
            sessionManager.audioPlayerManager = player
            sessionManager.resumeResultPollingIfNeeded()
            sessionManager.processQueue()
        }
        .onOpenURL { url in
            guard let route = WatchCaptureRoute(url: url, isRecording: recorder.isRecording,
                                                preparingCapture: sessionManager.isCapturing) else { return }
            selectedTab = 0
            requestedResult = nil
            captureReady = route == .ready
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active {
                sessionManager.resumeResultPollingIfNeeded()
                sessionManager.processQueue()
            }
            if phase == .background && preparingCapture { cancelRecording() }
        }
        .onChange(of: selectedTab) { tab in
            if tab != 0 && sessionManager.isCapturing { cancelRecording() }
        }
        .onChange(of: sessionManager.resultState) { state in
            if !sessionManager.isCapturing,
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
            if sessionManager.isCapturing { cancelRecording(resumeQueue: false) }
            selectedTab = 0
            captureReady = false
            recordingWasCancelled = false
        }
    }

    private var voiceTab: some View {
        VStack(spacing: 6) {
            Group {
                if voicePhase == .recording {
                    recordingArea
                } else {
                    TimelineView(.periodic(from: .now, by: 10)) { context in
                        let content = VStack(alignment: .leading, spacing: 4) {
                            switch voicePhase {
                            case .idle:
                                Text(LocalizedStringKey(recordingWasCancelled ? "Recording discarded" : "Ready to listen"))
                                    .font(.headline)
                                    .accessibilityIdentifier("capture.ready")
                                Text("Up to 15 s").font(.body)
                                    .accessibilityLabel(Text("Up to 15 seconds"))
                                    .accessibilityIdentifier("capture.durationLimit")
                                if !recordingWasCancelled {
                                    followUpCaption(at: context.date)
                                }
                                if !sessionManager.isReachable {
                                    Label("Phone offline", systemImage: "iphone").font(.caption)
                                        .foregroundColor(CVZ.textSub)
                                }
                            case .preparing:
                                ProgressView("Preparing microphone…").font(.body).tint(CVZ.accent)
                            case .finalizing:
                                ProgressView("Finishing recording…").font(.body).tint(CVZ.accent)
                            case .sending:
                                ProgressView("Sending request…").font(.body).tint(CVZ.accent)
                            case .result:
                                resultCard(at: context.date)
                            case .recording:
                                EmptyView()
                            }
                        }
                        .foregroundColor(CVZ.text)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        if voicePhase == .idle {
                            // Short ready feedback fits without Watch ScrollView's
                            // extra margins; longer follow-up content remains scrollable.
                            ViewThatFits(in: .vertical) {
                                content
                                ScrollView { content }
                            }
                            .frame(maxHeight: .infinity, alignment: .topLeading)
                        } else {
                            ScrollView { content.fixedSize(horizontal: false, vertical: true) }
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            // A sibling action row owns its space; text cannot flow behind it.
            captureActions
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, 4)
        .background(CVZ.bg.ignoresSafeArea())
    }

    private func resultCard(at date: Date) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let state = displayedState {
                Label(NSLocalizedString(state.titleKey, comment: "job state"), systemImage: state.symbolName)
                    .font(.headline).foregroundColor(CVZ.statusColor(state))
                    .accessibilityIdentifier("capture.result.\(state)")
                if state.isReportedResult {
                    Text("Agent-reported result").font(.caption).foregroundColor(CVZ.textSub)
                }
            }
            Text(displayedText)
                .font(.body).foregroundColor(CVZ.text)
                .fixedSize(horizontal: false, vertical: true)
            if displayedState == .running || displayedState == .queued {
                Text("You can start another request. Earlier jobs stay in Jobs.")
                    .font(.body).foregroundColor(CVZ.textSub)
            } else if displayedState?.needsAttention == true {
                Text("Review the next step on iPhone.")
                    .font(.body).foregroundColor(CVZ.warn)
            }
            followUpCaption(at: date)
        }
    }

    @ViewBuilder
    private func followUpCaption(at date: Date) -> some View {
        // An absent/expired caption must not leave a TimelineView row in the stack.
        if !sessionManager.isSending, let last = sessionManager.lastResultAt,
           date.timeIntervalSince(last) < WatchSessionManager.continuationWindow {
            Text("↩ follow-up").font(.caption).foregroundColor(CVZ.accent)
        }
    }

    private var recordingArea: some View {
        TimelineView(.periodic(from: .now, by: 0.25)) { _ in
            let remaining = max(0, Int(ceil(AudioRecorderManager.maximumDuration - recorder.elapsedSeconds)))
            VStack(spacing: 4) {
                Text("Recording").font(.body.weight(.semibold)).foregroundColor(CVZ.text)
                    .accessibilityIdentifier("capture.recording")
                Text(String(format: NSLocalizedString("%d s", comment: "short capture countdown"), remaining))
                    .font(.title2.weight(.bold)).monospacedDigit().foregroundColor(CVZ.text)
                    .accessibilityLabel(Text(String(format: NSLocalizedString("%d seconds left", comment: "capture countdown"), remaining)))
                    .accessibilityIdentifier("capture.countdown")
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var captureActions: some View {
        HStack(spacing: 12) {
            if sessionManager.isCapturing {
                Button(action: { cancelRecording() }) {
                    Text("Delete").font(.body.weight(.semibold)).foregroundColor(CVZ.err)
                        .frame(maxWidth: .infinity, minHeight: 54)
                        .background(CVZ.errBg, in: RoundedRectangle(cornerRadius: 16))
                }
                .buttonStyle(.plain).accessibilityLabel(Text("Discard recording"))
                .accessibilityIdentifier("capture.cancel")
            } else if voicePhase == .result, let url = displayedURL {
                Button { sessionManager.openHandoff(url: url, jobId: displayedJobID) } label: {
                    Image(systemName: "iphone.and.arrow.forward").font(.title3.weight(.semibold))
                        .foregroundColor(CVZ.accent).frame(maxWidth: .infinity, minHeight: 54)
                        .background(CVZ.panel, in: RoundedRectangle(cornerRadius: 16))
                }
                .buttonStyle(.plain).disabled(handoffRequested)
                .accessibilityLabel(Text(LocalizedStringKey(handoffRequested ? "SENT TO IPHONE" : "Open on iPhone")))
                .accessibilityIdentifier("capture.openOnPhone")
            }
            Button {
                if recorder.isRecording { recorder.stopRecording() } else { start() }
            } label: {
                Group {
                    if sessionManager.isCapturing {
                        Text("Send").font(.body.weight(.semibold))
                    } else {
                        Image(systemName: "mic").font(.title2.weight(.semibold))
                    }
                }
                    .foregroundColor(CVZ.accent)
                    .frame(maxWidth: .infinity, minHeight: 54)
                    .background(CVZ.panel, in: RoundedRectangle(cornerRadius: 16))
                    .overlay(RoundedRectangle(cornerRadius: 16).stroke(CVZ.accent, lineWidth: 1.5))
            }
            .buttonStyle(.plain)
            .disabled(!recorder.isRecording && (sessionManager.isSending || sessionManager.isCapturing))
            .accessibilityLabel(Text(LocalizedStringKey(sessionManager.isCapturing ? "Send recording" : "Start recording")))
            .accessibilityIdentifier("capture.primary")
        }
        .background(CVZ.bg)
    }

    private func start() {
        guard !sessionManager.isCapturing && !sessionManager.isSending else { return }
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
        }
    }

    private func cancelRecording(resumeQueue: Bool = true) {
        preparingCapture = false
        recorder.cancelRecording()
        sessionManager.isCapturing = false
        sessionManager.stopExtendedSession()
        recordingWasCancelled = true
        captureReady = true
        WKInterfaceDevice.current().play(.click)
        if resumeQueue { sessionManager.processQueue() }
    }
}
