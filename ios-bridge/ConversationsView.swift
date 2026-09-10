import SwiftUI

struct ConversationsView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var sessions: [OpenClawConversation] = []
    @State private var agents: [OpenClawConversationAgent] = []
    @State private var agentId = ""
    @State private var search = ""
    @State private var older = false
    @State private var nextOffset: Int?
    @State private var loading = false
    @State private var error: String?
    @State private var revision = 0
    @State private var selectedSession: OpenClawConversation?

    private var selection: String { "\(agentId)|\(older)|\(revision)|\(search.trimmingCharacters(in: .whitespacesAndNewlines))" }

    var body: some View {
        List {
            Section {
                Text("Continue an OpenClaw conversation here. Your watch keeps its current behavior.")
                    .font(.subheadline).foregroundColor(CVZ.textSub)
                Picker("Assistant", selection: $agentId) {
                    Text("All assistants").tag("")
                    ForEach(agents) { agent in Text(agent.name).tag(agent.id) }
                }
                .accessibilityIdentifier("conversations.agent")
                Toggle("Include older conversations", isOn: $older)
                    .accessibilityIdentifier("conversations.older")
            }
            .listRowBackground(CVZ.panel)

            if DemoMode.isActive {
                Text("Pair with your Ceviz service to see your OpenClaw conversations.")
                    .foregroundColor(CVZ.textSub).listRowBackground(CVZ.panel)
            } else {
                if let error { errorRow(error) }
                if loading && sessions.isEmpty {
                    ProgressView("Loading conversations…").listRowBackground(CVZ.panel)
                } else if sessions.isEmpty && error == nil {
                    Text(LocalizedStringKey(search.isEmpty ? "No conversations in this view. Try another assistant or include older conversations." : "No matching conversations. Try another assistant or include older conversations."))
                        .foregroundColor(CVZ.textSub).listRowBackground(CVZ.panel)
                }
                ForEach(sessions) { session in
                    Button { selectedSession = session } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(session.title).font(.headline).foregroundColor(CVZ.text)
                            if let preview = session.preview, !preview.isEmpty {
                                Text(preview).font(.subheadline).foregroundColor(CVZ.textSub).lineLimit(2)
                            }
                            HStack {
                                Text(session.agentId)
                                if session.archived { Text("Archived") }
                                if session.isRunning { Text("Working") }
                                Spacer()
                                if let date = session.updatedAt { Text(date, style: .relative) }
                            }
                            .font(.caption).foregroundColor(CVZ.textSub)
                        }
                        .padding(.vertical, 4)
                    }
                    .listRowBackground(CVZ.panel)
                    .accessibilityIdentifier("conversations.row.\(session.sessionKey)")
                }
                if let offset = nextOffset {
                    Button("Load more conversations") { Task { await load(offset: offset) } }
                        .disabled(loading).listRowBackground(CVZ.panel)
                        .accessibilityIdentifier("conversations.more")
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(CVZ.bg)
        .tint(CVZ.accent)
        .foregroundColor(CVZ.text)
        .navigationTitle("Conversations")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .searchable(text: $search, prompt: "Search conversations")
        .refreshable { revision += 1 }
        .task(id: selection) {
            guard !DemoMode.isActive else { return }
            loading = true
            sessions = []
            nextOffset = nil
            if !search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                do { try await Task.sleep(nanoseconds: 300_000_000) } catch { return }
            }
            await load()
        }
        .navigationDestination(isPresented: Binding(
            get: { selectedSession != nil }, set: { if !$0 { selectedSession = nil } }
        )) {
            if let selectedSession { ConversationDetailView(selected: selectedSession).id(selectedSession.sessionKey) }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active { revision += 1 }
        }
        .onReceive(NotificationCenter.default.publisher(for: BackendConfig.connectionDidChange)) { _ in
            sessions = []
            agents = []
            selectedSession = nil
            agentId = ""
            revision += 1
        }
    }

    private func errorRow(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(message).font(.subheadline).foregroundColor(CVZ.warn)
                .accessibilityIdentifier("conversation.error")
            Button("Try again") { revision += 1 }
        }
        .listRowBackground(CVZ.panel)
    }

    @MainActor
    private func load(offset: Int = 0) async {
        guard !DemoMode.isActive, !Task.isCancelled else { return }
        let requestedSelection = selection
        let requestedAgent = agentId
        let requestedOlder = older
        let requestedSearch = search.trimmingCharacters(in: .whitespacesAndNewlines)
        loading = true
        error = nil
        if offset == 0 { sessions = []; nextOffset = nil }
        do {
            var query = [URLQueryItem(name: "older", value: String(requestedOlder)), URLQueryItem(name: "offset", value: String(offset))]
            if !requestedAgent.isEmpty { query.append(URLQueryItem(name: "agent_id", value: requestedAgent)) }
            if !requestedSearch.isEmpty { query.append(URLQueryItem(name: "search", value: requestedSearch)) }
            let request = try ConversationClient.request("", query: query)
            let response = try await ConversationClient.load(request, as: OpenClawConversationsResponse.self)
            guard !Task.isCancelled, requestedSelection == selection else { return }
            // Keep the service's ordering. A changing catalog may overlap pages.
            let known = Set(sessions.map(\.id))
            sessions.append(contentsOf: response.sessions.filter { !known.contains($0.id) })
            agents = response.agents
            nextOffset = response.hasMore ? response.nextOffset : nil
        } catch {
            guard !Task.isCancelled, requestedSelection == selection else { return }
            self.error = error.localizedDescription
        }
        if requestedSelection == selection { loading = false }
    }
}

