import Foundation
import NaturalLanguage

/// What the Watch reads aloud for a result, and when. Kept free of audio APIs so it can be tested.
enum SpokenSummary {
    /// About 30 seconds of speech; the rest stays on screen and on iPhone.
    static let maximumCharacters = 400

    /// The summary as speech, followed by the answers when the result asks the user to choose.
    static func text(from summary: String, linkWord: String, choices: [String] = [], optionsWord: String = "") -> String {
        let options = choices.map { cleaned($0, linkWord: linkWord) }.filter { !$0.isEmpty }
        guard !options.isEmpty else { return shortened(cleaned(summary, linkWord: linkWord), limit: maximumCharacters) }
        // The answers are the point of a question: they stay whole and the summary gives way.
        // Each answer ends with a stop so "Yes, delete" and "No" are heard as separate answers.
        let tail = "\(optionsWord): " + options.map { option in
            option.last.map { ".!?".contains($0) } == true ? option : option + "."
        }.joined(separator: " ")
        let head = shortened(cleaned(summary, linkWord: linkWord),
                             limit: max(maximumCharacters - tail.count - 1, maximumCharacters / 4))
        return head.isEmpty ? tail : "\(head) \(tail)"
    }

    /// A synthesizer reads markdown marks as symbols, spells a URL out character by character
    /// and names each emoji, so those are dropped or replaced.
    private static func cleaned(_ summary: String, linkWord: String) -> String {
        var text = summary.replacingOccurrences(
            of: #"(https?://|www\.)[^\s)\]]+"#, with: linkWord, options: [.regularExpression, .caseInsensitive])
        text = text.replacingOccurrences(of: "_", with: " ")
        text = text.replacingOccurrences(of: #"[*`#>|~]+"#, with: "", options: .regularExpression)
        text = String(String.UnicodeScalarView(text.unicodeScalars.filter { !isEmoji($0) }))
        return text.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// The language to speak `text` in: the one it is written in, else the user's first language.
    static func language(for text: String, preferredLanguages: [String]) -> String? {
        let recognizer = NLLanguageRecognizer()
        recognizer.processString(text)
        if let best = recognizer.languageHypotheses(withMaximum: 1).first, best.value >= 0.5 {
            return best.key.rawValue
        }
        return preferredLanguages.first
    }

    private static func isEmoji(_ scalar: Unicode.Scalar) -> Bool {
        // Digits, '#' and '*' count as emoji (keycap bases); keep everything below the emoji blocks.
        if scalar.value == 0x200D || scalar.value == 0xFE0F { return true }
        return scalar.properties.isEmojiPresentation || (scalar.properties.isEmoji && scalar.value > 0x238C)
    }

    private static func shortened(_ text: String, limit: Int) -> String {
        guard text.count > limit else { return text }
        let head = String(text.prefix(limit))
        // End on a finished sentence when one ends in the second half, else on a whole word.
        if let end = head.lastIndex(where: { ".!?".contains($0) }),
           head.distance(from: head.startIndex, to: end) >= limit / 2 {
            return String(head[...end])
        }
        let words = head.split(separator: " ").dropLast()
        return words.joined(separator: " ") + "…"
    }
}

/// When a result is read without being asked: once per job, only while enabled.
enum ResultSpeechPolicy {
    /// A result that arrives while the app is away is still read if the app opens this soon:
    /// watchOS returns to the app on a wrist raise within 2 minutes by default.
    static let pendingLifetime: TimeInterval = 120

    static func shouldAnnounce(jobID: String, lastSpokenJobID: String?, enabled: Bool) -> Bool {
        enabled && !jobID.isEmpty && jobID != lastSpokenJobID
    }

    static func pendingIsFresh(until deadline: Date, now: Date) -> Bool {
        now < deadline
    }
}
