import Foundation

/// Presentation of a recorded run and its reported outcome, not proof of external effects.
enum CVZJobState: Equatable {
    case queued, running, completed, blocked, needsInput, failed, resultReady, unknown

    static func resolve(status: String, outcome: String?) -> CVZJobState {
        switch status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "queued": return .queued
        case "running", "processing": return .running
        case "failed": return .failed
        case "completed":
            // A completed run can still require input. Older beta payloads without
            // outcome remain readable, but must not acquire an invented success.
            switch outcome?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            case "done": return .completed
            case "blocked": return .blocked
            case "needs_input": return .needsInput
            default: return .resultReady
            }
        default: return .unknown
        }
    }

    var needsAttention: Bool {
        self == .blocked || self == .needsInput || self == .failed
    }

    var isReportedResult: Bool {
        self == .completed || self == .blocked || self == .needsInput || self == .resultReady
    }

    var titleKey: String {
        switch self {
        case .queued: return "Queued"
        case .running: return "Working"
        case .completed: return "Completed"
        case .blocked: return "Blocked"
        case .needsInput: return "Needs your input"
        case .failed: return "Failed"
        case .resultReady: return "Result ready"
        case .unknown: return "Status unavailable"
        }
    }

    var statusTagKey: String {
        switch self {
        case .queued: return "[QUEUED]"
        case .running: return "[RUNNING]"
        case .completed: return "[DONE]"
        case .blocked: return "[BLOCKED]"
        case .needsInput: return "[NEEDS INPUT]"
        case .failed: return "[FAILED]"
        case .resultReady: return "[RESULT READY]"
        case .unknown: return "[UNKNOWN]"
        }
    }

    var symbolName: String {
        switch self {
        case .queued: return "tray.and.arrow.down"
        case .running: return "hourglass"
        case .completed: return "checkmark.circle"
        case .blocked: return "exclamationmark.octagon"
        case .needsInput: return "text.bubble"
        case .failed: return "exclamationmark.triangle"
        case .resultReady: return "doc.text"
        case .unknown: return "questionmark.circle"
        }
    }
}
