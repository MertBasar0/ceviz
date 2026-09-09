import XCTest
import UIKit

/// Real Ceviz screens and normal pairing; the host fixture replaces only the
/// external Gateway boundary. No launch flag changes production UI or state.
@MainActor
final class ConversationUITests: XCTestCase {
    private let app = XCUIApplication(bundleIdentifier: "com.mertbasar.cevizwatch")
    private let fixtureURL = "http://127.0.0.1:18790"
    private let fixtureToken = "ceviz-phone-ui-test-only"
    private let mainKey = "agent:planner:weekend"
    private let busyKey = "agent:builder:review"

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    private func element(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }

    private func capture(_ name: String) {
        let picture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        picture.name = name
        picture.lifetime = .keepAlways
        add(picture)
        let tree = XCTAttachment(string: app.debugDescription)
        tree.name = name + "-accessibility"
        tree.lifetime = .keepAlways
        add(tree)
    }

    private func fixture(_ path: String) async throws -> [String: Any] {
        var request = URLRequest(url: URL(string: fixtureURL + "/__fixture/" + path)!)
        request.setValue("Bearer " + fixtureToken, forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 5
        let (data, response) = try await URLSession.shared.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private func clearSystemPrompts() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        for _ in 0..<3 {
            guard springboard.alerts.firstMatch.waitForExistence(timeout: 1) else { return }
            let alert = springboard.alerts.firstMatch
            // These belong only to this fresh simulator's normal pairing and
            // permission flow. Never dismiss an unknown alert blindly.
            let allowed = ["Open", "Aç", "Don’t Allow", "Don't Allow", "İzin Verme", "Allow", "İzin Ver", "OK", "Tamam"]
            guard let button = allowed.map({ alert.buttons[$0] }).first(where: { $0.exists }) else {
                capture("unexpected-system-alert")
                XCTFail("Unexpected system alert requires inspection")
                return
            }
            button.tap()
        }
    }

    private func prepare(_ scenario: String = "normal", language: String = "en") async throws {
        guard #available(iOS 16.4, *) else {
            throw XCTSkip("Normal per-test pairing requires XCTest URL opening on iOS 16.4 or later")
        }
        // Host runner installs and opens ceviz://pair before XCTest starts.
        // Complete any normal Open prompt before terminating that first launch.
        app.activate()
        clearSystemPrompts()
        app.terminate()
        let reset = try await fixture("reset?scenario=" + scenario)
        let pairingToken = try XCTUnwrap(reset["pairing_token"] as? String)
        app.launchArguments = ["-AppleLanguages", "(\(language))", "-AppleLocale", language == "tr" ? "tr_TR" : "en_US"]
        app.launch()
        // A normal credential change isolates durable pending deliveries. Never
        // erase the app's store or bypass pairing to reset a UI test.
        var pairing = URLComponents()
        pairing.scheme = "ceviz"
        pairing.host = "pair"
        pairing.queryItems = [URLQueryItem(name: "u", value: fixtureURL),
                              URLQueryItem(name: "t", value: pairingToken),
                              URLQueryItem(name: "m", value: "relay")]
        app.open(try XCTUnwrap(pairing.url))
        clearSystemPrompts()
        XCTAssertTrue(element("conversations.open").waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts["DEMO"].exists, "Normal pairing must succeed; demo content is not integration proof")
        element("conversations.open").tap()
        XCTAssertTrue(element("conversations.row." + mainKey).waitForExistence(timeout: 15))
    }

    private func open(_ key: String) {
        let row = element("conversations.row." + key)
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        XCTAssertTrue(row.isHittable)
        row.tap()
        XCTAssertTrue(element("conversation.target").waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["The riverside route is quieter."].waitForExistence(timeout: 10))
    }

    private func send(_ text: String) {
        let draft = element("conversation.draft")
        XCTAssertTrue(draft.waitForExistence(timeout: 10))
        XCTAssertTrue(draft.isEnabled)
        draft.tap()
        draft.typeText(text)
        let send = element("conversation.send")
        XCTAssertTrue(send.isEnabled)
        XCTAssertTrue(send.isHittable, "Send stays reachable above the keyboard")
        XCTAssertTrue(app.frame.contains(send.frame))
        send.tap()
    }

    private func assertEmptyDraft() {
        let draft = element("conversation.draft")
        XCTAssertTrue(draft.waitForExistence(timeout: 10))
        let text = draft.value as? String
        XCTAssertTrue(text == nil || text == "" || text == "Message this conversation",
                      "The new composer must not contain the earlier private message text")
    }

