import Foundation

struct OpenClawConversation: Decodable, Identifiable, Equatable {
    let sessionKey: String
    let sessionId: String?
    let agentId: String
    let title: String
    let preview: String?
    let updatedAtMs: Double?
    let isRunning: Bool
    let archived: Bool
    let status: String?
    let activeLeafEntryId: String?
    let canSend: Bool

    var id: String { sessionKey }
    var updatedAt: Date? { updatedAtMs.map { Date(timeIntervalSince1970: $0 / 1000) } }

    enum CodingKeys: String, CodingKey {
        case sessionKey = "session_key"
        case sessionId = "session_id"
        case agentId = "agent_id"
        case title, preview
        case updatedAtMs = "updated_at_ms"
        case isRunning = "is_running"
        case archived, status
        case activeLeafEntryId = "active_leaf_entry_id"
        case canSend = "can_send"
    }

}

struct OpenClawConversationAgent: Decodable, Identifiable {
    let id: String
    let name: String
}

struct OpenClawConversationsResponse: Decodable {
    let sessions: [OpenClawConversation]
    let agents: [OpenClawConversationAgent]
    let hasMore: Bool
    let nextOffset: Int?

    enum CodingKeys: String, CodingKey {
        case sessions, agents
        case hasMore = "has_more"
        case nextOffset = "next_offset"
    }

}

struct OpenClawConversationMessage: Decodable, Identifiable {
    let id: String
    let role: String
    let text: String
    let timestampMs: Double?
    let hasOtherContent: Bool

    var timestamp: Date? { timestampMs.map { Date(timeIntervalSince1970: $0 / 1000) } }

    enum CodingKeys: String, CodingKey {
        case id, role, text
        case timestampMs = "timestamp_ms"
        case hasOtherContent = "has_other_content"
    }
}

struct OpenClawConversationHistory: Decodable {
    let session: OpenClawConversation
    let messages: [OpenClawConversationMessage]
    let hasMore: Bool
    let nextOffset: Int?
    let activeRunIds: [String]
    let pendingCount: Int

    enum CodingKeys: String, CodingKey {
        case session, messages
        case hasMore = "has_more"
        case nextOffset = "next_offset"
        case activeRunIds = "active_run_ids"
        case pendingCount = "pending_count"
    }
}

struct OpenClawConversationRequest: Encodable, Equatable {
    let sessionKey: String
    let sessionId: String
    let text: String
    let requestId: String
    let expectedLeafEntryId: String?

    enum CodingKeys: String, CodingKey {
        case sessionKey = "session_key"
        case sessionId = "session_id"
        case text
        case requestId = "request_id"
        case expectedLeafEntryId = "expected_leaf_entry_id"
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(sessionKey, forKey: .sessionKey)
        try values.encode(sessionId, forKey: .sessionId)
        try values.encode(text, forKey: .text)
        try values.encode(requestId, forKey: .requestId)
        // A known empty transcript leaf is JSON null, not an omitted concurrency guard.
        try values.encode(expectedLeafEntryId, forKey: .expectedLeafEntryId)
    }
}

struct OpenClawConversationReceipt: Decodable {
    let runId: String
    let status: String
    let deliveryConfirmed: Bool

    enum CodingKeys: String, CodingKey {
        case runId = "run_id"
        case status
        case deliveryConfirmed = "delivery_confirmed"
    }
}

struct OpenClawConversationRun: Decodable {
    let runId: String
    let status: String
    let detail: String?

    var isTerminal: Bool { ["completed", "failed", "aborted"].contains(status) }

    var statusKey: String {
        switch status {
        case "running": return "Working"
        case "queued": return "Queued"
        case "completed": return "Run finished — review the conversation."
        case "failed": return "The response could not be completed."
        case "aborted": return "The response was stopped."
        case "unconfirmed": return "Delivery is not confirmed. Check the conversation before sending again."
        default: return "Request received — status unavailable."
        }
    }

    enum CodingKeys: String, CodingKey {
        case runId = "run_id"
        case status, detail
    }
}

/// The request survives an ambiguous HTTP result without becoming a new send.
enum ConversationSubmission {
    case idle
    case sending(OpenClawConversationRequest)
    case tracking(OpenClawConversationRequest, runId: String, run: OpenClawConversationRun?)

    var isSending: Bool {
        if case .sending = self { return true }
        return false
    }

    var preventsNewMessage: Bool {
        switch self {
        case .idle: return false
        case .sending: return true
        case let .tracking(_, _, run): return run?.isTerminal != true
        }
    }
}
