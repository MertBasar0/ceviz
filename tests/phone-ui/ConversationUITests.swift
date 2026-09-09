import XCTest

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
        // Host runner installs and opens ceviz://pair before XCTest starts.
        // Complete any normal Open prompt before terminating that first launch.
        app.activate()
        clearSystemPrompts()
        app.terminate()
        _ = try await fixture("reset?scenario=" + scenario)
        app.launchArguments = ["-AppleLanguages", "(\(language))", "-AppleLocale", language == "tr" ? "tr_TR" : "en_US"]
        app.launch()
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
