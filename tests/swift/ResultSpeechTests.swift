import Foundation

@main
struct ResultSpeechTests {
    static func main() {
        let link = "bağlantı"

        // A URL is not spelled out; markdown marks are not read as symbols.
        let oauth = SpokenSummary.text(
            from: "Zoho OAuth sayfası **hazır**: https://accounts.zoho.eu/oauth/v2/auth?scope=x&state=1 adresini aç.",
            linkWord: link)
        precondition(oauth == "Zoho OAuth sayfası hazır: bağlantı adresini aç.", oauth)
        let markdown = SpokenSummary.text(from: "## Durum\n- `needs_input` döndü", linkWord: link)
        precondition(markdown == "Durum - needs input döndü", markdown)
        let bare = SpokenSummary.text(from: "Taslak site (www.example.com/path) yayında.", linkWord: link)
        precondition(bare == "Taslak site (bağlantı) yayında.", bare)

        // Emoji are dropped; digits, '#', Turkish letters and plain arrows stay readable.
        let emoji = SpokenSummary.text(from: "Notepad açıldı ✅ 🎉 ⚠️ Sürüm 2026.10.20 #3 → çğıöşüİ", linkWord: link)
        precondition(emoji == "Notepad açıldı Sürüm 2026.10.20 3 → çğıöşüİ", emoji)
        precondition(SpokenSummary.text(from: "  \n ** ` \n", linkWord: link).isEmpty, "Nothing to read stays empty")

        // Long summaries end on a sentence, or on a whole word, within the limit.
        let sentences = String(repeating: "Bu cümle sonucu açıklıyor. ", count: 30)
        let cut = SpokenSummary.text(from: sentences, linkWord: link)
        precondition(cut.count <= SpokenSummary.maximumCharacters && cut.hasSuffix("."), cut)
        let words = String(repeating: "kelime ", count: 120)
        let wordCut = SpokenSummary.text(from: words, linkWord: link)
        precondition(wordCut.count <= SpokenSummary.maximumCharacters + 1 && wordCut.hasSuffix("kelime…"), wordCut)

        // The voice follows the summary's own language, else the user's first language.
        precondition(SpokenSummary.language(
            for: "Bilgisayarındaki Not Defteri açıldı ve boş belge yazmaya hazır.", preferredLanguages: ["en-US"]) == "tr")
        precondition(SpokenSummary.language(
            for: "The build passed and the full report is ready on your phone.", preferredLanguages: ["tr-TR"]) == "en")
        precondition(SpokenSummary.language(for: "", preferredLanguages: ["tr-TR"]) == "tr-TR")

        // Each job is read once, only while enabled; a late pending result expires.
        precondition(ResultSpeechPolicy.shouldAnnounce(jobID: "job-1", lastSpokenJobID: nil, enabled: true))
        precondition(!ResultSpeechPolicy.shouldAnnounce(jobID: "job-1", lastSpokenJobID: "job-1", enabled: true))
        precondition(ResultSpeechPolicy.shouldAnnounce(jobID: "job-2", lastSpokenJobID: "job-1", enabled: true))
        precondition(!ResultSpeechPolicy.shouldAnnounce(jobID: "job-2", lastSpokenJobID: nil, enabled: false))
        precondition(!ResultSpeechPolicy.shouldAnnounce(jobID: "", lastSpokenJobID: nil, enabled: true))
        let now = Date()
        precondition(ResultSpeechPolicy.pendingIsFresh(until: now.addingTimeInterval(5), now: now))
        precondition(!ResultSpeechPolicy.pendingIsFresh(until: now, now: now.addingTimeInterval(1)))
        print("result speech tests passed")
    }
}
