import Foundation

/// The durable phone boundary between WC and HTTP. Neither a transport error
/// nor a missing journal grants permission to repeat an external action.
@MainActor
final class WatchDeliveryCoordinator {
    typealias Loader = (URLRequest) async throws -> (Data, URLResponse)
    enum Failure: Error { case updateRequired, unknown, connectionChanged, invalidReceipt }
    private let store: WatchDeliveryStore
    private let makeRequest: (String) -> URLRequest
    private let isCurrent: () -> Bool
    private var active: Set<String> = []
    var deliveryJournalID: String { store.journalID }

    init(baseURL: String, token: String, databaseURL: URL? = nil, isCurrent: @escaping () -> Bool) throws {
        store = try WatchDeliveryStore(baseURL: baseURL, token: token, databaseURL: databaseURL)
        makeRequest = { path in
            var request = URLRequest(url: URL(string: baseURL + "/api/v1/watch/command/" + path)!)
            if !token.isEmpty { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
            request.timeoutInterval = 20
            return request
        }
        self.isCurrent = isCurrent
    }

    func submit(_ incoming: WatchCommandTransport.Incoming, load: Loader) async throws -> [String: Any] {
        guard incoming.recoveryProtocol == 1, let identity = incoming.identity else { throw Failure.updateRequired }
        guard isCurrent() else { throw Failure.connectionChanged }
        // The Watch pins this epoch before handing audio to WC. A delayed file
        // cannot be admitted again after phone storage has been replaced.
        guard incoming.deliveryJournalID == store.journalID else { throw Failure.unknown }
        guard active.insert(identity.commandID).inserted else { return reply("in_flight", identity: identity) }
        defer { active.remove(identity.commandID) }
        var delivery = try store.reserve(identity, request: incoming.request)
        if delivery.phase == .accepted { return try accepted(delivery) }
        if delivery.phase == .unconfirmed {
            let response = try await reconcile(delivery, load: load)
            guard response["status"] as? String == "not_submitted" else { return response }
            // Keep the ORIGINAL ledger, even after a verified missing row.
            // A database replacement must reject the replay, never rebind it.
        } else {
            let capabilities = try await json(makeRequest("capabilities"), load: load)
            guard capabilities["watch_command_recovery_v1"] as? Bool == true,
                  let ledger = capabilities["watch_command_ledger_id"] as? String,
                  UUID(uuidString: ledger) != nil else { throw Failure.updateRequired }
            guard isCurrent(), WatchCommandTransport.isCurrent(incoming.request) else { throw Failure.connectionChanged }
            delivery = try store.bindForDispatch(identity, ledgerID: ledger)
        }
        guard isCurrent(), WatchCommandTransport.isCurrent(incoming.request) else { throw Failure.connectionChanged }
        var payload = try JSONSerialization.jsonObject(with: JSONEncoder().encode(incoming.request)) as! [String: Any]
        for (key, value) in delivery.query { payload[key] = value }
        let response = try await json(try post("submit", body: payload), load: load)
        return try apply(response, to: delivery)
    }

    func status(_ identity: WatchCommandTransport.Identity, load: Loader) async throws -> [String: Any] {
        guard isCurrent() else { throw Failure.connectionChanged }
        if active.contains(identity.commandID) { return reply("in_flight", identity: identity) }
        // No row may mean old-version delivery or lost phone storage. Never
        // fabricate a new ledger from current capabilities to answer this query.
        guard let delivery = try store.find(identity) else { return reply("unknown", identity: identity) }
        switch delivery.phase {
        case .prepared: return reply("not_submitted", identity: identity)
        case .accepted: return try accepted(delivery)
        case .unconfirmed: return try await reconcile(delivery, load: load)
        }
    }

    private func reconcile(_ delivery: WatchDeliveryStore.Delivery, load: Loader) async throws -> [String: Any] {
        let response = try await json(try post("status", body: delivery.query), load: load)
        return try apply(response, to: delivery)
    }

    private func apply(_ response: [String: Any], to delivery: WatchDeliveryStore.Delivery) throws -> [String: Any] {
        guard isCurrent() else { throw Failure.connectionChanged }
        guard response["command_id"] as? String == delivery.identity.commandID,
              response["audio_digest"] as? String == delivery.identity.digest,
              response["ledger_id"] as? String == delivery.ledgerID,
              response["client_timestamp"] as? String == delivery.timestamp,
              (response["continue_job_id"] as? String ?? "") == delivery.parentID,
              let state = response["delivery_state"] as? String else { throw Failure.invalidReceipt }
        switch state {
        case "accepted":
            guard let job = response["job_id"] as? String else { throw Failure.invalidReceipt }
            try store.acknowledge(delivery.identity, ledgerID: delivery.ledgerID, jobID: job)
            guard let saved = try store.find(delivery.identity) else { throw Failure.invalidReceipt }
            return try accepted(saved, response: response["response"] as? [String: Any])
        case "not_submitted", "in_flight", "unknown": return reply(state, identity: delivery.identity)
        default: throw Failure.invalidReceipt
        }
    }

    private func accepted(_ delivery: WatchDeliveryStore.Delivery, response: [String: Any]? = nil) throws -> [String: Any] {
        var result = reply("accepted", identity: delivery.identity)
        var payload: [String: Any] = ["status": "processing", "job_id": delivery.jobID, "outcome": "unknown",
            "summary_text": NSLocalizedString("Request received. Checking result…", comment: "Watch delivery acknowledgement"),
            "transcript": "", "requires_phone_handoff": false]
        if let response, response["job_id"] as? String == delivery.jobID,
           let data = try? JSONSerialization.data(withJSONObject: response),
           let receipt = try? WatchCommandTransport.receipt(responseData: data, identity: delivery.identity),
           let compact = receipt["response_data"] as? Data {
            result["response_data"] = compact
        } else {
            // An accepted delivery is not proof that the work succeeded. The
            // existing Watch result poll resolves the immutable job identity.
            payload["deep_link"] = "ceviz://job/" + delivery.jobID
            result["response_data"] = try JSONSerialization.data(withJSONObject: payload)
        }
        return result
    }

    private func reply(_ state: String, identity: WatchCommandTransport.Identity) -> [String: Any] {
        ["status": state, "command_id": identity.commandID, "audio_digest": identity.digest]
    }

    private func post(_ path: String, body: [String: Any]) throws -> URLRequest {
        var request = makeRequest(path)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return request
    }

    private func json(_ request: URLRequest, load: Loader) async throws -> [String: Any] {
        guard isCurrent() else { throw Failure.connectionChanged }
        let (data, response) = try await load(request)
        guard isCurrent() else { throw Failure.connectionChanged }
        guard let http = response as? HTTPURLResponse else { throw Failure.unknown }
        if http.statusCode == 404 { throw Failure.updateRequired }
        guard (200..<300).contains(http.statusCode),
              let result = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw Failure.unknown }
        return result
    }
}
