import Foundation

// This executable never links the production Keychain implementation or stores
// pairing values. Its explicit session protocol handles a private scheme and
// the reserved backend.invalid capability fixture, never a configured real backend.
enum KeychainStore {
    static func get(_ key: String) -> String? { nil }
    static func set(_ value: String, for key: String) { preconditionFailure("No Keychain writes in transport tests") }
}

private final class HoldingProtocol: URLProtocol, @unchecked Sendable {
    private final class Registry: @unchecked Sendable {
        let queue = DispatchQueue(label: "ceviz.transport-test.protocol")
        var pending: [String: HoldingProtocol] = [:]
        var starts: [String: Int] = [:]
    }
    private static let registry = Registry()

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.scheme == "ceviz-transport-test" || request.url?.host == "backend.invalid"
    }
    override class func canInit(with task: URLSessionTask) -> Bool {
        task.currentRequest.map { canInit(with: $0) } ?? false
    }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.registry.queue.async {
            let path = self.request.url!.path
            Self.registry.pending[path] = self
            Self.registry.starts[path, default: 0] += 1
        }
    }
    override func stopLoading() {
        Self.registry.queue.async {
            let path = self.request.url!.path
            if Self.registry.pending[path] === self { Self.registry.pending.removeValue(forKey: path) }
        }
    }
    static func started(_ path: String) -> Bool {
        registry.queue.sync { registry.starts[path] == 1 }
    }
    static func finish(_ path: String, body: Data = Data("ok".utf8)) {
        registry.queue.async {
            guard let loading = registry.pending.removeValue(forKey: path) else { return }
            let response: URLResponse = loading.request.url!.scheme == "https"
                ? HTTPURLResponse(url: loading.request.url!, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!
                : URLResponse(url: loading.request.url!, mimeType: "text/plain", expectedContentLength: body.count,
                              textEncodingName: "utf-8")
            loading.client?.urlProtocol(loading, didReceive: response, cacheStoragePolicy: .notAllowed)
            loading.client?.urlProtocol(loading, didLoad: body)
            loading.client?.urlProtocolDidFinishLoading(loading)
        }
    }
    static var isEmpty: Bool { registry.queue.sync { registry.pending.isEmpty } }
}

private final class Completion: @unchecked Sendable {
    private let lock = NSLock()
    private var result: Result<Data, Error>?
    func receive(_ data: Data?, _ response: URLResponse?, _ error: Error?) {
        lock.lock()
        defer { lock.unlock() }
        precondition(result == nil, "A native task must complete exactly once")
        if let error { result = .failure(error) }
        else if let data, response != nil { result = .success(data) }
        else { result = .failure(URLError(.badServerResponse)) }
    }
    var finished: Bool {
        lock.lock(); defer { lock.unlock() }
        return result != nil
    }
    var cancelled: Bool {
        lock.lock(); defer { lock.unlock() }
        guard case .failure(let error)? = result else { return false }
        return (error as? URLError)?.code == .cancelled || error is CancellationError
    }
    var succeeded: Bool {
        lock.lock(); defer { lock.unlock() }
        guard case .success(let data)? = result else { return false }
        return data == Data("ok".utf8)
    }
}

