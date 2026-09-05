import Foundation

@main
struct WatchTransportTests {
    private static let commandID = "BB8F2A1C-2345-4567-ABCD-0123456789AB"
    private static let otherID = "CC8F2A1C-2345-4567-ABCD-0123456789AB"
    private static let now = Date(timeIntervalSince1970: 1_780_000_000)

    static func main() throws {
        for (count, file) in [(59_999, false), (60_000, false), (60_001, true)] {
            precondition(WatchCommandTransport.needsFile(Data(count: count)) == file)
        }
        precondition(WatchCommandTransport.supportsFiles(["audio_file_v1": true]))
        let unsupportedReplies: [[String: Any]] = [[:], ["error": "Unknown action"], ["audio_file_v1": false], ["audio_file_v1": "true"]]
        for reply in unsupportedReplies {
            precondition(!WatchCommandTransport.supportsFiles(reply), "An older phone must not silently accept an unsupported file")
        }
        let small = request(bytes: 100)
        let encodedSmall = try WatchCommandTransport.encode(small, commandID: commandID)
        precondition(!WatchCommandTransport.needsFile(encodedSmall))
        // Mixed versions: the new flat envelope still decodes in the old model.
        let oldModel = try JSONDecoder().decode(WatchCommandRequest.self, from: encodedSmall)
        precondition(oldModel.audioData == small.audioData && oldModel.clientTimestamp == small.clientTimestamp)
        let legacy = try WatchCommandTransport.decode(JSONEncoder().encode(small), now: now)
        precondition(legacy.identity == nil)
        let aac = WatchCommandRequest(audioData: small.audioData, format: "aac", clientTimestamp: small.clientTimestamp)
        _ = try WatchCommandTransport.decode(WatchCommandTransport.encode(aac, commandID: commandID), now: now)

        // This payload crossed the old 60KB guard and was deleted without a
        // receipt. It now selects file transport with the exact same audio/time.
        let large = request(bytes: 48_000)
        let encoded = try WatchCommandTransport.encode(large, commandID: commandID)
        precondition(encoded.count > 60_000 && WatchCommandTransport.needsFile(encoded))
        let identity = WatchCommandTransport.identity(commandID: commandID, request: large)
        let received = try WatchCommandTransport.decode(encoded, metadata: identity.fileMetadata, now: now)
        precondition(received.identity == identity)
        precondition(received.request.audioData == large.audioData && received.request.clientTimestamp == large.clientTimestamp)
        let retryEncoding = try WatchCommandTransport.encode(large, commandID: commandID)
        precondition(retryEncoding == encoded, "Retries preserve serialized request bytes")
        var differentLocale = large
        differentLocale.locale = "tr_TR"
        precondition(WatchCommandTransport.identity(commandID: commandID, request: differentLocale) == identity)

        try mustReject { _ = try WatchCommandTransport.decode(encoded, metadata: [:], now: now) }
        var wrongMetadata = identity.fileMetadata
        wrongMetadata["command_id"] = otherID
        try mustReject { _ = try WatchCommandTransport.decode(encoded, metadata: wrongMetadata, now: now) }
        var tampered = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
        tampered["audio_data"] = small.audioData
        let tamperedData = try JSONSerialization.data(withJSONObject: tampered)
        try mustReject { _ = try WatchCommandTransport.decode(tamperedData, metadata: identity.fileMetadata, now: now) }
        try mustReject { _ = try WatchCommandTransport.decode(encoded, metadata: identity.fileMetadata, now: now.addingTimeInterval(900)) }
        precondition(WatchCommandTransport.isCurrent(large, after: now.addingTimeInterval(-1), now: now))
        precondition(!WatchCommandTransport.isCurrent(large, after: now, now: now), "Capture before/equal to a configuration reset must never target the new backend")
        precondition(!WatchCommandTransport.isCurrent(large, now: now.addingTimeInterval(900)))
        try mustReject { _ = try WatchCommandTransport.encode(large, commandID: "../invalid") }

        let fullResponse = try response(summary: "e" + String(repeating: "\u{301}", count: 50_000), tts: String(repeating: "A", count: 100_000))
        let receipt = try WatchCommandTransport.receipt(responseData: fullResponse, identity: identity)
        let plist = try PropertyListSerialization.data(fromPropertyList: receipt, format: .binary, options: 0)
        precondition(plist.count < 10_000, "Background receipts cannot carry a full report or TTS")
        let compactData = WatchCommandTransport.receivedReceipt(receipt, matching: identity)!
        let compact = try JSONDecoder().decode(WatchCommandResponse.self, from: compactData)
        precondition(compact.jobId == "job-1" && compact.status == "processing")
        precondition(compact.ttsAudioData == nil && compact.phoneReport == nil)
        precondition(WatchCommandTransport.receivedReceipt(receipt, matching: .init(commandID: otherID, digest: identity.digest)) == nil)
        precondition(WatchCommandTransport.receivedReceipt(receipt, matching: .init(commandID: commandID, digest: "wrong")) == nil)
        try mustReject { _ = try WatchCommandTransport.receipt(responseData: response(status: "error", jobID: nil), identity: identity) }
        try mustReject { _ = try WatchCommandTransport.receipt(responseData: response(jobID: nil), identity: identity) }
        try mustReject { _ = try WatchCommandTransport.receipt(responseData: Data("invalid".utf8), identity: identity) }
        for status in ["queued", "running", "completed", "failed"] {
            let message = try WatchCommandTransport.receipt(responseData: response(status: status), identity: identity)
            precondition(WatchCommandTransport.receivedReceipt(message, matching: identity) != nil)
        }
        try testFileLifetime(encoded, identity: identity)
        print("Watch file/message transport, stable identity, expiry/reset cutoff, receipt validation and file cleanup passed")
    }

