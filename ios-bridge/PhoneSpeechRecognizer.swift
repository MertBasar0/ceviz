import AVFoundation
import Foundation
import Speech

/// Turns a Watch capture into text on this iPhone, for a helper whose machine runs no Whisper.
///
/// Only on-device recognizers are used, so the audio is not sent to Apple for this:
/// SpeechTranscriber (iOS 26), else DictationTranscriber (iOS 26: the on-device models of
/// system dictation, without its keyboard, Done button or time limit), else SFSpeechRecognizer
/// with on-device recognition required (iOS 16–25). A language without an on-device model fails
/// with a reason the helper shows; it never falls back to a network recognizer.
enum PhoneSpeechRecognizer {
    struct Preparation: Equatable {
        let ready: Bool
        let message: String
    }

    /// `hints`: proper nouns to expect (the helper's speech hints, Whisper's hotwords).
    static func transcribe(_ request: WatchCommandRequest, hints: [String] = []) async -> PhoneTranscript {
        guard let audio = Data(base64Encoded: request.audioData), !audio.isEmpty else {
            return PhoneTranscript(error: NSLocalizedString("The recording could not be read.", comment: "Phone transcription"))
        }
        let file = FileManager.default.temporaryDirectory
            .appendingPathComponent("ceviz-capture-" + UUID().uuidString)
            .appendingPathExtension(request.format == "aac" ? "aac" : "m4a")
        do {
            try audio.write(to: file)
        } catch {
            return PhoneTranscript(error: NSLocalizedString("The recording could not be saved for transcription.", comment: "Phone transcription"))
        }
        defer { try? FileManager.default.removeItem(at: file) }
        let locale = locale(request.locale)
        do {
            if #available(iOS 26.0, *) {
                return try await analyze(file: file, locale: locale, hints: hints)
            }
            return try await recognizeOnDevice(file: file, locale: locale, hints: hints)
        } catch {
            return PhoneTranscript(error: String(format: NSLocalizedString("iPhone speech recognition failed: %@", comment: "Phone transcription"),
                                                 error.localizedDescription))
        }
    }

    /// For Settings, while the app is open: ask for permission and download this language's
    /// on-device model, so commands also work while the phone is locked.
    static func prepare(localeIdentifier: String? = nil) async -> Preparation {
        let locale = locale(localeIdentifier)
        let permitted = await authorized()
        if #available(iOS 26.0, *) {
            do {
                if let supported = await SpeechTranscriber.supportedLocale(equivalentTo: locale),
                   (try? await install(speechTranscriber(supported))) != nil {
                    return Preparation(ready: true, message: String(format: NSLocalizedString(
                        "Ready: %@ on this iPhone (Apple speech model).", comment: "Phone transcription"), name(supported)))
                }
                if let supported = await DictationTranscriber.supportedLocale(equivalentTo: locale) {
                    try await install(dictationTranscriber(supported))
                    return Preparation(ready: true, message: String(format: NSLocalizedString(
                        "Ready: %@ on this iPhone (Apple dictation model).", comment: "Phone transcription"), name(supported)))
                }
            } catch {
                return Preparation(ready: false, message: error.localizedDescription)
            }
            return Preparation(ready: false, message: noModel(locale))
        }
        guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.supportsOnDeviceRecognition else {
            return Preparation(ready: false, message: noModel(locale))
        }
        guard permitted else { return Preparation(ready: false, message: notAllowed) }
        return Preparation(ready: true, message: String(format: NSLocalizedString(
            "Ready: %@ on this iPhone (Apple dictation model).", comment: "Phone transcription"), name(locale)))
    }

    // MARK: - iOS 26

    /// SpeechTranscriber first; on a device or language it cannot serve, the dictation model.
    @available(iOS 26.0, *)
    private static func analyze(file: URL, locale: Locale, hints: [String]) async throws -> PhoneTranscript {
        var failure: Error?
        if let supported = await SpeechTranscriber.supportedLocale(equivalentTo: locale) {
            do {
                let transcriber = speechTranscriber(supported)
                try await install(transcriber)
                async let phrases = try transcriber.results.reduce(into: [String]()) { $0.append(String($1.text.characters)) }
                try await run(transcriber, file: file, hints: hints)
                return PhoneTranscript(text: joined(try await phrases), source: "speech-transcriber")
            } catch {
                failure = error
            }
        }
        if let supported = await DictationTranscriber.supportedLocale(equivalentTo: locale) {
            let transcriber = dictationTranscriber(supported)
            try await install(transcriber)
            async let phrases = try transcriber.results.reduce(into: [String]()) { $0.append(String($1.text.characters)) }
            try await run(transcriber, file: file, hints: hints)
            return PhoneTranscript(text: joined(try await phrases), source: "dictation-transcriber")
        }
        if let failure { throw failure }
        return PhoneTranscript(error: noModel(locale))
    }

    @available(iOS 26.0, *)
    private static func speechTranscriber(_ locale: Locale) -> SpeechTranscriber {
        // No volatile results: only the final text of each phrase is reported.
        SpeechTranscriber(locale: locale, transcriptionOptions: [], reportingOptions: [], attributeOptions: [])
    }

    @available(iOS 26.0, *)
    private static func dictationTranscriber(_ locale: Locale) -> DictationTranscriber {
        DictationTranscriber(locale: locale, contentHints: [], transcriptionOptions: [], reportingOptions: [],
                             attributeOptions: [])
    }

    /// Downloads the language's model from Apple once; it is shared with other apps afterwards.
    @available(iOS 26.0, *)
    private static func install(_ module: any SpeechModule) async throws {
        if let request = try await AssetInventory.assetInstallationRequest(supporting: [module]) {
            try await request.downloadAndInstall()
        }
    }

    @available(iOS 26.0, *)
    private static func run(_ module: any SpeechModule, file: URL, hints: [String]) async throws {
        let analyzer = SpeechAnalyzer(modules: [module], options: nil)
        if !hints.isEmpty {
            let context = AnalysisContext()
            context.contextualStrings = [.general: hints]
            try await analyzer.setContext(context)
        }
        if let end = try await analyzer.analyzeSequence(from: AVAudioFile(forReading: file)) {
            try await analyzer.finalizeAndFinish(through: end)
        } else {
            await analyzer.cancelAndFinishNow()
        }
    }

    // MARK: - iOS 16–25

    private static func recognizeOnDevice(file: URL, locale: Locale, hints: [String]) async throws -> PhoneTranscript {
        guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.supportsOnDeviceRecognition else {
            return PhoneTranscript(error: noModel(locale))
        }
        guard await authorized() else { return PhoneTranscript(error: notAllowed) }
        let request = SFSpeechURLRecognitionRequest(url: file)
        request.requiresOnDeviceRecognition = true  // never a network recognizer
        request.shouldReportPartialResults = false
        request.contextualStrings = hints
        let text: String = try await withCheckedThrowingContinuation { continuation in
            var finished = false
            _ = recognizer.recognitionTask(with: request) { result, error in
                guard !finished else { return }
                if let error {
                    finished = true
                    continuation.resume(throwing: error)
                } else if let result, result.isFinal {
                    finished = true
                    continuation.resume(returning: result.bestTranscription.formattedString)
                }
            }
        }
        return PhoneTranscript(text: joined([text]), source: "on-device-recognizer")
    }

    private static func authorized() async -> Bool {
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized: return true
        case .notDetermined:
            return await withCheckedContinuation { continuation in
                SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0 == .authorized) }
            }
        default: return false
        }
    }

    // MARK: - Text

    /// The Watch sends the device language ("tr_TR"); without one, the phone's language is used.
    private static func locale(_ identifier: String?) -> Locale {
        Locale(identifier: identifier?.isEmpty == false ? identifier! : Locale.current.identifier)
    }

    private static func joined(_ phrases: [String]) -> String {
        phrases.joined(separator: " ").split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }

    private static func name(_ locale: Locale) -> String {
        Locale.current.localizedString(forIdentifier: locale.identifier) ?? locale.identifier
    }

    private static func noModel(_ locale: Locale) -> String {
        String(format: NSLocalizedString("This iPhone has no on-device speech model for %@.", comment: "Phone transcription"),
               name(locale))
    }

    private static var notAllowed: String {
        NSLocalizedString("Allow Speech Recognition for Ceviz in iOS Settings.", comment: "Phone transcription")
    }
}