private struct ConversationDetailView: View {
    let selected: OpenClawConversation
    @EnvironmentObject private var conversationStore: ConversationSessionStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @State private var history: OpenClawConversationHistory?
    @State private var messages: [OpenClawConversationMessage] = []
    @State private var nextOffset: Int?
    @State private var loading = false
    @State private var error: String?
    @State private var historyGeneration = 0
    @State private var showingEarlierMessages = false
    @State private var shouldScrollToLatest = true
    @State private var latestScrollRevision = 0
    @State private var reviewingDelivery: (delivery: ConversationDelivery, scope: ConversationSessionScope)?

    private var scope: ConversationSessionScope { conversationStore.scope(for: selected.sessionKey) }
    private var sessionState: ConversationSessionState { conversationStore.state(for: scope) }
    private var draft: String { sessionState.draft }
    private var submission: ConversationSubmission { sessionState.submission }
    private var submissionError: String? { sessionState.error }
    private var draftBinding: Binding<String> {
        Binding(get: { draft }, set: { conversationStore.updateDraft($0, in: scope) })
    }
    private var target: OpenClawConversation { history?.session ?? selected }
    private var canSend: Bool {
        history?.session.sessionKey == selected.sessionKey && history?.session.sessionId != nil &&
            target.canSend && !target.archived && error == nil && conversationStore.storageError == nil &&
            !submission.preventsNewMessage &&
            !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(spacing: 0) {
            targetStrip
            ScrollViewReader { scroll in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        if let offset = nextOffset {
                            Button("Load earlier messages") { Task { await loadHistory(offset: offset) } }
                                .disabled(loading)
                                .accessibilityIdentifier("conversation.earlier")
                        }
                        if loading && history == nil { ProgressView("Loading conversation…") }
                        if let error {
                            Text(error).font(.subheadline).foregroundColor(CVZ.warn)
                                .accessibilityIdentifier("conversation.error")
                            Button("Refresh conversation") { Task { await loadHistory() } }.disabled(loading)
                        }
                        if history != nil && messages.isEmpty {
                            Text("No readable messages yet.").foregroundColor(CVZ.textSub)
                        }
                        ForEach(messages) { message in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(LocalizedStringKey(message.role == "user" ? "You" : "Assistant"))
                                        .font(.caption.weight(.semibold))
                                    Spacer()
                                    if let date = message.timestamp { Text(date, style: .time).font(.caption) }
                                }
                                .foregroundColor(message.role == "user" ? CVZ.accent : CVZ.textSub)
                                if !message.text.isEmpty {
                                    Text(message.text).font(.body).textSelection(.enabled)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                if message.hasOtherContent {
                                    Text("Attachments or other content are available in OpenClaw.")
                                        .font(.caption).foregroundColor(CVZ.textSub)
                                }
                            }
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(CVZ.panel, in: RoundedRectangle(cornerRadius: 8))
                        }
                        Color.clear.frame(height: 1).id("conversation.latest")
                    }
                    .padding(16)
                }
                .refreshable { await loadHistory() }
                .onChange(of: latestScrollRevision) { _ in
                    scroll.scrollTo("conversation.latest", anchor: .bottom)
                }
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .background(CVZ.bg)
        .foregroundColor(CVZ.text)
        .tint(CVZ.accent)
        .navigationTitle("Conversation")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(submission.isSending)
        .toolbar(.visible, for: .navigationBar)
        .alert("Start a new message after reviewing?", isPresented: Binding(
            get: { reviewingDelivery != nil }, set: { if !$0 { reviewingDelivery = nil } }
        ), presenting: reviewingDelivery) { review in
            Button("I reviewed it — start a new message") {
                conversationStore.finishReview(review.delivery, in: review.scope)
            }
            Button("Cancel", role: .cancel) { }
        } message: { _ in
            Text("The earlier message may still run. This does not resend or cancel it. Review the conversation before starting a new message.")
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            if history == nil || !showingEarlierMessages { await loadHistory() }
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds: 5_000_000_000) } catch { return }
                await checkRun()
                // Reading older history must not be interrupted by a polling reset.
                if !showingEarlierMessages || shouldScrollToLatest { await loadHistory() }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: BackendConfig.connectionDidChange)) { _ in
            historyGeneration += 1
            history = nil
            messages = []
            dismiss()
        }
    }

    private var targetStrip: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("THIS CONVERSATION").font(.caption.weight(.semibold)).foregroundColor(CVZ.accent)
            Text(target.title).font(.headline).fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("conversation.target")
            Text(target.agentId).font(.caption).foregroundColor(CVZ.textSub)
            if let history, !history.activeRunIds.isEmpty || history.pendingCount > 0 || target.isRunning {
                Text("This conversation is busy. Your message will wait its turn.")
                    .font(.caption).foregroundColor(CVZ.warn)
                    .accessibilityIdentifier("conversation.busy")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(CVZ.panel)
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let storageError = conversationStore.storageError {
                Text(storageError).font(.caption).foregroundColor(CVZ.warn)
                    .accessibilityIdentifier("conversation.storageError")
            }
            if let submissionError {
                Text(submissionError).font(.caption).foregroundColor(CVZ.warn)
                    .accessibilityIdentifier("conversation.submissionError")
            }
            if target.archived {
                Text("Archived conversation — read only.").font(.subheadline).foregroundColor(CVZ.textSub)
            } else if history != nil && !target.canSend {
                Text("This conversation is read only. Its current message target could not be verified.")
                    .font(.subheadline).foregroundColor(CVZ.warn)
            } else {
                if case let .tracking(delivery, run) = submission {
                    Text(LocalizedStringKey(run?.statusKey ?? "Delivery is not confirmed. Check the conversation before sending again."))
                        .font(.caption).foregroundColor(CVZ.warn)
                        .accessibilityIdentifier("conversation.status")
                    Button("Check status") { Task { await checkRun(); await loadHistory() } }
                        .font(.subheadline)
                        .accessibilityIdentifier("conversation.check")
                    if run == nil || run?.status == "unconfirmed" {
                        Button("Continue after reviewing") { reviewingDelivery = (delivery, scope) }
                            .font(.subheadline)
                            .disabled(conversationStore.storageError != nil)
                            .accessibilityIdentifier("conversation.review")
                    }
                }
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Message this conversation", text: draftBinding,
                              prompt: Text("Message this conversation").foregroundColor(CVZ.textSub), axis: .vertical)
                        .accessibilityIdentifier("conversation.draft")
                        .lineLimit(1...5)
                        .textInputAutocapitalization(.sentences)
                        .padding(10)
                        .background(CVZ.bg, in: RoundedRectangle(cornerRadius: 8))
                        .disabled(submission.preventsNewMessage)
                    Button { Task { await send() } } label: {
                        if submission.isSending { ProgressView() }
                        else { Image(systemName: "arrow.up.circle.fill").font(.title) }
                    }
                    .accessibilityLabel("Send message")
                    .accessibilityIdentifier("conversation.send")
                    .disabled(!canSend)
                    .frame(minWidth: 44, minHeight: 44)
                }
            }
        }
        .padding(16)
        .background(CVZ.panel)
    }

    @MainActor
    private func loadHistory(offset: Int = 0) async {
        guard !loading else { return }
        loading = true
        historyGeneration += 1
        let generation = historyGeneration
        defer { if generation == historyGeneration { loading = false } }
        do {
            let request = try ConversationClient.request("/history", query: [
                URLQueryItem(name: "session_key", value: selected.sessionKey),
                URLQueryItem(name: "offset", value: String(offset)),
            ])
            let response = try await ConversationClient.load(request, as: OpenClawConversationHistory.self)
            guard !Task.isCancelled, generation == historyGeneration else { return }
            guard response.session.sessionKey == selected.sessionKey else { throw URLError(.badServerResponse) }
            if offset == 0 {
                messages = response.messages
                history = response
                showingEarlierMessages = false
                if shouldScrollToLatest {
                    latestScrollRevision += 1
                    shouldScrollToLatest = false
                }
            } else {
                guard response.session.sessionId == history?.session.sessionId else {
                    throw URLError(.badServerResponse)
                }
                let known = Set(messages.map(\.id))
                messages.insert(contentsOf: response.messages.filter { !known.contains($0.id) }, at: 0)
                showingEarlierMessages = true
            }
            nextOffset = response.hasMore ? response.nextOffset : nil
            error = nil
        } catch {
            guard !Task.isCancelled, generation == historyGeneration else { return }
            self.error = error.localizedDescription
        }
    }

    @MainActor
    private func send() async {
        guard canSend, let sessionId = history?.session.sessionId else { return }
        let payload = OpenClawConversationRequest(
            sessionKey: selected.sessionKey, sessionId: sessionId,
            text: draft.trimmingCharacters(in: .whitespacesAndNewlines), requestId: UUID().uuidString,
            expectedLeafEntryId: history?.session.activeLeafEntryId
        )
        let requestScope = scope
        do {
            // Freeze the URL and credential before suspension, alongside the
            // delivery owner. A later pairing change must not retarget this send.
            let request = try ConversationClient.messageRequest(payload)
            guard conversationStore.beginSend(payload.delivery, in: requestScope) else { return }
            let receipt = try await ConversationClient.load(request, as: OpenClawConversationReceipt.self)
            guard conversationStore.isCurrent(requestScope) else { return }
            guard receipt.runId == payload.requestId else { throw URLError(.badServerResponse) }
            conversationStore.acknowledge(receipt, delivery: payload.delivery, in: requestScope)
            shouldScrollToLatest = true
            await loadHistory()
        } catch {
            guard conversationStore.isCurrent(requestScope) else { return }
            let rejected = (error as? ConversationServiceError)?.deliveryUncertain == false
            conversationStore.recordError(error.localizedDescription, in: requestScope)
            conversationStore.rejectSend(error.localizedDescription, delivery: payload.delivery,
                                         definitelyNotSent: rejected, in: requestScope)
            if rejected { await loadHistory() }
        }
    }

    @MainActor
    private func checkRun() async {
        guard case let .tracking(delivery, prior) = submission, prior?.isTerminal != true else { return }
        let requestScope = scope
        do {
            let request = try ConversationClient.request("/run", query: [
                URLQueryItem(name: "session_key", value: delivery.sessionKey), URLQueryItem(name: "run_id", value: delivery.requestId),
            ])
            let run = try await ConversationClient.load(request, as: OpenClawConversationRun.self)
            guard !Task.isCancelled,
                  conversationStore.recordRun(run, delivery: delivery, in: requestScope) else { return }
            if run.isTerminal { shouldScrollToLatest = true }
        } catch {
            guard !Task.isCancelled, conversationStore.isCurrent(requestScope) else { return }
            conversationStore.recordError(error.localizedDescription, in: requestScope)
        }
    }
}
