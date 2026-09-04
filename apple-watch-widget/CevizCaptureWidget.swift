import SwiftUI
import WidgetKit

private struct CevizCaptureEntry: TimelineEntry {
    let date: Date
}

private struct CevizCaptureProvider: TimelineProvider {
    func placeholder(in context: Context) -> CevizCaptureEntry {
        CevizCaptureEntry(date: Date())
    }

    func getSnapshot(in context: Context, completion: @escaping (CevizCaptureEntry) -> Void) {
        completion(CevizCaptureEntry(date: Date()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<CevizCaptureEntry>) -> Void) {
        // A launcher has no job state to refresh or expose on the watch face.
        completion(Timeline(entries: [CevizCaptureEntry(date: Date())], policy: .never))
    }
}

private struct CevizCaptureWidgetView: View {
    @Environment(\.widgetFamily) private var family

    var body: some View {
        Group {
            if #available(watchOS 10.0, *) {
                content.containerBackground(for: .widget) { Color.black }
            } else {
                content
            }
        }
        // The app selects its capture screen; recording still needs an explicit tap.
        .widgetURL(URL(string: "ceviz-watch://capture"))
        .privacySensitive(false)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Open Ceviz voice capture"))
        .accessibilityHint(Text("Opens the microphone screen without starting a recording."))
    }

    @ViewBuilder
    private var content: some View {
        switch family {
        case .accessoryCircular:
            microphone
        case .accessoryCorner:
            microphone.widgetLabel { Text("Ceviz") }
        case .accessoryRectangular:
            HStack(spacing: 8) {
                Image(systemName: "mic.fill")
                    .font(.title2)
                    .widgetAccentable()
                VStack(alignment: .leading, spacing: 2) {
                    Text("Ceviz").font(.headline)
                    Text("Voice command").font(.caption)
                }
                .lineLimit(1)
            }
        default:
            Label("Ceviz", systemImage: "mic.fill")
        }
    }

    private var microphone: some View {
        ZStack {
            AccessoryWidgetBackground()
            Image(systemName: "mic.fill")
                .font(.title2)
                .widgetAccentable()
        }
    }
}

@main
struct CevizCaptureWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "CevizCapture", provider: CevizCaptureProvider()) { _ in
            CevizCaptureWidgetView()
        }
        .configurationDisplayName("Ceviz Voice")
        .description("Open Ceviz and start a voice command when you are ready.")
        .supportedFamilies([
            .accessoryCircular,
            .accessoryCorner,
            .accessoryInline,
            .accessoryRectangular,
        ])
    }
}
