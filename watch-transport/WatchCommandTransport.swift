import Foundation
import CryptoKit

/// One request/receipt contract across interactive messages and background files.
/// The extra identity fields stay on the Watch link; the phone forwards the
/// unchanged audio and timestamp using the existing backend request model.
enum WatchCommandTransport {
    static let interactiveBudget = 60_000
    static let maximumAge: TimeInterval = 15 * 60
    static let fileAction = "audio_command_file_v1"
    static let receiptAction = "audio_command_receipt_v1"
    static let capabilitiesAction = "audio_command_capabilities"

    static func supportsFiles(_ reply: [String: Any]) -> Bool { reply["audio_file_v1"] as? Bool == true }

    struct Identity: Equatable {
        let commandID: String
        let digest: String

        var fileMetadata: [String: Any] {
            ["action": fileAction, "command_id": commandID, "audio_digest": digest]
        }
    }

    struct Incoming {
        let request: WatchCommandRequest
        let identity: Identity?
    }

    enum TransportError: Error {
        case invalidIdentity, expiredRequest, invalidRequest, invalidReceipt
    }

    static func identity(commandID: String, request: WatchCommandRequest) -> Identity {
        // Match both the saved audio bytes and their original capture timestamp.
        // Locale and JSON key order may differ after an app upgrade/retry.
        let material = (request.clientTimestamp ?? "") + "\n" + request.audioData
        let digest = SHA256.hash(data: Data(material.utf8)).map { String(format: "%02x", $0) }.joined()
        return Identity(commandID: commandID, digest: digest)
    }

    static func encode(_ request: WatchCommandRequest, commandID: String) throws -> Data {
        guard UUID(uuidString: commandID) != nil else { throw TransportError.invalidIdentity }
        let encoded = try JSONEncoder().encode(request)
        guard var object = try JSONSerialization.jsonObject(with: encoded) as? [String: Any] else {
            throw TransportError.invalidRequest
        }
        let identity = identity(commandID: commandID, request: request)
        object["command_id"] = identity.commandID
        object["audio_digest"] = identity.digest
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    static func needsFile(_ data: Data) -> Bool { data.count > interactiveBudget }

    static func isCurrent(_ request: WatchCommandRequest, after resetAt: Date? = nil, now: Date = Date()) -> Bool {
        guard let timestamp = request.clientTimestamp,
              let captured = ISO8601DateFormatter().date(from: timestamp) else { return false }
        if let resetAt, captured <= resetAt { return false }
        return now.timeIntervalSince(captured) < maximumAge
    }

    static func decode(_ data: Data, metadata: [String: Any]? = nil, now: Date = Date()) throws -> Incoming {
        let request = try JSONDecoder().decode(WatchCommandRequest.self, from: data)
        guard !request.audioData.isEmpty, ["m4a", "aac"].contains(request.format),
              let audio = Data(base64Encoded: request.audioData), !audio.isEmpty,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw TransportError.invalidRequest
        }
        // An old Watch still sends the original flat request without identity.
        if object["command_id"] == nil && object["audio_digest"] == nil && metadata == nil {
            return Incoming(request: request, identity: nil)
        }
        guard let commandID = object["command_id"] as? String, UUID(uuidString: commandID) != nil,
              let digest = object["audio_digest"] as? String else { throw TransportError.invalidIdentity }
        let expected = identity(commandID: commandID, request: request)
        guard expected.digest == digest else { throw TransportError.invalidIdentity }
        if let metadata {
            guard metadata["action"] as? String == fileAction,
                  metadata["command_id"] as? String == commandID,
                  metadata["audio_digest"] as? String == digest else { throw TransportError.invalidIdentity }
        }
        guard isCurrent(request, now: now) else { throw TransportError.expiredRequest }
        return Incoming(request: request, identity: expected)
    }

    /// Read synchronously while WCSession still owns the received URL. No mmap:
    /// all bytes are owned by Data before the delegate returns and Apple deletes it.
    static func receiveFile(at url: URL, metadata: [String: Any]?, now: Date = Date()) throws -> Incoming {
        guard let metadata else { throw TransportError.invalidIdentity }
        return try decode(Data(contentsOf: url), metadata: metadata, now: now)
    }

    static func isReceipt(_ response: WatchCommandResponse) -> Bool {
        guard let jobID = response.jobId, !jobID.isEmpty else { return false }
        return ["processing", "running", "queued", "completed", "failed"].contains(response.status)
    }

    /// Background receipts must remain small even when the HTTP response contains
    /// a full report or TTS. The complete result remains available through Jobs.
    static func receipt(responseData: Data, identity: Identity) throws -> [String: Any] {
        let response = try JSONDecoder().decode(WatchCommandResponse.self, from: responseData)
        guard isReceipt(response) else { throw TransportError.invalidReceipt }
        let compact: [String: Any] = [
            "status": response.status,
            "job_id": response.jobId!,
            "outcome": response.outcome ?? response.reportMeta?.outcome ?? "unknown",
            "summary_text": String(decoding: response.summaryText.utf8.prefix(4_096), as: UTF8.self),
            "transcript": "",
            "requires_phone_handoff": response.reportMeta?.requiresPhoneHandoff ?? response.requiresPhoneHandoff,
        ]
        return [
            "action": receiptAction,
            "command_id": identity.commandID,
            "audio_digest": identity.digest,
            "response_data": try JSONSerialization.data(withJSONObject: compact),
        ]
    }

    static func receivedReceipt(_ message: [String: Any], matching identity: Identity) -> Data? {
        guard message["action"] as? String == receiptAction,
              message["command_id"] as? String == identity.commandID,
              message["audio_digest"] as? String == identity.digest,
              let data = message["response_data"] as? Data,
              let response = try? JSONDecoder().decode(WatchCommandResponse.self, from: data),
              isReceipt(response) else { return nil }
        return data
    }
}

/// Disposable WC transfer artifacts, not another audio queue. The existing saved
/// command remains the source of truth until a backend receipt or its 15m expiry.
struct WatchCommandFiles {
    let directory: URL

    init(directory: URL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("ceviz-watch-command-transfers", isDirectory: true)) {
        self.directory = directory
    }

    func stage(_ data: Data, commandID: String) throws -> URL {
        guard UUID(uuidString: commandID) != nil else { throw WatchCommandTransport.TransportError.invalidIdentity }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent(commandID + ".json")
        // Reuse immutable bytes on retries; never rewrite a file WC may still read.
        if FileManager.default.fileExists(atPath: url.path) { return url }
        #if os(iOS) || os(watchOS)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        #else
        try data.write(to: url, options: .atomic)
        #endif
        return url
    }

    func remove(_ url: URL) {
        guard url.deletingLastPathComponent().standardizedFileURL == directory.standardizedFileURL,
              url.pathExtension == "json" else { return }
        try? FileManager.default.removeItem(at: url)
    }

    func remove(commandID: String) {
        guard UUID(uuidString: commandID) != nil else { return }
        remove(directory.appendingPathComponent(commandID + ".json"))
    }

    func prune(keeping commandIDs: Set<String>) {
        guard let files = try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) else { return }
        for file in files where !commandIDs.contains(file.deletingPathExtension().lastPathComponent) { remove(file) }
    }
}
