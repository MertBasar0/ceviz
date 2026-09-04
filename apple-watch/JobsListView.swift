import SwiftUI

struct JobsListView: View {
    @ObservedObject var sessionManager: WatchSessionManager

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("JOBS")
                        .font(.caption.weight(.semibold))
                        .tracking(1)
                        .foregroundColor(CVZ.accent)
                    Spacer()
                }
                .padding(.bottom, 4)

                if sessionManager.activeJobs.isEmpty {
                    Text("No active jobs")
                        .font(.caption)
                        .foregroundColor(CVZ.textDim)
                        .padding(.top, 12)
                } else {
                    ForEach(sessionManager.activeJobs) { job in
                        NavigationLink(destination: JobDetailView(job: job, sessionManager: sessionManager)) {
                            jobRow(job)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(.horizontal, 2)
        }
        .background(CVZ.bg.ignoresSafeArea())
        .onAppear {
            sessionManager.fetchJobs()
        }
    }

    private func jobRow(_ job: ActiveJob) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Rectangle().fill(CVZ.lineSoft).frame(height: 1)

            Text(job.name)
                .font(.headline)
                .foregroundColor(CVZ.text)
                .lineLimit(2)
                .multilineTextAlignment(.leading)

            HStack {
                CVZStatusChip(state: job.presentationState)
                Spacer()
                Text(String(format: "%02d:%02d", job.elapsedSeconds / 60, job.elapsedSeconds % 60))
                    .font(.caption2).monospacedDigit()
                    .foregroundColor(CVZ.textDim)
            }
        }
        .padding(.vertical, 5)
        .contentShape(Rectangle())
    }
}
