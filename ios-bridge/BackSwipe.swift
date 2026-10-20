import UIKit

/// Keeps the iOS edge swipe back working on screens that hide the navigation bar.
///
/// Home and the job report draw their own header and hide the system bar, and UIKit's
/// interactive pop gesture stops starting once the bar is hidden. Taking over its delegate
/// lets it start whenever there is a screen to go back to, unless that screen hid its back
/// button on purpose (a conversation that is still sending).
extension UINavigationController: @retroactive UIGestureRecognizerDelegate {
    override open func viewDidLoad() {
        super.viewDidLoad()
        interactivePopGestureRecognizer?.delegate = self
    }

    public func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard gestureRecognizer === interactivePopGestureRecognizer else { return true }
        return viewControllers.count > 1 && topViewController?.navigationItem.hidesBackButton != true
    }
}
