import XCTest

/// Real taps against the unconfigured simulator app. No capture/result fixtures.
/// This does not prove WatchConnectivity file delivery or microphone quality.
final class WatchCaptureUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    private func launch(_ language: String) -> XCUIApplication {
        let app = XCUIApplication(bundleIdentifier: "com.mertbasar.cevizwatch.watchkitapp")
        app.launchArguments = ["-AppleLanguages", "(\(language))", "-AppleLocale", language == "tr" ? "tr_TR" : "en_US"]
        app.launch()
        return app
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func assertVisible(_ element: XCUIElement, in app: XCUIApplication, _ message: String) {
        XCTAssertTrue(element.waitForExistence(timeout: 8), message)
        XCTAssertTrue(element.isHittable, message)
        XCTAssertTrue(app.frame.contains(element.frame), message)
    }

    func testReadyScreenEnglish() {
        let app = launch("en")
        defer { app.terminate() }
        // Text selectors also exercise the previous build without new identifiers.
        XCTAssertTrue(app.staticTexts["Ready to listen"].waitForExistence(timeout: 15))
        capture("ready-en")
        assertVisible(app.staticTexts["Up to 15 seconds"], in: app,
                      "15-second limit must be fully visible without scrolling")
        assertVisible(app.buttons["Start recording"], in: app, "Microphone must be reachable without scrolling")
    }

    func testRecordAndDiscardBothLanguages() {
        for language in ["en", "tr"] {
            let app = launch(language)
            defer { app.terminate() }
            let start = app.buttons["capture.primary"]
            XCTAssertTrue(start.waitForExistence(timeout: 15))
            start.tap()
            let countdown = app.staticTexts["capture.countdown"]
            let cancel = app.buttons["capture.cancel"]
            assertVisible(countdown, in: app, "Remaining time must be readable")
            assertVisible(cancel, in: app, "Discard must stay reachable")
            assertVisible(app.buttons["capture.primary"], in: app, "Send must stay reachable")
            for button in [cancel, start] {
                XCTAssertGreaterThanOrEqual(button.frame.width, 44)
                XCTAssertGreaterThanOrEqual(button.frame.height, 44)
                XCTAssertFalse(button.frame.intersects(countdown.frame), "Action space must not cover the countdown")
            }
            capture("recording-\(language)")
            app.buttons["capture.cancel"].tap()
            assertVisible(app.staticTexts["capture.durationLimit"], in: app, "Discard must return to ready")
            capture("discarded-\(language)")
        }
    }

    private func assertRetainedResult(in app: XCUIApplication) {
        let accepted = ["queued", "running", "completed", "blocked", "needsInput", "resultReady"]
        let retained = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            accepted.contains { app.descendants(matching: .any).matching(identifier: "capture.result.\($0)").firstMatch.exists }
        }, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [retained], timeout: 45), .completed,
                       "Capture must end in a saved request or received result, not disappear")
        XCTAssertFalse(app.descendants(matching: .any).matching(identifier: "capture.result.unknown").firstMatch.exists)
        XCTAssertFalse(app.descendants(matching: .any).matching(identifier: "capture.result.failed").firstMatch.exists)
        XCTAssertFalse(app.staticTexts["Recording too long. Please record a shorter request."].exists)
    }

    func testManualAndAutomaticFinishRetainRecording() {
        let app = launch("en")
        defer { app.terminate() }
        let start = app.buttons["capture.primary"]
        XCTAssertTrue(start.waitForExistence(timeout: 15))
        start.tap()
        let countdown = app.staticTexts["capture.countdown"]
        assertVisible(countdown, in: app, "Manual capture countdown must be readable")
        capture("manual-recording")
        let nineSeconds = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            guard countdown.exists, let first = countdown.label.split(separator: " ").first,
                  let remaining = Int(first) else { return false }
            return (4...6).contains(remaining)
        }, object: countdown)
        XCTAssertEqual(XCTWaiter.wait(for: [nineSeconds], timeout: 15), .completed,
                       "Exercise the reported failure boundary: send with six seconds remaining")
        app.buttons["capture.primary"].tap()
        assertRetainedResult(in: app)
        capture("manual-finished-retained")

        let canRecord = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: start)
        XCTAssertEqual(XCTWaiter.wait(for: [canRecord], timeout: 45), .completed)
        let began = ProcessInfo.processInfo.systemUptime
        start.tap()
        let recording = app.staticTexts["capture.recording"]
        XCTAssertTrue(recording.waitForExistence(timeout: 8))
        capture("automatic-recording")
        let stopped = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: recording)
        XCTAssertEqual(XCTWaiter.wait(for: [stopped], timeout: 25), .completed)
        XCTAssertGreaterThanOrEqual(ProcessInfo.processInfo.systemUptime - began, 14,
                                    "A full capture must not stop substantially before 15 seconds")
        assertRetainedResult(in: app)
        capture("automatic-finished-retained")
    }
}
