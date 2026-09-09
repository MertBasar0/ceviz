import Foundation

struct ConversationServiceError: Decodable, LocalizedError {
    let error: String
    let code: String
    let deliveryUncertain: Bool

    var errorDescription: String? {
        // The backend returns safe summaries; known codes have native translations.
        let key = "conversation.error.\(code)"
        let localized = NSLocalizedString(key, comment: "conversation service error")
        return localized == key ? error : localized
    }

    enum CodingKeys: String, CodingKey {
        case error, code
        case deliveryUncertain = "delivery_uncertain"
    }
}

enum ConversationClient {
    static func request(_ path: String, query: [URLQueryItem] = []) throws -> URLRequest {
        var request = BackendConfig.request("/api/v1/sessions" + path)
        guard let currentURL = request.url,
              var components = URLComponents(url: currentURL, resolvingAgainstBaseURL: false) else {
            throw URLError(.badURL)
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw URLError(.badURL) }
        request.url = url
        return request
    }

    static func load<T: Decodable>(_ request: URLRequest, as type: T.Type) async throws -> T {
        let (data, response) = try await BackendTransport.shared.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200...299).contains(response.statusCode) else {
            if let error = try? JSONDecoder().decode(ConversationServiceError.self, from: data) { throw error }
            if response.statusCode == 404 {
                throw ConversationServiceError(
                    error: NSLocalizedString("Update the Ceviz helper service to use conversations.", comment: ""),
                    code: "not_supported", deliveryUncertain: false
                )
            }
            throw URLError(response.statusCode == 401 ? .userAuthenticationRequired : .badServerResponse)
        }
        return try JSONDecoder().decode(type, from: data)
    }

    static func send(_ payload: OpenClawConversationRequest) async throws -> OpenClawConversationReceipt {
        var request = try request("/message")
        request.httpMethod = "POST"
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(payload)
        return try await load(request, as: OpenClawConversationReceipt.self)
    }
}
