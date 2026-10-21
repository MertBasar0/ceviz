import AVFoundation
import WatchKit
import os

/// Reads result summaries aloud with the system voice.
///
/// A result for a command this Watch sent is read once, automatically, when it arrives while the
/// app is on screen. One that arrives while the app is away is read if the app opens within
/// `ResultSpeechPolicy.pendingLifetime`. Listen buttons read any summary again. Recording always
/// stops speech first, and nothing is read while a capture is in progress.
final class ResultSpeaker: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    static let shared = ResultSpeaker()
    /// Watch-local setting; results are read aloud unless the user turned it off.
    static let enabledKey = "cvz.speakResults"
    private static let lastSpokenJobKey = "cvz.lastSpokenJobId"
    private static let logger = Logger(subsystem: "com.mertbasar.cevizwatch", category: "speech")

    @Published private(set) var isSpeaking = false
    private let synthesizer = AVSpeechSynthesizer()
    private var pending: (summary: String, jobID: String, until: Date)?

    var isEnabled: Bool { UserDefaults.standard.object(forKey: Self.enabledKey) as? Bool ?? true }

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    /// A finished result arrived for `jobID`. Reads it now, or when the app next opens.
    func announce(_ summary: String, jobID: String) {
        let lastSpoken = UserDefaults.standard.string(forKey: Self.lastSpokenJobKey)
        guard ResultSpeechPolicy.shouldAnnounce(jobID: jobID, lastSpokenJobID: lastSpoken, enabled: isEnabled) else { return }
        guard WKExtension.shared().applicationState == .active else {
            pending = (summary, jobID, Date().addingTimeInterval(ResultSpeechPolicy.pendingLifetime))
            return
        }
        pending = nil
        UserDefaults.standard.set(jobID, forKey: Self.lastSpokenJobKey)
        speak(summary)
    }

    /// The app is on screen again: read a result that arrived while it was away, if still fresh.
    func announcePending() {
        guard let pending else { return }
        self.pending = nil
        guard ResultSpeechPolicy.pendingIsFresh(until: pending.until, now: Date()) else { return }
        announce(pending.summary, jobID: pending.jobID)
    }

    /// Reads `summary` now, replacing anything being read.
    func speak(_ summary: String) {
        let text = SpokenSummary.text(from: summary, linkWord: NSLocalizedString("link", comment: "spoken in place of a web address"))
        guard !text.isEmpty else { return }
        synthesizer.stopSpeaking(at: .immediate)
        do {
            // The recorder leaves the shared session in playAndRecord; speech needs playback.
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .voicePrompt)
            try session.setActive(true)
        } catch {
            Self.logger.error("Speech could not start: \(error.localizedDescription, privacy: .public)")
            return
        }
        let utterance = AVSpeechUtterance(string: text)
        if let language = SpokenSummary.language(for: text, preferredLanguages: Locale.preferredLanguages),
           let voice = Self.voice(for: language) {
            utterance.voice = voice
        }
        isSpeaking = true
        synthesizer.speak(utterance)
    }

    /// A voice for a bare language code ("tr") or a full one ("tr-TR"), preferring the user's region.
    private static func voice(for language: String) -> AVSpeechSynthesisVoice? {
        if let voice = AVSpeechSynthesisVoice(language: language) { return voice }
        let code = String(language.split(separator: "-").first ?? Substring(language))
        if let regional = Locale.preferredLanguages.first(where: { $0.hasPrefix(code) }),
           let voice = AVSpeechSynthesisVoice(language: regional) {
            return voice
        }
        return AVSpeechSynthesisVoice.speechVoices().first { $0.language.hasPrefix(code) }
    }

    /// Stops reading. A result still waiting for the app to open stays pending.
    func stop() {
        guard synthesizer.isSpeaking || isSpeaking else { return }
        synthesizer.stopSpeaking(at: .immediate)
    }

    /// A new recording makes an earlier result's late readback unwanted.
    func cancelPending() {
        pending = nil
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        finished()
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        finished()
    }

    private func finished() {
        DispatchQueue.main.async {
            guard !self.synthesizer.isSpeaking else { return }
            self.isSpeaking = false
            // A recording that started meanwhile switched the session to playAndRecord and owns it now.
            let session = AVAudioSession.sharedInstance()
            if session.category == .playback {
                try? session.setActive(false, options: .notifyOthersOnDeactivation)
            }
        }
    }
}
