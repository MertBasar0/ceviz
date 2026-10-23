import SwiftUI

/// Answer buttons for a result that asks the user to choose. A tap sends only the answer's id.
struct ChoiceButtons: View {
    let choices: [NextActionPayload]
    let jobID: String
    let identifierPrefix: String
    @ObservedObject var sessionManager: WatchSessionManager

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Choose an answer").font(.caption).foregroundColor(CVZ.accent)
            ForEach(Array(choices.enumerated()), id: \.element.id) { index, choice in
                Button { sessionManager.chooseOption(choice, for: jobID) } label: {
                    Text(choice.label).font(.body).multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                }
                .buttonStyle(.bordered).tint(CVZ.accent)
                .disabled(sessionManager.choiceSendingJobID != nil)
                .accessibilityIdentifier("\(identifierPrefix).choice.\(index + 1)")
            }
            if sessionManager.choiceSendingJobID == jobID {
                ProgressView().tint(CVZ.accent)
            }
            if let error = sessionManager.choiceErrorKey {
                Text(LocalizedStringKey(error)).font(.caption).foregroundColor(CVZ.warn)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
