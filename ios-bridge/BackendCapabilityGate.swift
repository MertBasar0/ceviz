import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// An older helper interprets any parent job as approval. Verify semantics
/// before a linked command crosses the HTTP boundary, never after its receipt.
enum BackendCapabilityGate {
    static func send(
        _ request: URLRequest, capabilityRequest: URLRequest, requiring capability: BackendCapability,
        session: URLSession, isCurrent: () -> Bool
    ) async throws -> (Data, URLResponse) {
        do {
            let (data, response) = try await session.data(for: capabilityRequest)
            guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
            if http.statusCode == 401 { throw URLError(.userAuthenticationRequired) }
            guard (200...299).contains(http.statusCode),
                  let capabilities = try? JSONDecoder().decode(BackendCapabilities.self, from: data),
                  capabilities.supports(capability) else { throw BackendCapabilityError.updateRequired }
            try Task.checkCancellation()
            guard isCurrent() else { throw BackendCapabilityError.connectionChanged }
        } catch {
            // This type means no command POST occurred; the user may safely try again.
            throw error as? BackendCapabilityError ?? .verificationFailed(error.localizedDescription)
        }
        // Pairing also invalidates this captured session after the identity check.
        return try await session.data(for: request)
    }
}
