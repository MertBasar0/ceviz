import Combine
import Foundation

struct ConversationSessionScope: Equatable {
    fileprivate let pairingId: UUID
    let sessionKey: String
}

struct ConversationSessionState {
    var draft = ""
    var submission: ConversationSubmission = .idle
    var error: String?
}

/// Navigation is not a new delivery attempt. This app-session owner retains
/// pending identities and drafts without persisting messages or credentials.
@MainActor
final class ConversationSessionStore: ObservableObject {
    private struct PairingIdentity: Equatable {
        let baseURL: String
        let token: String
    }

    private var pairing: PairingIdentity
    private var pairingId = UUID()
    @Published private var entries: [String: ConversationSessionState] = [:]

    init(baseURL: String, token: String) {
        pairing = PairingIdentity(baseURL: baseURL, token: token)
    }

    func synchronizeConnection(baseURL: String, token: String) {
        let updated = PairingIdentity(baseURL: baseURL, token: token)
        guard updated != pairing else { return }
        pairing = updated
        pairingId = UUID()
        entries.removeAll()
    }

    func scope(for sessionKey: String) -> ConversationSessionScope {
        ConversationSessionScope(pairingId: pairingId, sessionKey: sessionKey)
    }

    func isCurrent(_ scope: ConversationSessionScope) -> Bool { scope.pairingId == pairingId }

    func state(for scope: ConversationSessionScope) -> ConversationSessionState {
        guard isCurrent(scope) else { return ConversationSessionState() }
        return entries[scope.sessionKey] ?? ConversationSessionState()
    }

    func update(_ scope: ConversationSessionScope, _ change: (inout ConversationSessionState) -> Void) {
        guard isCurrent(scope) else { return }
        var value = entries[scope.sessionKey] ?? ConversationSessionState()
        change(&value)
        entries[scope.sessionKey] = value
    }

    @discardableResult
    func recordRun(_ run: OpenClawConversationRun, request: OpenClawConversationRequest, in scope: ConversationSessionScope) -> Bool {
        guard isCurrent(scope), var value = entries[scope.sessionKey],
              case let .tracking(current, runId, previous) = value.submission,
              current == request, runId == run.runId, previous?.isTerminal != true else { return false }
        // A slower poll from a previous screen must not replace terminal evidence.
        value.submission = .tracking(request, runId: runId, run: run)
        if run.status != "unconfirmed" { value.draft = "" }
        entries[scope.sessionKey] = value
        return true
    }
}