// swiftc job-state/CVZJobState.swift ios-bridge/Models.swift ios-bridge/BackendEndpointPolicy.swift
// ios-bridge/BackendCapabilityGate.swift ios-bridge/BackendConfig.swift tests/swift/BackendTransportTests.swift
// -o build/tests/backend-transport-tests
@main
struct BackendTransportTests {
    private static let callerConfiguration: URLSessionConfiguration = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HoldingProtocol.self]
        return configuration
    }()
    private static let transport = BackendTransport(configuration: callerConfiguration)

    static func request(_ path: String) -> URLRequest {
        URLRequest(url: URL(string: "ceviz-transport-test://fixture" + path)!)
    }
    private static func start(_ path: String) -> (URLSessionDataTask, Completion) {
        let completion = Completion()
        let task = transport.dataTask(with: request(path), completionHandler: completion.receive)
        task.resume()
        return (task, completion)
    }
    static func eventually(_ message: String, _ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(5)
        while !condition(), Date() < deadline { try await Task.sleep(nanoseconds: 10_000_000) }
        precondition(condition(), message)
    }
    // Inspect lifecycle ownership under the owner's actual lock; no production
    // count/debug API exists solely to satisfy this cleanup assertion.
    static func drainingSessions() -> [URLSession] {
        let owner = transport
        let lock = Mirror(reflecting: owner).children.first { $0.label == "lock" }!.value as! NSLock
        lock.lock(); defer { lock.unlock() }
        let draining = Mirror(reflecting: owner).children.first { $0.label == "draining" }!.value
        return Array((draining as! [ObjectIdentifier: URLSession]).values)
    }
    static func drainingCount() -> Int { drainingSessions().count }
    static func ownedTaskCount() -> Int {
        let owner = transport
        let lock = Mirror(reflecting: owner).children.first { $0.label == "lock" }!.value as! NSLock
        lock.lock(); defer { lock.unlock() }
        let tasks = Mirror(reflecting: owner).children.first { $0.label == "tasks" }!.value
        return (tasks as! [UUID: URLSessionDataTask]).count
    }
    static func resetAndCheckCleanup() async throws {
        transport.reset()
        try await eventually("Invalidation callbacks must release every retired session") { drainingCount() == 0 }
        precondition(ownedTaskCount() == 0, "Completed/cancelled tasks must leave no owned task entries")
        try await eventually("No URLProtocol work may escape a test") { HoldingProtocol.isEmpty }
    }
    static func main() async throws {
        // Snapshot before the first task. Neither this edit nor future resets
        // may detach the native fixture protocol from the owned transport.
        _ = transport
        callerConfiguration.protocolClasses = []
        defer { transport.reset() }

        let (taskA, resultA) = start("/reset-a")
        try await eventually("Native session A must start through its copied configuration protocol") { HoldingProtocol.started("/reset-a") }
        transport.reset(cancelInFlight: false)
        let (taskB, resultB) = start("/reset-b")
        try await eventually("Replacement session B must retain the copied protocol after caller configuration changed") { HoldingProtocol.started("/reset-b") }
        precondition(!resultA.finished && !resultB.finished, "A graceful refresh must preserve active work")
        transport.reset()
        try await eventually("A real reset must cancel BOTH the draining A task and current B task") {
            resultA.cancelled && resultB.cancelled
        }
        precondition(taskA.state == .completed && taskB.state == .completed)
        try await resetAndCheckCleanup()

        let (_, gracefulA) = start("/graceful-a")
        try await eventually("Graceful A must start") { HoldingProtocol.started("/graceful-a") }
        transport.reset(cancelInFlight: false)
        precondition(drainingCount() == 1, "Keep the retired session owned until its native invalidation callback")
        let sessionA = drainingSessions().first!
        let configurationA = sessionA.configuration
        let cookiesA = configurationA.httpCookieStorage!
        let credentialsA = configurationA.urlCredentialStorage!
        let cookie = HTTPCookie(properties: [.domain: "backend.invalid", .path: "/",
            .name: "ceviz-fixture-cookie", .value: "session-a-only", .secure: "TRUE"])!
        cookiesA.setCookie(cookie)
        precondition(cookiesA.cookies?.contains(where: { $0.name == cookie.name }) == true)
        let (_, gracefulB) = start("/graceful-b")
        try await eventually("Graceful B must start") { HoldingProtocol.started("/graceful-b") }
        // Retire B gracefully too so both ACTUAL native configurations can be
        // inspected through existing ownership, without a production debug API.
        transport.reset(cancelInFlight: false)
        let sessionB = drainingSessions().first { $0 !== sessionA }!
        let configurationB = sessionB.configuration
        let cookiesB = configurationB.httpCookieStorage!
        let credentialsB = configurationB.urlCredentialStorage!
        precondition(cookiesA !== cookiesB && credentialsA !== credentialsB,
                     "Session generations must not share private cookie/credential stores")
        precondition(cookiesB.cookies?.contains(where: { $0.name == cookie.name }) != true,
                     "A's synthetic cookie must not leak into B")
        HoldingProtocol.finish("/graceful-a")
        HoldingProtocol.finish("/graceful-b")
        try await eventually("Both sides of a graceful refresh must finish normally") { gracefulA.succeeded && gracefulB.succeeded }
        try await eventually("Normal completion must release the draining session") { drainingCount() == 0 }
        try await resetAndCheckCleanup()

        let suspendedResult = Completion()
        let suspended = transport.dataTask(with: request("/suspended"), completionHandler: suspendedResult.receive)
        transport.reset(cancelInFlight: false)
        suspended.resume()
        try await eventually("An already-created suspended task remains owned across graceful refresh") { HoldingProtocol.started("/suspended") }
        HoldingProtocol.finish("/suspended")
        try await eventually("The suspended old-session task must complete") { suspendedResult.succeeded }
        try await resetAndCheckCleanup()

        let retiredSuspendedResult = Completion()
        let retiredSuspended = transport.dataTask(with: request("/retired-suspended"),
                                                   completionHandler: retiredSuspendedResult.receive)
        transport.reset(cancelInFlight: false)
        transport.reset()
        try await eventually("A later full reset must cancel even a never-resumed task in a retired session") {
            retiredSuspendedResult.cancelled
        }
        retiredSuspended.resume()
        precondition(retiredSuspended.state == .completed && !HoldingProtocol.started("/retired-suspended"))
        try await resetAndCheckCleanup()

        let beforeCreate = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            return try await transport.data(for: request("/cancel-before-create"))
        }
        do { _ = try await beforeCreate.value; preconditionFailure("Pre-cancelled task must fail") }
        catch { precondition(error is CancellationError || (error as? URLError)?.code == .cancelled) }
        precondition(!HoldingProtocol.started("/cancel-before-create"), "Task cancellation before creation must not start HTTP")

        let inFlight = Task { try await transport.data(for: request("/async-cancel")) }
        try await eventually("Async task must start") { HoldingProtocol.started("/async-cancel") }
        inFlight.cancel()
        do { _ = try await inFlight.value; preconditionFailure("Cancelling Swift Task must cancel native HTTP") }
        catch { precondition(error is CancellationError || (error as? URLError)?.code == .cancelled) }
        try await resetAndCheckCleanup()

        precondition(BackendConfig.baseURLString == BackendConfig.unconfiguredBaseURL,
                     "This executable must not run against a configured user's backend")
        let command = BackendConfig.request("/api/v1/shortcuts/command", method: "POST")
        let guarded = Task { try await transport.data(for: command, requiring: .continuation) }
        try await eventually("Capability GET must start on the captured native session") {
            HoldingProtocol.started("/api/v1/capabilities")
        }
        transport.reset(cancelInFlight: false)
        HoldingProtocol.finish("/api/v1/capabilities", body: Data("{\"continuation_v1\":true,\"suggestion_approval_v1\":false}".utf8))
        do { _ = try await guarded.value; preconditionFailure("Changed generation must refuse before POST") }
        catch {
            guard case .connectionChanged? = error as? BackendCapabilityError else {
                preconditionFailure("A refreshed capability session must report connectionChanged: \(error)")
            }
        }
        precondition(!HoldingProtocol.started("/api/v1/shortcuts/command"), "Capability completion on A must not submit through B")
        try await resetAndCheckCleanup()

        for index in 0..<10 {
            let path = "/completion-race-\(index)"
            let racing = Task { try await transport.data(for: request(path)) }
            try await eventually("Completion-race request must start") { HoldingProtocol.started(path) }
            HoldingProtocol.finish(path)
            racing.cancel()
            do { let (data, _) = try await racing.value; precondition(data == Data("ok".utf8)) }
            catch { precondition(error is CancellationError || (error as? URLError)?.code == .cancelled) }
            try await resetAndCheckCleanup()
        }
        print("PASS: real URLSession graceful drain, all-generation reset, cancellation, completion races and cleanup")
    }
}
