import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

private final class CapabilityProtocol: URLProtocol {
    static var status = 200
    static var body = Data()
    static var received: [String] = []
    static var failMethod: String?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.received.append(request.httpMethod ?? "GET")
        if request.httpMethod == Self.failMethod {
            client?.urlProtocol(self, didFailWithError: URLError(.timedOut))
            return
        }
        let isCapability = request.url!.path.hasSuffix("/capabilities")
        let response = HTTPURLResponse(url: request.url!, statusCode: isCapability ? Self.status : 202, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: isCapability ? Self.body : Data("{}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

// swiftc job-state/CVZJobState.swift ios-bridge/Models.swift ios-bridge/BackendCapabilityGate.swift tests/swift/BackendCapabilityTests.swift -o /tmp/capability-tests
@main
struct BackendCapabilityTests {
    static func main() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [CapabilityProtocol.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let capabilityRequest = URLRequest(url: URL(string: "https://ceviz.example/ceviz/api/v1/capabilities")!)
        var command = URLRequest(url: URL(string: "https://ceviz.example/ceviz/api/v1/shortcuts/command")!)
        command.httpMethod = "POST"
        command.httpBody = try JSONEncoder().encode(PhoneJobCommand.followUp(jobId: "job-selected", text: "Explain first", locale: "en_US"))

        for (status, body, required, current, shouldSend) in [
            (404, "{}", BackendCapability.continuation, true, false),
            (401, "{}", .continuation, true, false),
            (200, "{}", .continuation, true, false),
            (200, "{\"continuation_v1\":false,\"suggestion_approval_v1\":true}", .continuation, true, false),
            (200, "{\"continuation_v1\":true,\"suggestion_approval_v1\":false}", .suggestionApproval, true, false),
            (200, "{\"continuation_v1\":true,\"suggestion_approval_v1\":false}", .continuation, true, true),
            (200, "{\"continuation_v1\":true,\"suggestion_approval_v1\":true}", .suggestionApproval, false, false),
            (200, "{\"continuation_v1\":true,\"suggestion_approval_v1\":true}", .suggestionApproval, true, true),
        ] {
            CapabilityProtocol.status = status
            CapabilityProtocol.body = Data(body.utf8)
            CapabilityProtocol.received = []
            do {
                _ = try await BackendCapabilityGate.send(command, capabilityRequest: capabilityRequest, requiring: required,
                                                         session: session, isCurrent: { current })
                precondition(shouldSend, "An unsupported or changed helper must reject before submission")
            } catch {
                precondition(!shouldSend, "A supported unchanged helper should receive the linked request: \(error)")
                precondition(error is BackendCapabilityError, "A definitive pre-POST failure must allow a user retry")
            }
            precondition(CapabilityProtocol.received == (shouldSend ? ["GET", "POST"] : ["GET"]),
                         "Old helpers, missing capabilities and pairing changes must never receive the POST")
        }
        for method in ["GET", "POST"] {
            CapabilityProtocol.failMethod = method
            CapabilityProtocol.received = []
            do {
                _ = try await BackendCapabilityGate.send(command, capabilityRequest: capabilityRequest, requiring: .continuation,
                                                         session: session, isCurrent: { true })
                preconditionFailure("The injected HTTP timeout must be visible")
            } catch {
                precondition((error is BackendCapabilityError) == (method == "GET"),
                             "Only a failed capability GET permits retry; a POST timeout stays ambiguous")
            }
            precondition(CapabilityProtocol.received == (method == "GET" ? ["GET"] : ["GET", "POST"]))
            if method == "GET" {
                CapabilityProtocol.failMethod = nil
                _ = try await BackendCapabilityGate.send(command, capabilityRequest: capabilityRequest, requiring: .continuation,
                                                         session: session, isCurrent: { true })
                precondition(CapabilityProtocol.received == ["GET", "GET", "POST"],
                             "Retrying the unchanged intent after a GET-only failure sends exactly one command")
            }
        }
        print("PASS: capability refusals, safe GET-only retry, and no retry permission after a POST timeout")
    }
}
