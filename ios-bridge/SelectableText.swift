import SwiftUI
import UIKit

/// Read-only text the user can select part of and copy, with tappable links.
///
/// SwiftUI's `Text` with `.textSelection(.enabled)` only offers copying the whole text on iOS
/// and never turns URLs into links. Agent answers often carry a URL to open or a code to
/// copy, so they are shown in a non-editable `UITextView`: native selection handles, the
/// system Copy/Share menu, and URLs that open in the browser.
struct SelectableText: UIViewRepresentable {
    let text: String
    var font: UIFont = .systemFont(ofSize: 13.5)
    var color: Color = CVZ.textSub
    var lineSpacing: CGFloat = 6

    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false
        view.isSelectable = true
        view.isScrollEnabled = false
        view.backgroundColor = .clear
        view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0
        view.dataDetectorTypes = [.link]
        view.adjustsFontForContentSizeCategory = true
        view.linkTextAttributes = [
            .foregroundColor: UIColor(CVZ.accent),
            .underlineStyle: NSUnderlineStyle.single.rawValue,
        ]
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = lineSpacing
        let attributed = NSAttributedString(string: text, attributes: [
            .font: UIFontMetrics.default.scaledFont(for: font),
            .foregroundColor: UIColor(color),
            .paragraphStyle: paragraph,
        ])
        if view.attributedText != attributed {
            view.attributedText = attributed
        }
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        let fitted = uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
        return CGSize(width: width, height: ceil(fitted.height))
    }
}
