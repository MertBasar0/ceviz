import SwiftUI

struct JobDetailView: View {
    let job: ActiveJob
    @ObservedObject var sessionManager: WatchSessionManager
    @ObservedObject private var speaker = ResultSpeaker.shared

    private var currentJob: ActiveJob {
        sessionManager.activeJobs.first { $0.id == job.id } ?? job
    }

    /// Answers this job's question offers, unless this Watch already answered it.
    private var choices: [NextActionPayload] {
        guard currentJob.presentationState == .needsInput,
              !sessionManager.answeredChoiceJobIDs.contains(job.id) else { return [] }
        return (currentJob.nextActions ?? []).filter { $0.kind == "choice" }
    }

    private var handoffRequested: Bool {
        sessionManager.handoffJobId == job.id &&
            (sessionManager.handoffState == .pendingOnPhone || sessionManager.handoffState == .openedOnPhone)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text(currentJob.name).font(.headline).foregroundColor(CVZ.text)
                CVZStatusChip(state: currentJob.presentationState)
                if currentJob.presentationState.isReportedResult {
                    Text("Agent-reported result").font(.caption2).foregroundColor(CVZ.textSub)
                }
                Text(currentJob.summaryText).font(.body).foregroundColor(CVZ.text)
                    .fixedSize(horizontal: false, vertical: true)
                if !currentJob.summaryText.isEmpty {
                    Button {
                        if speaker.isSpeaking { speaker.stop() } else {
                            speaker.speak(currentJob.summaryText, choices: choices.map(\.label))
                        }
                    } label: {
                        Label(LocalizedStringKey(speaker.isSpeaking ? "Stop" : "Listen"),
                              systemImage: speaker.isSpeaking ? "stop.fill" : "speaker.wave.2")
                            .font(.caption.weight(.semibold))
                    }
                    .tint(CVZ.accent)
                    .accessibilityIdentifier("job.listen")
                }
                if !choices.isEmpty {
                    ChoiceButtons(choices: choices, jobID: job.id, identifierPrefix: "job", sessionManager: sessionManager)
                } else if sessionManager.answeredChoiceJobIDs.contains(job.id) {
                    Text("Answer sent. Its result appears on the Voice tab.").font(.caption).foregroundColor(CVZ.textSub)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let nextAction = currentJob.reportMeta?.nextAction, !nextAction.isEmpty {
                    Text("Next step").font(.caption2.weight(.semibold)).foregroundColor(CVZ.accent)
                    Text(nextAction).font(.caption).foregroundColor(CVZ.textSub).lineLimit(3)
                } else if currentJob.presentationState.needsAttention, choices.isEmpty {
                    Text("Review the next step on iPhone.").font(.caption).foregroundColor(CVZ.warn)
                }
                Button {
                    sessionManager.openHandoff(url: currentJob.deepLink ?? "ceviz://job/\(job.id)", jobId: job.id)
                } label: {
                    Label(LocalizedStringKey(handoffRequested ? "SENT TO IPHONE" : "Open on iPhone"), systemImage: "iphone.and.arrow.forward")
                        .font(.caption.weight(.semibold))
                }
                .tint(CVZ.accent).disabled(handoffRequested)
                Button { sessionManager.fetchJobs() } label: {
                    Label("Refresh", systemImage: "arrow.clockwise").font(.caption)
                }
                .disabled(sessionManager.jobsLoading)
                if sessionManager.jobsLoading {
                    ProgressView("Refreshing jobs…").font(.caption).tint(CVZ.accent)
                }
                if let error = sessionManager.jobsErrorKey {
                    Text(LocalizedStringKey(error)).font(.caption).foregroundColor(CVZ.warn)
                }
                if !sessionManager.isReachable {
                    Text("Phone offline — showing the last received result.")
                        .font(.caption2).foregroundColor(CVZ.textSub)
                } else if sessionManager.jobsErrorKey != nil {
                    Text("Showing the last received result.").font(.caption2).foregroundColor(CVZ.textSub)
                }
            }
            .padding(.horizontal, 4)
        }
        .background(CVZ.bg)
        .navigationTitle("Details")
        .onAppear { sessionManager.fetchJobs() }
        .onDisappear { speaker.stop() }
    }
}
