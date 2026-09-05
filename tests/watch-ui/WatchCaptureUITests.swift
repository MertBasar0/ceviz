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

    private func recordTestRunnerTextCategory(_ scenario: String) {
        let category = WKInterfaceDevice.current().preferredContentSizeCategory
        let attachment = XCTAttachment(string: "scenario=\(scenario) testRunnerPreferredContentSizeCategory=\(category) diagnosticOnly=true; not the Settings or Ceviz process")
        attachment.name = "test-runner-text-category-\(scenario)"
        attachment.lifetime = .keepAlways
        add(attachment)
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

    private func openSettingsTextSize(in settings: XCUIApplication) -> Bool {
        if settings.navigationBars["Text Size"].exists { return true }
        if settings.navigationBars["Settings"].exists {
            openSettingsRow("Display & Brightness", in: settings)
        }
        guard settings.navigationBars["Display & Brightness"].exists else {
            captureSettings(settings, "settings-unexpected-navigation")
            XCTFail("Settings must show an observed page before navigating to Text Size")
            return false
        }
        openSettingsRow("Text Size", in: settings)
        guard settings.navigationBars["Text Size"].waitForExistence(timeout: 8) else {
            captureSettings(settings, "settings-text-size-not-opened")
            XCTFail("The actual Text Size page did not open")
            return false
        }
        return true
    }

    private func setSettingsTextSize(_ target: CGFloat, in settings: XCUIApplication) -> Bool {
        // This native control exposes the AA buttons as one slider. Tap its
        // observed left/right letters; a best-effort drag restored the wrong step.
        for step in 0...8 {
            guard settings.navigationBars["Text Size"].exists, settings.sliders.count == 1 else {
                captureSettings(settings, "settings-unidentified-text-size")
                XCTFail("Refusing to change text size without its page and unique control")
                return false
            }
            let slider = settings.sliders.element(boundBy: 0)
            let position = slider.normalizedSliderPosition
            guard position.isFinite, (0...1).contains(position),
                  slider.isHittable, settings.frame.contains(slider.frame) else {
                captureSettings(settings, "settings-unreachable-text-size")
                XCTFail("The actual Text Size control must be readable and fully reachable")
                return false
            }
            if abs(position - target) <= 0.01 { return true }
            guard step < 8 else { break }
            let increasing = position < target
            slider.coordinate(withNormalizedOffset: CGVector(dx: increasing ? 0.85 : 0.15, dy: 0.5)).tap()
            let changed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                slider.exists && abs(slider.normalizedSliderPosition - position) > 0.01
            }, object: slider)
            guard XCTWaiter.wait(for: [changed], timeout: 8) == .completed else {
                captureSettings(settings, "settings-text-size-no-progress")
                XCTFail("A letter tap did not change the actual Text Size value")
                return false
            }
            let next = slider.normalizedSliderPosition
            let movedTowardTarget = increasing ? (next > position && next <= target + 0.01)
                                             : (next < position && next >= target - 0.01)
            guard movedTowardTarget else {
                captureSettings(settings, "settings-text-size-wrong-step")
                XCTFail("The Text Size value moved away from or past its target")
                return false
            }
        }
        captureSettings(settings, "settings-text-size-step-limit")
        XCTFail("The bounded letter taps did not reach the actual Text Size target")
        return false
    }

    private func useLargerSystemText() {
        let originalAppText = checkReadyScreenEnglish("ready-before-larger")
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
        guard openSettingsTextSize(in: settings) else { return }
        captureSettings(settings, "settings-text-size-before")
        // Display & Brightness also contains a slider. Never adjust it until the
        // Text Size page itself and its unique slider have been positively identified.
        XCTAssertTrue(settings.navigationBars["Text Size"].waitForExistence(timeout: 8),
                      "The Text Size page must be identified before changing its slider")
        XCTAssertEqual(settings.sliders.count, 1, "Expected one actual Text Size slider; inspect the attached Settings tree")
        let slider = settings.sliders.element(boundBy: 0)
        let originalPosition = slider.normalizedSliderPosition
        let preview = settings.staticTexts["Apps that support Dynamic Type will adjust to your preferred reading size."]
        XCTAssertTrue(preview.waitForExistence(timeout: 8))
        let originalPreview = preview.frame.size
        XCTAssertGreaterThan(originalPreview.height, 0)
        recordTestRunnerTextCategory("before-larger-settings")
        addTeardownBlock {
            settings.activate()
            self.captureSettings(settings, "settings-before-restore")
            guard self.setSettingsTextSize(originalPosition, in: settings) else { return }
            let livePosition = settings.sliders.element(boundBy: 0).normalizedSliderPosition
            let livePreview = preview.exists ? preview.frame.size : nil
            self.captureSettings(settings, "settings-restored-live")
            // Keep the live discrepancy as evidence, then compare like lifecycles:
            // the baseline and this measurement both use a freshly launched Settings.
            settings.launch()
            self.captureSettings(settings, "settings-restored-relaunched")
            guard self.openSettingsTextSize(in: settings) else { return }
            XCTAssertEqual(settings.sliders.count, 1, "The fresh Text Size page must expose its unique control")
            let coldPosition = settings.sliders.element(boundBy: 0).normalizedSliderPosition
            let coldPreview = settings.staticTexts["Apps that support Dynamic Type will adjust to your preferred reading size."]
            let restored = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                coldPreview.exists && abs(coldPreview.frame.width - originalPreview.width) <= 1 &&
                    abs(coldPreview.frame.height - originalPreview.height) <= 1
            }, object: coldPreview)
            let restoreResult = XCTWaiter.wait(for: [restored], timeout: 8)
            let restoredPreview = coldPreview.exists ? coldPreview.frame.size : nil
            self.captureSettings(settings, "settings-restored-cold")
            self.recordTestRunnerTextCategory("restored-settings")
            let restoredAppText = self.checkReadyScreenEnglish("ready-restored")
            let measurements = XCTAttachment(string: "original position=\(originalPosition) preview=\(originalPreview) app=\(originalAppText)\nlive position=\(livePosition) preview=\(String(describing: livePreview))\ncold position=\(coldPosition) preview=\(String(describing: restoredPreview)) app=\(restoredAppText)")
            measurements.name = "text-size-restore-measurements"
            measurements.lifetime = .keepAlways
            self.add(measurements)
            // Capture both restored apps before an equality failure can halt teardown.
            XCTAssertEqual(livePosition, originalPosition, accuracy: 0.01)
            XCTAssertEqual(coldPosition, originalPosition, accuracy: 0.01)
            XCTAssertEqual(restoreResult, .completed,
                           "Fresh Settings must return to its original text geometry")
            if let restoredPreview {
                XCTAssertEqual(restoredPreview.width, originalPreview.width, accuracy: 1)
                XCTAssertEqual(restoredPreview.height, originalPreview.height, accuracy: 1)
            } else {
                XCTFail("The fresh Settings preview must be present after restore")
            }
            XCTAssertEqual(restoredAppText.title.width, originalAppText.title.width, accuracy: 1)
            XCTAssertEqual(restoredAppText.title.height, originalAppText.title.height, accuracy: 1)
            XCTAssertEqual(restoredAppText.limit.width, originalAppText.limit.width, accuracy: 1)
            XCTAssertEqual(restoredAppText.limit.height, originalAppText.limit.height, accuracy: 1,
                           "Ceviz must return to its original text geometry after restoring Settings")
        }
        XCTAssertLessThan(originalPosition, 0.95, "The device is already at maximum text size; a larger scenario cannot be claimed")
        guard setSettingsTextSize(1, in: settings) else { return }
        XCTAssertEqual(slider.normalizedSliderPosition, 1, accuracy: 0.01,
                                    "The actual Text Size slider must reach its maximum")
        let enlarged = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            preview.exists && preview.frame.height > originalPreview.height
        }, object: preview)
        XCTAssertEqual(XCTWaiter.wait(for: [enlarged], timeout: 8), .completed,
                       "The actual Settings preview must visibly grow")
        XCTAssertGreaterThan(preview.frame.height, originalPreview.height,
                             "The actual Settings preview must visibly grow")
        recordTestRunnerTextCategory("larger-settings")
        captureSettings(settings, "settings-text-size-larger")
        let enlargedAppText = checkReadyScreenEnglish("ready-larger")
        XCTAssertGreaterThan(enlargedAppText.title.height, originalAppText.title.height,
                             "Ceviz must render a larger heading under the real system setting")
        XCTAssertGreaterThan(enlargedAppText.limit.height, originalAppText.limit.height,
                             "Ceviz must render larger duration text under the real system setting")
    }

    @discardableResult
    private func checkReadyScreenEnglish(_ screenshotName: String = "ready-en") -> (title: CGSize, limit: CGSize) {
        let app = launch("en")
        defer { app.terminate() }
        // Text selectors also exercise the previous build without new identifiers.
        XCTAssertTrue(app.staticTexts["Ready to listen"].waitForExistence(timeout: 15))
        capture(screenshotName, in: app)
        assertVisible(app.staticTexts["Ready to listen"], in: app, "The complete ready heading must be visible")
        assertVisible(app.staticTexts["Up to 15 seconds"], in: app,
                      "15-second limit must be fully visible without scrolling")
        assertVisible(app.buttons["Start recording"], in: app, "Microphone must be reachable without scrolling")
        XCTAssertFalse(app.staticTexts["Up to 15 seconds"].frame.intersects(app.buttons["Start recording"].frame),
                       "The microphone action must not cover any part of the duration limit")
        let offline = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Phone offline")).firstMatch
        if offline.exists {
            assertVisible(offline, in: app, "A displayed Phone offline label must not be clipped by the microphone action")
            XCTAssertFalse(offline.frame.intersects(app.buttons["Start recording"].frame),
                           "The microphone action must not cover the Phone offline label")
        }
        return (app.staticTexts["Ready to listen"].frame.size, app.staticTexts["Up to 15 seconds"].frame.size)
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
            XCTAssertFalse(app.staticTexts["capture.durationLimit"].frame.intersects(start.frame),
                           "The microphone action must not cover the duration limit after discard")
            let discarded = app.staticTexts[language == "tr" ? "Kayıt silindi" : "Discarded"]
            assertVisible(discarded, in: app, "The complete discard confirmation must be visible without scrolling")
            XCTAssertFalse(discarded.frame.intersects(start.frame),
                           "The microphone action must not cover the discard confirmation")
            capture("discarded-\(language)", in: app)
        }
    }

    func testReadyScreenEnglish() {
        recordTestRunnerTextCategory("device-default-ready")
        checkReadyScreenEnglish()
    }

    func testRecordAndDiscardBothLanguages() {
        recordTestRunnerTextCategory("device-default-recording")
        checkRecordAndDiscardBothLanguages()
    }

    func testLargerTextReadyAndDiscardBothLanguages() {
        useLargerSystemText()
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
        recordTestRunnerTextCategory("device-default-finish")
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
