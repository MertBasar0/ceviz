import Foundation

/// Backend endpoint yapilandirmasi.
///
/// URL ve auth token kullaniciya ait: Ayarlar ekranindan girilir ya da QR
/// ile eslesir. Token KEYCHAIN'de saklanir (uygulama silinse bile kalir);
/// URL UserDefaults'ta. Yapilandirilmamis adres gercek bir sunucuya yonelmez.
/// Backend WATCH_CEVIZ_AUTH_TOKEN ile calisiyorsa tum /api istekleri
/// "Authorization: Bearer <token>" ister.
enum BackendConfig {
    static let connectionDidChange = Notification.Name("cvz.backendConnectionDidChange")
    static let connectionDidRefresh = Notification.Name("cvz.backendConnectionDidRefresh")
    static let urlDefaultsKey = "cvz.backendURL"
    static let connectionMethodKey = "cvz.connectionMethod"
    static let tokenDefaultsKey = "cvz.backendToken"   // eski UserDefaults konumu (migrasyon)
    static let tokenKeychainKey = "backendToken"
    static let unconfiguredBaseURL = "https://backend.invalid"

    static var baseURLString: String {
        let stored = UserDefaults.standard.string(forKey: urlDefaultsKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let method = UserDefaults.standard.string(forKey: connectionMethodKey) ?? "tailscale"
        var base = stored
        if base.isEmpty || !BackendEndpointPolicy.isAllowed(base, connectionMethod: method) {
            base = unconfiguredBaseURL
        }
        while base.hasSuffix("/") { base.removeLast() }
        return base
    }

    static func setBaseURL(_ value: String) {
        UserDefaults.standard.set(value.trimmingCharacters(in: .whitespacesAndNewlines), forKey: urlDefaultsKey)
    }

    static var token: String {
        if let kc = KeychainStore.get(tokenKeychainKey) {
            return kc.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        // Eski surumden migrasyon: UserDefaults'taki token'i Keychain'e tasi.
        if let legacy = UserDefaults.standard.string(forKey: tokenDefaultsKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines), !legacy.isEmpty {
            KeychainStore.set(legacy, for: tokenKeychainKey)
            UserDefaults.standard.removeObject(forKey: tokenDefaultsKey)
            return legacy
        }
        return ""
    }

    static func setToken(_ value: String) {
        KeychainStore.set(value.trimmingCharacters(in: .whitespacesAndNewlines), for: tokenKeychainKey)
    }

    /// ceviz://pair?u=<url>&t=<token> eslesme baglantisini isle. Basarili
    /// oldu ise (url, token) doner.
    @discardableResult
    static func applyPairing(_ url: URL) -> (url: String, token: String)? {
        guard url.scheme == "ceviz", url.host == "pair",
              let comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let items = comps.queryItems else { return nil }
        let u = items.first(where: { $0.name == "u" })?.value ?? ""
        let t = items.first(where: { $0.name == "t" })?.value ?? ""
        let method = items.first(where: { $0.name == "m" })?.value ?? "manual"
        guard !u.isEmpty, !t.isEmpty,
              BackendEndpointPolicy.isAllowed(u, connectionMethod: method) else { return nil }
        guard save(baseURL: u, token: t, connectionMethod: method) else { return nil }
        return (u, t)
    }

    @discardableResult
    static func save(baseURL: String, token: String, connectionMethod: String) -> Bool {
        guard baseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
              BackendEndpointPolicy.isAllowed(baseURL, connectionMethod: connectionMethod) else { return false }
        let unchanged = BackendEndpointPolicy.isSameConnection(baseURLString, token: self.token,
                                                               as: baseURL, token: token)
        // Preserve the stored spelling too: other durable consumers bind their
        // scope to this URL. Cosmetic host/port edits must not orphan that scope.
        setBaseURL(unchanged ? baseURLString : baseURL)
        if !unchanged { setToken(token) }
        UserDefaults.standard.set(connectionMethod, forKey: connectionMethodKey)
        NotificationCenter.default.post(name: unchanged ? connectionDidRefresh : connectionDidChange, object: nil)
        return true
    }

    static func pairingMethod(_ url: URL) -> String? {
        URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
            .first(where: { $0.name == "m" })?.value
    }

    static func url(_ path: String) -> URL {
        URL(string: baseURLString + path) ?? URL(string: unconfiguredBaseURL + path)!
    }

    static func applyAuth(_ request: inout URLRequest) {
        let t = token
        if !t.isEmpty {
            request.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
        }
    }

    static func request(_ path: String, method: String = "GET") -> URLRequest {
        var request = URLRequest(url: url(path))
        request.httpMethod = method
        applyAuth(&request)
        return request
    }
}

/// Owns backend networking separately from URLSession.shared so pairing can
/// discard stale DNS, connection and request state without reinstalling the app.
final class BackendTransport: NSObject, URLSessionDelegate, @unchecked Sendable {
    static let shared = BackendTransport()

    private let lock = NSLock()
    private let configurationTemplate: URLSessionConfiguration
    // All session access, task creation and invalidation share this lock.
    private lazy var session = makeSession()
    private var draining: [ObjectIdentifier: URLSession] = [:]
    private var tasks: [UUID: URLSessionDataTask] = [:]

    init(configuration: URLSessionConfiguration = .ephemeral) {
        // Keep the dependency snapshot private: caller mutations must not change
        // connection policy or protocol ownership in a later reset generation.
        configurationTemplate = configuration.copy() as! URLSessionConfiguration
        super.init()
    }

    private func makeSession() -> URLSession {
        let configuration = configurationTemplate.copy() as! URLSessionConfiguration
        // Configuration copies share these objects. Preserve fresh private
        // cookie/credential stores for each generation, including pairing reset.
        let privateStorage = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = privateStorage.httpCookieStorage
        configuration.urlCredentialStorage = privateStorage.urlCredentialStorage
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.urlCache = nil
        configuration.timeoutIntervalForRequest = 20
        configuration.timeoutIntervalForResource = 180
        // Offline is a visible delivery state, not an invisible 180-second wait.
        // A POST failure still means unknown delivery, never permission to replay.
        configuration.waitsForConnectivity = false
        return URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
    }

    func dataTask(
        with request: URLRequest,
        completionHandler: @escaping (Data?, URLResponse?, Error?) -> Void
    ) -> URLSessionDataTask {
        lock.lock()
        defer { lock.unlock() }
        return createTask(with: request, completion: completionHandler)
    }

    func reset(cancelInFlight: Bool = true) {
        lock.lock()
        defer { lock.unlock() }
        let previous = session
        draining[ObjectIdentifier(previous)] = previous
        session = makeSession()
        // Own tasks from creation, not a later native enumeration: even a
        // never-resumed task belongs here. Invalidate each session exactly once;
        // later full resets cancel its still-owned tasks, not the session again.
        if cancelInFlight { tasks.values.forEach { $0.cancel() } }
        previous.finishTasksAndInvalidate()
    }

    func urlSession(_ session: URLSession, didBecomeInvalidWithError error: Error?) {
        lock.lock()
        defer { lock.unlock() }
        draining.removeValue(forKey: ObjectIdentifier(session))
    }

    private func currentSession() -> URLSession {
        lock.lock()
        defer { lock.unlock() }
        return session
    }

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        try await data(for: request, in: nil)
    }

    /// Capture synchronously before an actor hop. All requests in one delivery
    /// exchange are fenced by this session, including its capability GET/POST.
    func loader() -> (URLRequest) async throws -> (Data, URLResponse) {
        let selected = currentSession()
        return { try await self.data(for: $0, in: selected) }
    }

    private func data(for request: URLRequest, in selectedSession: URLSession?) async throws -> (Data, URLResponse) {
        let cancellation = TaskCancellation()
        return try await withTaskCancellationHandler(operation: {
            try Task.checkCancellation()
            return try await withCheckedThrowingContinuation { continuation in
                do {
                    let task = try self.makeTask(with: request, in: selectedSession) { data, response, error in
                        if let error { continuation.resume(throwing: error) }
                        else if let data, let response { continuation.resume(returning: (data, response)) }
                        else { continuation.resume(throwing: URLError(.badServerResponse)) }
                    }
                    cancellation.start(task)
                } catch { continuation.resume(throwing: error) }
            }
        }, onCancel: { cancellation.cancel() })
    }

    private func makeTask(with request: URLRequest, in selectedSession: URLSession?,
                          completion: @escaping (Data?, URLResponse?, Error?) -> Void) throws -> URLSessionDataTask {
        lock.lock()
        defer { lock.unlock() }
        // Checking identity separately from creation leaves a window in which
        // reset invalidates the captured session before its task exists.
        if let selectedSession, selectedSession !== session { throw BackendCapabilityError.connectionChanged }
        return createTask(with: request, completion: completion)
    }

    // Both creation entry points hold lock. Remove before invoking the caller,
    // so callbacks may start/reset transport without leaking a completed task.
    private func createTask(with request: URLRequest,
                            completion: @escaping (Data?, URLResponse?, Error?) -> Void) -> URLSessionDataTask {
        let id = UUID()
        let task = session.dataTask(with: request) { [weak self] data, response, error in
            if let self {
                self.lock.lock()
                self.tasks.removeValue(forKey: id)
                self.lock.unlock()
            }
            completion(data, response, error)
        }
        tasks[id] = task
        return task
    }

    private final class TaskCancellation: @unchecked Sendable {
        private let lock = NSLock()
        private var task: URLSessionDataTask?
        private var cancelled = false

        func start(_ task: URLSessionDataTask) {
            lock.lock()
            self.task = task
            let wasCancelled = cancelled
            lock.unlock()
            // Cancellation can arrive before the continuation creates its
            // native task; a cancelled task never gets resumed as fresh work.
            if wasCancelled { task.cancel() }
            else { task.resume() }
        }

        func cancel() {
            lock.lock()
            cancelled = true
            let current = task
            lock.unlock()
            current?.cancel()
        }
    }

    func data(for request: URLRequest, requiring capability: BackendCapability) async throws -> (Data, URLResponse) {
        let selectedSession = currentSession()
        let capabilityRequest = BackendConfig.request("/api/v1/capabilities")
        guard request.url?.absoluteString.hasPrefix(BackendConfig.baseURLString + "/api/v1/") == true,
              request.value(forHTTPHeaderField: "Authorization") == capabilityRequest.value(forHTTPHeaderField: "Authorization") else {
            throw BackendCapabilityError.connectionChanged
        }
        return try await BackendCapabilityGate.send(
            request, capabilityRequest: capabilityRequest, requiring: capability,
            load: { try await self.data(for: $0, in: selectedSession) },
            isCurrent: { self.currentSession() === selectedSession }
        )
    }
}