    private func waitForStatus(_ label: String) {
        let status = element("conversation.status")
        let expected = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            status.exists && status.label == label
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 20), .completed)
    }

    private func assertSends(_ count: Int, key: String? = nil) async throws {
        let state = try await fixture("state")
        let sends = try XCTUnwrap(state["send_calls"] as? [[String: Any]])
        XCTAssertEqual(sends.count, count)
        if let key, let sent = sends.last {
            XCTAssertEqual(sent["sessionKey"] as? String, key)
            XCTAssertEqual(sent["agentId"] as? String, key.split(separator: ":")[1].description)
            XCTAssertEqual(sent["queueMode"] as? String, "followup")
            XCTAssertNotNil(sent["expectedLeafEntryId"])
        }
        let attachment = XCTAttachment(data: try JSONSerialization.data(withJSONObject: state, options: .prettyPrinted),
                                      uniformTypeIdentifier: "public.json")
        attachment.name = "fixture-gateway-evidence"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func luminance(of element: XCUIElement, named name: String) throws -> (background: Double, foreground: Double) {
        XCTAssertTrue(element.waitForExistence(timeout: 10), name)
        XCTAssertTrue(element.isHittable, name)
        let shot = element.screenshot()
        let picture = XCTAttachment(screenshot: shot)
        picture.name = name
        picture.lifetime = .keepAlways
        add(picture)
        let image = try XCTUnwrap(shot.image.cgImage)
        var pixels = [UInt8](repeating: 0, count: image.width * image.height * 4)
        try pixels.withUnsafeMutableBytes { buffer in
            let context = try XCTUnwrap(CGContext(
                data: buffer.baseAddress, width: image.width, height: image.height,
                bitsPerComponent: 8, bytesPerRow: image.width * 4,
                space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue
            ))
            context.draw(image, in: CGRect(x: 0, y: 0, width: CGFloat(image.width), height: CGFloat(image.height)))
        }
        func linear(_ value: UInt8) -> Double {
            let channel = Double(value) / 255
            return channel <= 0.04045 ? channel / 12.92 : pow((channel + 0.055) / 1.055, 2.4)
        }
        let levels = stride(from: 0, to: pixels.count, by: 4).map { index in
            0.2126 * linear(pixels[index]) + 0.7152 * linear(pixels[index + 1]) + 0.0722 * linear(pixels[index + 2])
        }.sorted()
        // Text occupies a minority of each observed element. The median samples
        // its background; the 99th percentile ignores isolated antialias pixels.
        let result = (background: levels[levels.count / 2], foreground: levels[levels.count * 99 / 100])
        let report = XCTAttachment(string: "element=\(name) frame=\(element.frame) background=\(result.background) foreground=\(result.foreground) contrast=\((result.foreground + 0.05) / (result.background + 0.05))")
        report.name = name + "-luminance"
        report.lifetime = .keepAlways
        add(report)
        return result
    }

    func testConversationAppearanceStaysReadableOnLightAndDarkPhones() async throws {
        guard #available(iOS 16.4, *) else {
            throw XCTSkip("Changing actual device appearance requires iOS 16.4 or later")
        }
        let device = XCUIDevice.shared
        let originalAppearance = device.appearance
        defer { device.appearance = originalAppearance }
        for darkPhone in [false, true] {
            device.appearance = darkPhone ? .dark : .light
            let mode = darkPhone ? "dark-phone" : "light-phone"
            try await prepare()
            capture("phone-conversations-list-" + mode)
            open(mainKey)
            capture("phone-conversation-empty-" + mode)
            let title = try luminance(of: app.navigationBars["Conversation"].staticTexts["Conversation"], named: "navigation-title-" + mode)
            XCTAssertLessThan(title.background, 0.2, "System navigation must match the app's dark palette")
            XCTAssertGreaterThanOrEqual((title.foreground + 0.05) / (title.background + 0.05), 4.5,
                                       "The navigation title must be readable against its actual background")
            element("conversation.draft").tap()
            XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10))
            capture("phone-conversation-keyboard-" + mode)
            let keyboard = try luminance(of: app.keyboards.firstMatch, named: "keyboard-" + mode)
            XCTAssertLessThan(keyboard.background, 0.2, "The system keyboard must follow the app's dark appearance")
            try await assertSends(0)
        }
    }

    func testUncertainDeliverySurvivesAppAndHelperRestartWithoutResending() async throws {
        try await prepare("uncertain")
        open(mainKey)
        send("Please compare the two options.")
        let uncertain = "Delivery is not confirmed. Check the conversation before sending again."
        waitForStatus(uncertain)
        try await assertSends(1, key: mainKey)
        let before = try await fixture("state")
        let generation = try XCTUnwrap(before["helper_generation"] as? Int)
        app.terminate()
        let restarted = try await fixture("restart_helper")
        XCTAssertEqual(restarted["helper_generation"] as? Int, generation + 1)
        XCTAssertEqual(restarted["pairing_token"] as? String, before["pairing_token"] as? String)
        // Preserve pairing, Gateway state and the app's durable metadata. A fresh
        // fixture/credential would hide the duplicate-submission failure.
        app.launch()
        clearSystemPrompts()
        XCTAssertTrue(element("conversations.open").waitForExistence(timeout: 15))
        element("conversations.open").tap()
        open(mainKey)
        waitForStatus(uncertain)
        assertEmptyDraft()
        XCTAssertFalse(element("conversation.send").isEnabled)
        capture("phone-conversation-uncertain-after-restart-en")
        try await assertSends(1, key: mainKey)
        element("conversation.check").tap()
        waitForStatus(uncertain)
        XCTAssertFalse(element("conversation.send").isEnabled)
        try await assertSends(1, key: mainKey)
    }

    func testExplicitReviewUnlocksOnlyANewMessageAndSurvivesRestart() async throws {
        try await prepare("uncertain")
        open(mainKey)
        let originalText = "Please compare the two options."
        send(originalText)
        let uncertain = "Delivery is not confirmed. Check the conversation before sending again."
        waitForStatus(uncertain)
        try await assertSends(1, key: mainKey)
        let before = try await fixture("state")
        let originalSends = try XCTUnwrap(before["send_calls"] as? [[String: Any]])
        let originalRequest = try XCTUnwrap(originalSends.first?["idempotencyKey"] as? String)

        let review = element("conversation.review")
        XCTAssertTrue(review.waitForExistence(timeout: 10))
        review.tap()
        let confirm = app.buttons["I reviewed it — start a new message"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Start a new message after reviewing?"].exists)
        capture("phone-conversation-review-confirmation-en")
        app.buttons["Cancel"].tap()
        waitForStatus(uncertain)
        XCTAssertEqual(element("conversation.draft").value as? String, originalText)
        XCTAssertFalse(element("conversation.send").isEnabled)
        try await assertSends(1, key: mainKey)

        review.tap()
        XCTAssertTrue(confirm.waitForExistence(timeout: 10))
        confirm.tap()
        let unlocked = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"),
                                                 object: element("conversation.draft"))
        XCTAssertEqual(XCTWaiter.wait(for: [unlocked], timeout: 10), .completed)
        assertEmptyDraft()
        XCTAssertFalse(element("conversation.status").exists)
        XCTAssertFalse(element("conversation.send").isEnabled, "An empty new draft cannot be submitted")
        try await assertSends(1, key: mainKey)

        // Review is a durable local decision; neither relaunch nor confirmation
        // may replay the earlier request or discard the helper's replay guard.
        app.terminate()
        app.launch()
        clearSystemPrompts()
        XCTAssertTrue(element("conversations.open").waitForExistence(timeout: 15))
        element("conversations.open").tap()
        open(mainKey)
        assertEmptyDraft()
        XCTAssertTrue(element("conversation.draft").isEnabled)
        XCTAssertFalse(element("conversation.status").exists)
        XCTAssertFalse(element("conversation.send").isEnabled)
        capture("phone-conversation-reviewed-after-restart-en")
        try await assertSends(1, key: mainKey)
        let restored = try await fixture("state")
        XCTAssertEqual(restored["pairing_token"] as? String, before["pairing_token"] as? String)

        let newText = "Show the walking time for the shorter route."
        send(newText)
        waitForStatus(uncertain)
        try await assertSends(2, key: mainKey)
        let after = try await fixture("state")
        let sends = try XCTUnwrap(after["send_calls"] as? [[String: Any]])
        let newRequest = try XCTUnwrap(sends.last?["idempotencyKey"] as? String)
        XCTAssertNotEqual(newRequest, originalRequest, "Only the newly typed message gets a fresh submission identity")
        XCTAssertEqual(sends.first?["message"] as? String, originalText)
        XCTAssertEqual(sends.last?["message"] as? String, newText)
        XCTAssertTrue(sends.allSatisfy { ($0["sessionKey"] as? String) == mainKey && ($0["sessionId"] as? String) == "planner-session" },
                      "Both deliberate sends must target the exact selected conversation")
    }

    func testListHistoryAndExactConversationSend() async throws {
        try await prepare()
        let first = element("conversations.row." + mainKey)
        let second = element("conversations.row." + busyKey)
        let unnamed = element("conversations.row.agent:planner:untitled-thread")
        XCTAssertTrue(second.exists && unnamed.exists)
        XCTAssertLessThan(first.frame.minY, second.frame.minY)
        XCTAssertLessThan(second.frame.minY, unnamed.frame.minY)
        capture("phone-conversations-list-en")

        let more = element("conversations.more")
        for _ in 0..<3 where !more.isHittable { app.swipeUp() }
        XCTAssertTrue(more.isHittable)
        more.tap()
        XCTAssertTrue(element("conversations.row.agent:planner:earlier").waitForExistence(timeout: 10))
        for _ in 0..<3 where !first.isHittable { app.swipeDown() }
        open(mainKey)
        XCTAssertEqual(element("conversation.target").label, "Weekend plan")
        capture("phone-conversation-history-en")
        let earlier = element("conversation.earlier")
        XCTAssertTrue(earlier.waitForExistence(timeout: 10))
        for _ in 0..<5 where !earlier.isHittable { app.scrollViews.firstMatch.swipeDown() }
        XCTAssertTrue(earlier.isHittable)
        earlier.tap()
        XCTAssertTrue(app.staticTexts["Earlier route notes."].waitForExistence(timeout: 10))
        send("Show the shorter route.")
        waitForStatus("Run finished — review the conversation.")
        capture("phone-conversation-response-en")
        try await assertSends(1, key: mainKey)
    }

    func testBusyConversationQueuesWithoutDuplicateSubmission() async throws {
        try await prepare("queued")
        open(busyKey)
        XCTAssertTrue(element("conversation.busy").exists)
        capture("phone-conversation-busy-en")
        send("Summarize the checks when ready.")
        waitForStatus("Queued")
        XCTAssertFalse(element("conversation.send").isEnabled)
        element("conversation.check").tap()
        waitForStatus("Queued")
        capture("phone-conversation-queued-en")
        try await assertSends(1, key: busyKey)
    }

    func testUncertainDeliveryRetainsDraftAndNeverResendsOnCheck() async throws {
        try await prepare("uncertain")
        open(mainKey)
        let text = "Please compare the two options."
        send(text)
        waitForStatus("Delivery is not confirmed. Check the conversation before sending again.")
        XCTAssertEqual(element("conversation.draft").value as? String, text)
        XCTAssertFalse(element("conversation.send").isEnabled)
        app.navigationBars["Conversation"].buttons.firstMatch.tap()
        XCTAssertTrue(element("conversations.row." + mainKey).waitForExistence(timeout: 10))
        open(mainKey)
        waitForStatus("Delivery is not confirmed. Check the conversation before sending again.")
        XCTAssertEqual(element("conversation.draft").value as? String, text,
                       "Navigation must retain the same unconfirmed message, not create a new draft")
        XCTAssertFalse(element("conversation.send").isEnabled)
        try await assertSends(1, key: mainKey)
        element("conversation.check").tap()
        waitForStatus("Delivery is not confirmed. Check the conversation before sending again.")
        capture("phone-conversation-uncertain-en")
        try await assertSends(1, key: mainKey)
    }

    func testResetConversationRejectsOldTargetBeforeSending() async throws {
        try await prepare("reset")
        open(mainKey)
        let text = "Continue the plan."
        send(text)
        XCTAssertTrue(element("conversation.submissionError").waitForExistence(timeout: 10))
        XCTAssertEqual(element("conversation.draft").value as? String, text)
        capture("phone-conversation-reset-error-en")
        try await assertSends(0)
    }

    func testFailedRunIsNotShownAsCompleted() async throws {
        try await prepare("failed")
        open(mainKey)
        send("Check the route details.")
        waitForStatus("The response could not be completed.")
        capture("phone-conversation-failed-en")
        try await assertSends(1, key: mainKey)
    }

    func testTurkishListAndHistoryStayReadable() async throws {
        try await prepare(language: "tr")
        capture("phone-conversations-list-tr")
        open(mainKey)
        let title = element("conversation.target")
        let draft = element("conversation.draft")
        XCTAssertTrue(app.frame.contains(title.frame))
        XCTAssertTrue(draft.isHittable)
        XCTAssertFalse(title.frame.intersects(draft.frame))
        capture("phone-conversation-history-tr")
        try await assertSends(0)
    }
}