    private static func request(bytes: Int) -> WatchCommandRequest {
        WatchCommandRequest(audioData: Data(repeating: 17, count: bytes).base64EncodedString(), format: "m4a",
                            clientTimestamp: ISO8601DateFormatter().string(from: now), locale: "en_US")
    }

    private static func response(status: String = "processing", jobID: String? = "job-1", summary: String = "Working", tts: String? = nil) throws -> Data {
        var value: [String: Any] = ["status": status, "transcript": "check", "summary_text": summary, "requires_phone_handoff": false]
        if let jobID { value["job_id"] = jobID }
        if let tts { value["tts_audio_data"] = tts }
        return try JSONSerialization.data(withJSONObject: value)
    }

    private static func mustReject(_ operation: () throws -> Void) throws {
        do { try operation() } catch { return }
        preconditionFailure("Invalid/unacknowledged input must not be accepted")
    }

    private static func testFileLifetime(_ data: Data, identity: WatchCommandTransport.Identity) throws {
        let directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
            .appendingPathComponent("ceviz-transport-test-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let files = WatchCommandFiles(directory: directory.appendingPathComponent("outbox", isDirectory: true))
        let url = try files.stage(data, commandID: commandID)
        let retry = try files.stage(Data("must not rewrite".utf8), commandID: commandID)
        precondition(url == retry)
        let retryBytes = try Data(contentsOf: retry)
        precondition(retryBytes == data, "An in-flight file remains immutable")
        let incoming = try WatchCommandTransport.receiveFile(at: url, metadata: identity.fileMetadata, now: now)
        files.remove(commandID: commandID)
        precondition(!FileManager.default.fileExists(atPath: url.path))
        precondition(incoming.request.audioData == request(bytes: 48_000).audioData,
                     "The received request owns its bytes before Apple's callback deletes the URL")
        let fresh = try files.stage(data, commandID: commandID)
        let orphan = try files.stage(data, commandID: otherID)
        files.prune(keeping: [commandID])
        precondition(FileManager.default.fileExists(atPath: fresh.path))
        precondition(!FileManager.default.fileExists(atPath: orphan.path))
        files.prune(keeping: [])
        precondition(!FileManager.default.fileExists(atPath: fresh.path), "ACK/expiry removes disposable audio artifacts")
        let outside = directory.appendingPathComponent("keep.json")
        try Data("keep".utf8).write(to: outside)
        files.remove(outside)
        precondition(FileManager.default.fileExists(atPath: outside.path), "Cleanup is confined to the transfer directory")
        let badFiles = WatchCommandFiles(directory: outside)
        try mustReject { _ = try badFiles.stage(data, commandID: commandID) }
    }
}
