import Foundation
import AVFoundation
import os

class AudioRecorderManager: NSObject, ObservableObject, AVAudioRecorderDelegate {
    static let maximumDuration = WatchRecordingLifecycle.maximumDuration
    private var audioRecorder: AVAudioRecorder?
    private var interruptionObserver: NSObjectProtocol?
    private var lifecycle = WatchRecordingLifecycle()
    private let logger = Logger(subsystem: "com.mertbasar.ceviz.watch", category: "AudioCapture")
    @Published private(set) var isRecording = false
    @Published var lastError: String?
    /// Delivered once on main after a manual or native time-limit finish, never after cancellation.
    var onRecordingFinished: ((Result<String, Error>) -> Void)?

    deinit {
        if let observer = interruptionObserver { NotificationCenter.default.removeObserver(observer) }
        audioRecorder?.stop()
        if let url = audioRecorder?.url { try? FileManager.default.removeItem(at: url) }
    }

    var elapsedSeconds: TimeInterval { lifecycle.elapsed(at: ProcessInfo.processInfo.systemUptime) }

    func startRecording(completion: @escaping (Bool) -> Void) {
        guard lifecycle.id == nil else { return }
        lastError = nil
        let id = lifecycle.prepare()
        let session = AVAudioSession.sharedInstance()
        let permitted: (Bool) -> Void = { [weak self] granted in
            guard let self, self.lifecycle.isPreparing(id) else { return }
            if granted {
                completion(self.beginRecording(session: session, id: id))
            } else {
                self.lastError = NSLocalizedString("Microphone access denied. Allow it in Watch settings.", comment: "")
                self.lifecycle.cancel()
                completion(false)
            }
        }
        switch session.recordPermission {
        case .granted: permitted(true)
        case .denied: permitted(false)
        case .undetermined:
            session.requestRecordPermission { granted in DispatchQueue.main.async { permitted(granted) } }
        @unknown default:
            lastError = NSLocalizedString("Unknown microphone permission state.", comment: "")
            lifecycle.cancel()
            completion(false)
        }
    }

    private func beginRecording(session: AVAudioSession, id: UUID) -> Bool {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("command-\(id).m4a")
        do {
            try session.setCategory(.playAndRecord, mode: .default)
            try session.setActive(true)
            // These are requested encoder settings, not a guarantee about final file size.
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC), AVSampleRateKey: 16000,
                AVNumberOfChannelsKey: 1, AVEncoderBitRateKey: 16000,
                AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
            ]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            audioRecorder = recorder
            recorder.delegate = self
            guard recorder.record(forDuration: Self.maximumDuration) else {
                lastError = NSLocalizedString("Could not start recording.", comment: "")
                lifecycle.cancel()
                discardAudio()
                return false
            }
            lifecycle.begin(id, at: ProcessInfo.processInfo.systemUptime)
            interruptionObserver = NotificationCenter.default.addObserver(
                forName: AVAudioSession.interruptionNotification, object: session, queue: .main
            ) { [weak self, weak recorder] notification in
                guard let recorder,
                      let type = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                      type == AVAudioSession.InterruptionType.began.rawValue else { return }
                // Interruptions do not emit the finished delegate. Bind this observer to
                // this recorder so a queued old interruption cannot cancel its successor.
                self?.finishRecording(recorder, successfully: false)
            }
            isRecording = true
            return true
        } catch {
            lastError = String(format: NSLocalizedString("Recording setup failed: %@", comment: ""), error.localizedDescription)
            lifecycle.cancel()
            discardAudio()
            try? FileManager.default.removeItem(at: url)
            return false
        }
    }

    func stopRecording() {
        guard lifecycle.requestStop(at: ProcessInfo.processInfo.systemUptime) else { return }
        // The delegate owns finalization for both manual stop and record(forDuration:).
        audioRecorder?.stop()
    }

    func cancelRecording() {
        lifecycle.cancel()
        discardAudio()
        lastError = nil
    }

    private func discardAudio() {
        if let observer = interruptionObserver { NotificationCenter.default.removeObserver(observer) }
        interruptionObserver = nil
        let recorder = audioRecorder
        audioRecorder = nil
        recorder?.stop()
        isRecording = false
        if let url = recorder?.url { try? FileManager.default.removeItem(at: url) }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func finishRecording(_ recorder: AVAudioRecorder, successfully: Bool, at time: TimeInterval = ProcessInfo.processInfo.systemUptime) {
        guard recorder === audioRecorder, let id = lifecycle.id,
              lifecycle.finish(id, at: time) else { return }
        let result: Result<String, Error>
        if successfully, let data = try? Data(contentsOf: recorder.url), !data.isEmpty {
            // Numeric file metadata only: never log speech, Base64, filenames, or transcripts.
            if let file = try? AVAudioFile(forReading: recorder.url) {
                let duration = Double(file.length) / file.processingFormat.sampleRate
                let codec = file.fileFormat.streamDescription.pointee.mFormatID
                logger.info("Capture finalized: duration_seconds=\(duration, privacy: .public) bytes=\(data.count, privacy: .public) codec=\(codec, privacy: .public) sample_rate=\(file.fileFormat.sampleRate, privacy: .public) channels=\(file.fileFormat.channelCount, privacy: .public)")
            } else {
                logger.info("Capture finalized: bytes=\(data.count, privacy: .public) file_metadata=unavailable")
            }
            result = .success(data.base64EncodedString())
        } else {
            let message = NSLocalizedString(successfully ? "The audio file is empty or unreadable." : "Recording was interrupted. Please try again.", comment: "")
            lastError = message
            result = .failure(NSError(domain: "CevizAudioCapture", code: 1, userInfo: [NSLocalizedDescriptionKey: message]))
        }
        discardAudio()
        onRecordingFinished?(result)
    }

    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        let finishedAt = ProcessInfo.processInfo.systemUptime
        DispatchQueue.main.async { [weak self] in self?.finishRecording(recorder, successfully: flag, at: finishedAt) }
    }

    func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        let finishedAt = ProcessInfo.processInfo.systemUptime
        DispatchQueue.main.async { [weak self] in self?.finishRecording(recorder, successfully: false, at: finishedAt) }
    }
}
