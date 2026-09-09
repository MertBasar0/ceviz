import Foundation

// Mirrors watch-command-request.schema.json
struct WatchCommandRequest: Codable {
    let audioData: String
    let format: String
    let clientTimestamp: String?
    /// Saatten gelir; gelmezse telefonun dili kullanilir.
    var locale: String? = Locale.current.identifier
    /// Frozen by the Watch when recording starts; the phone never chooses a target.
    var continueJobId: String? = nil

    enum CodingKeys: String, CodingKey {
        case audioData = "audio_data"
        case format
        case clientTimestamp = "client_timestamp"
        case locale
        case continueJobId = "continue_job_id"
    }
}

/// Continuing a report is not approval to execute its suggested action.
enum PhoneJobCommand: Encodable {
    case followUp(jobId: String, text: String, locale: String)
    case approveSuggestion(jobId: String, actionId: String, locale: String)

    private enum CodingKeys: String, CodingKey {
        case intent, text, locale
        case continueJobId = "continue_job_id"
        case nextActionId = "next_action_id"
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case let .followUp(jobId, text, locale):
            try values.encode("follow_up", forKey: .intent)
            try values.encode(jobId, forKey: .continueJobId)
            try values.encode(text, forKey: .text)
            try values.encode(locale, forKey: .locale)
        case let .approveSuggestion(jobId, actionId, locale):
            try values.encode("approve_suggestion", forKey: .intent)
            try values.encode(jobId, forKey: .continueJobId)
            try values.encode(actionId, forKey: .nextActionId)
            try values.encode(locale, forKey: .locale)
        }
    }
}

enum BackendCapability {
    case continuation
    case suggestionApproval
}

struct BackendCapabilities: Decodable {
    let continuationV1: Bool
    let suggestionApprovalV1: Bool

    enum CodingKeys: String, CodingKey {
        case continuationV1 = "continuation_v1"
        case suggestionApprovalV1 = "suggestion_approval_v1"
    }

    func supports(_ capability: BackendCapability) -> Bool {
        continuationV1 && (capability == .continuation || suggestionApprovalV1)
    }
}

enum BackendCapabilityError: LocalizedError {
    case updateRequired
    case connectionChanged
    case verificationFailed(String)

    var errorDescription: String? {
        switch self {
        case .updateRequired:
            return NSLocalizedString("Update the Ceviz helper service before continuing this job.", comment: "")
        case .connectionChanged:
            return NSLocalizedString("The connection changed. Review the target before sending again.", comment: "")
        case let .verificationFailed(message):
            return message
        }
    }
}

struct ReportMeta: Codable, Equatable {
    let title: String?
    let status: String?
    let severity: String?
    let category: String
    let watchSummary: String
    let requiresPhoneHandoff: Bool
    let handoffReason: String?
    let phoneReport: String
    let nextAction: String?
    let retryCount: Int
    let failureCode: String?
    let failureMessage: String?
    let outcome: String?

    enum CodingKeys: String, CodingKey {
        case title
        case status
        case severity
        case category
        case watchSummary = "watch_summary"
        case requiresPhoneHandoff = "requires_phone_handoff"
        case handoffReason = "handoff_reason"
        case phoneReport = "phone_report"
        case nextAction = "next_action"
        case retryCount = "retry_count"
        case failureCode = "failure_code"
        case failureMessage = "failure_message"
        case outcome
    }
}

struct NextActionPayload: Codable, Equatable, Identifiable {
    let id: String
    let label: String
    let kind: String
    let target: String?
}

// Mirrors watch-command-response.schema.json
struct WatchCommandResponse: Codable {
    let status: String
    var outcome: String? = nil
    let transcript: String
    let summaryText: String
    let ttsAudioData: String?
    let ttsFormat: String?
    let requiresPhoneHandoff: Bool
    let handoffUrl: String?
    let deepLink: String?
    let handoffReason: String?
    let jobId: String?
    let phoneReport: String?
    let reportMeta: ReportMeta?
    let reportSections: [ReportBodySectionPayload]?
    let previewSections: [PreviewSectionPayload]?
    let nextActions: [NextActionPayload]?

    enum CodingKeys: String, CodingKey {
        case status
        case outcome
        case transcript
        case summaryText = "summary_text"
        case ttsAudioData = "tts_audio_data"
        case ttsFormat = "tts_format"
        case requiresPhoneHandoff = "requires_phone_handoff"
        case handoffUrl = "handoff_url"
        case deepLink = "deep_link"
        case handoffReason = "handoff_reason"
        case jobId = "job_id"
        case phoneReport = "phone_report"
        case reportMeta = "report_meta"
        case reportSections = "report_sections"
        case previewSections = "preview_sections"
        case nextActions = "next_actions"
    }
}

struct JobSummaryResponse: Codable {
    let summary: String
    let requiresPhoneHandoff: Bool
    let status: String
    var outcome: String? = nil
    let transcript: String
    let phoneReport: String
    let handoffUrl: String?
    let deepLink: String?
    let handoffReason: String?
    let reportMeta: ReportMeta?
    let reportSections: [ReportBodySectionPayload]?
    let previewSections: [PreviewSectionPayload]?
    let nextActions: [NextActionPayload]?

    enum CodingKeys: String, CodingKey {
        case summary
        case requiresPhoneHandoff = "requires_phone_handoff"
        case status
        case outcome
        case transcript
        case phoneReport = "phone_report"
        case handoffUrl = "handoff_url"
        case deepLink = "deep_link"
        case handoffReason = "handoff_reason"
        case reportMeta = "report_meta"
        case reportSections = "report_sections"
        case previewSections = "preview_sections"
        case nextActions = "next_actions"
    }
}

struct StructuredSectionPayload: Codable, Equatable, Identifiable {
    let id: String
    let title: String
    let eyebrow: String
    let icon: String
    let content: String
}

typealias PreviewSectionPayload = StructuredSectionPayload
typealias ReportBodySectionPayload = StructuredSectionPayload

struct ActiveJob: Codable, Identifiable {
    let id: String
    var conversationId: String?
    let name: String
    var status: String
    var outcome: String? = nil
    let elapsedSeconds: Int
    let summaryText: String
    let requiresPhoneHandoff: Bool
    let transcript: String
    let phoneReport: String
    let deepLink: String?
    let reportMeta: ReportMeta?
    let reportSections: [ReportBodySectionPayload]?
    let previewSections: [PreviewSectionPayload]?
    let nextActions: [NextActionPayload]?

    var presentationState: CVZJobState {
        CVZJobState.resolve(status: status, outcome: outcome ?? reportMeta?.outcome)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case conversationId = "conversation_id"
        case name
        case status
        case outcome
        case elapsedSeconds = "elapsed_seconds"
        case summaryText = "summary_text"
        case requiresPhoneHandoff = "requires_phone_handoff"
        case transcript
        case phoneReport = "phone_report"
        case deepLink = "deep_link"
        case reportMeta = "report_meta"
        case reportSections = "report_sections"
        case previewSections = "preview_sections"
        case nextActions = "next_actions"
    }
}

struct ActiveJobsResponse: Codable {
    let jobs: [ActiveJob]
}
