import Foundation
import AVFoundation

class AudioRecorderManager: NSObject, ObservableObject, AVAudioRecorderDelegate {
    static let maximumDuration: TimeInterval = 15
    private var audioRecorder: AVAudioRecorder?
    private var recordingURL: URL?
    private var permissionGeneration = 0
    @Published private(set) var isRecording = false
    @Published var lastError: String?

    override init() {
        super.init()
        NotificationCenter.default.addObserver(self, selector: #selector(recordingInterrupted(_:)), name: AVAudioSession.interruptionNotification, object: AVAudioSession.sharedInstance())
    }

    var elapsedSeconds: TimeInterval { audioRecorder?.currentTime ?? 0 }

    func startRecording(completion: @escaping (Bool) -> Void) {
        lastError = nil
        permissionGeneration += 1
        let generation = permissionGeneration
        let session = AVAudioSession.sharedInstance()
        switch session.recordPermission {
        case .granted:
            completion(beginRecording(session: session))
        case .denied:
            lastError = NSLocalizedString("Microphone access denied. Allow it in Watch settings.", comment: "")
            completion(false)
        case .undetermined:
            session.requestRecordPermission { [weak self] granted in
                DispatchQueue.main.async {
                    // Dismissing a permission prompt must not start a cancelled capture later.
                    guard let self, self.permissionGeneration == generation else { return }
                    if granted {
                        completion(self.beginRecording(session: session))
                    } else {
                        self.lastError = NSLocalizedString("Microphone permission was not granted.", comment: "")
                        completion(false)
                    }
                }
            }
        @unknown default:
            lastError = NSLocalizedString("Unknown microphone permission state.", comment: "")
            completion(false)
        }
    }

    private func beginRecording(session: AVAudioSession) -> Bool {
        do {
            try session.setCategory(.playAndRecord, mode: .default)
            try session.setActive(true)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("command.m4a")
            recordingURL = url
            // Keep a short AAC recording below the WCSession payload limit.
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC), AVSampleRateKey: 16000,
                AVNumberOfChannelsKey: 1, AVEncoderBitRateKey: 16000,
                AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
            ]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            recorder.delegate = self
            guard recorder.record(forDuration: Self.maximumDuration) else {
                lastError = NSLocalizedString("Could not start recording.", comment: "")
                discardAudio()
                return false
            }
            audioRecorder = recorder
            isRecording = true
            return true
        } catch {
            lastError = String(format: NSLocalizedString("Recording setup failed: %@", comment: ""), error.localizedDescription)
            discardAudio()
            return false
        }
    }

    func stopRecording() -> String? {
        permissionGeneration += 1
        guard let recorder = audioRecorder else { return nil }
        audioRecorder = nil
        recorder.stop()
        isRecording = false
        defer { discardAudio() }
        guard lastError == nil, let url = recordingURL,
              let data = try? Data(contentsOf: url), !data.isEmpty else {
            if lastError == nil { lastError = NSLocalizedString("The audio file is empty or unreadable.", comment: "") }
            return nil
        }
        return data.base64EncodedString()
    }

    func cancelRecording() {
        permissionGeneration += 1
        discardAudio()
        lastError = nil
    }

    private func discardAudio() {
        let recorder = audioRecorder
        audioRecorder = nil
        recorder?.stop()
        isRecording = false
        if let url = recordingURL { try? FileManager.default.removeItem(at: url) }
        recordingURL = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        DispatchQueue.main.async { [weak self] in
            guard let self, recorder === self.audioRecorder else { return }
            if !flag { self.lastError = NSLocalizedString("Recording was interrupted. Please try again.", comment: "") }
            self.isRecording = false
        }
    }

    @objc private func recordingInterrupted(_ notification: Notification) {
        guard let type = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              type == AVAudioSession.InterruptionType.began.rawValue else { return }
        let generation = permissionGeneration
        DispatchQueue.main.async { [weak self] in
            guard let self, self.isRecording, self.permissionGeneration == generation else { return }
            self.lastError = NSLocalizedString("Recording was interrupted. Please try again.", comment: "")
            self.discardAudio()
        }
    }
}
