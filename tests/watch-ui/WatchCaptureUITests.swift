import XCTest
import WatchKit

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

    private func capture(_ name: String, in app: XCUIApplication) {
        capture(name)
        let controls = ["capture.primary", "capture.cancel", "capture.countdown"].map { identifier in
            let element = app.descendants(matching: .any).matching(identifier: identifier).firstMatch
            return element.exists
                ? "\(identifier): frame=\(element.frame), hittable=\(element.isHittable), label=\(element.label)"
                : "\(identifier): absent"
        }
        let attachment = XCTAttachment(string: "app.frame=\(app.frame)\n\(controls.joined(separator: "\n"))\n\(app.debugDescription)")
        attachment.name = "\(name)-accessibility"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func assertVisible(_ element: XCUIElement, in app: XCUIApplication, _ message: String) {
        XCTAssertTrue(element.waitForExistence(timeout: 8), message)
        XCTAssertTrue(element.isHittable, message)
        XCTAssertTrue(app.frame.contains(element.frame), message)
    }

    @discardableResult
    private func recordSystemTextSize(_ scenario: String) -> String {
        let category = WKInterfaceDevice.current().preferredContentSizeCategory
        let attachment = XCTAttachment(string: "scenario=\(scenario) preferredContentSizeCategory=\(category)")
        attachment.name = "system-text-size-\(scenario)"
        attachment.lifetime = .keepAlways
        add(attachment)
        return category
    }

    private func captureSettings(_ settings: XCUIApplication, _ name: String) {
        capture(name)
        let tree = settings.state == .notRunning ? "Settings is not running" : settings.debugDescription
        let attachment = XCTAttachment(string: tree)
        attachment.name = "\(name)-accessibility"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func openSettingsRow(_ title: String, in settings: XCUIApplication) {
        let row = settings.descendants(matching: .any).matching(NSPredicate(format: "label == %@", title)).firstMatch
        for step in 0...8 {
            if row.exists && row.isHittable {
                captureSettings(settings, "settings-found-\(title)")
                row.tap()
                return
            }
            guard step < 8 else { break }
            // Native video showed full-screen swipes fling past Display & Brightness.
            // A short slow drag with an end hold exposes overlapping, settled rows.
            guard settings.collectionViews.count == 1 else {
                captureSettings(settings, "settings-unexpected-list-\(title)")
                XCTFail("Expected the actual Settings collection before scrolling toward \(title)")
                return
            }
            let list = settings.collectionViews.element(boundBy: 0)
            let rowsBefore = list.cells.allElementsBoundByIndex.map { "\($0.identifier):\($0.label):\($0.frame)" }
            let start = list.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
            let end = list.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45))
            start.press(forDuration: 0.05, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)
            let rowsAfter = list.cells.allElementsBoundByIndex.map { "\($0.identifier):\($0.label):\($0.frame)" }
            guard (row.exists && row.isHittable) || rowsAfter != rowsBefore else {
                captureSettings(settings, "settings-no-scroll-progress-\(title)")
                XCTFail("The Settings list did not move toward \(title); refusing repeated unchanged gestures")
                return
            }
        }
        captureSettings(settings, "settings-missing-\(title)")
        XCTFail("The actual Settings UI did not expose a reachable \(title) row")
    }

    private func useLargerSystemText() {
        // Bundle ID verified from this runtime's simctl listapps, not an app fixture.
        let settings = XCUIApplication(bundleIdentifier: "com.apple.NanoSettings")
        settings.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        addTeardownBlock {
            if settings.state != .notRunning { settings.activate() }
            self.captureSettings(settings, "settings-final-state")
            settings.terminate()
        }
        settings.launch()
        captureSettings(settings, "settings-opened")
        openSettingsRow("Display & Brightness", in: settings)
        openSettingsRow("Text Size", in: settings)
        captureSettings(settings, "settings-text-size-before")
        // Display & Brightness also contains a slider. Never adjust it until the
        // Text Size page itself and its unique slider have been positively identified.
        XCTAssertTrue(settings.navigationBars["Text Size"].waitForExistence(timeout: 8),
                      "The Text Size page must be identified before changing its slider")
        XCTAssertEqual(settings.sliders.count, 1, "Expected one actual Text Size slider; inspect the attached Settings tree")
        let slider = settings.sliders.element(boundBy: 0)
        let originalPosition = slider.normalizedSliderPosition
        let originalCategory = recordSystemTextSize("before-larger-settings")
        addTeardownBlock {
            settings.activate()
            self.captureSettings(settings, "settings-before-restore")
            guard settings.navigationBars["Text Size"].exists, settings.sliders.count == 1 else {
                XCTFail("Settings no longer shows Text Size; refusing to adjust an unidentified control during restore")
                return
            }
            let restoredSlider = settings.sliders.element(boundBy: 0)
            restoredSlider.adjust(toNormalizedSliderPosition: originalPosition)
            let restored = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                WKInterfaceDevice.current().preferredContentSizeCategory == originalCategory
            }, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [restored], timeout: 8), .completed,
                           "The original system text-size category must be restored")
            XCTAssertEqual(restoredSlider.normalizedSliderPosition, originalPosition, accuracy: 0.05)
            self.recordSystemTextSize("restored-settings")
            self.captureSettings(settings, "settings-restored")
        }
        XCTAssertLessThan(originalPosition, 0.95, "The device is already at maximum text size; a larger scenario cannot be claimed")
        slider.adjust(toNormalizedSliderPosition: 1)
        let changed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            WKInterfaceDevice.current().preferredContentSizeCategory != originalCategory
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [changed], timeout: 8), .completed,
                       "Moving Settings must change the public system text-size category")
        XCTAssertGreaterThanOrEqual(slider.normalizedSliderPosition, 0.95,
                                    "The actual Text Size slider must reach its maximum")
        recordSystemTextSize("larger-settings")
        captureSettings(settings, "settings-text-size-larger")
    }

    private func checkReadyScreenEnglish() {
        let app = launch("en")
        defer { app.terminate() }
        // Text selectors also exercise the previous build without new identifiers.
        XCTAssertTrue(app.staticTexts["Ready to listen"].waitForExistence(timeout: 15))
        capture("ready-en", in: app)
        assertVisible(app.staticTexts["Up to 15 seconds"], in: app,
                      "15-second limit must be fully visible without scrolling")
        assertVisible(app.buttons["Start recording"], in: app, "Microphone must be reachable without scrolling")
        let offline = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Phone offline")).firstMatch
        if offline.exists {
            assertVisible(offline, in: app, "A displayed Phone offline label must not be clipped by the microphone action")
            XCTAssertFalse(offline.frame.intersects(app.buttons["Start recording"].frame),
                           "The microphone action must not cover the Phone offline label")
        }
    }

    private func checkRecordAndDiscardBothLanguages() {
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
            // Capture the frame before the real 15s deadline; detailed AX queries
            // can outlast recording on a loaded runner. Inspect AX after discard.
            capture("recording-\(language)")
            app.buttons["capture.cancel"].tap()
            assertVisible(app.staticTexts["capture.durationLimit"], in: app, "Discard must return to ready")
            let discarded = app.staticTexts[language == "tr" ? "Kayıt silindi" : "Discarded"]
            assertVisible(discarded, in: app, "The complete discard confirmation must be visible without scrolling")
            XCTAssertFalse(discarded.frame.intersects(start.frame),
                           "The microphone action must not cover the discard confirmation")
            capture("discarded-\(language)", in: app)
        }
    }

    func testReadyScreenEnglish() {
        recordSystemTextSize("device-default-ready")
        checkReadyScreenEnglish()
    }

    func testRecordAndDiscardBothLanguages() {
        recordSystemTextSize("device-default-recording")
        checkRecordAndDiscardBothLanguages()
    }

    func testLargerTextReadyAndDiscardBothLanguages() {
        useLargerSystemText()
        checkReadyScreenEnglish()
        checkRecordAndDiscardBothLanguages()
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
        recordSystemTextSize("device-default-finish")
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
