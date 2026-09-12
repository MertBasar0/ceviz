import CryptoKit
import Foundation
import SQLite3

/// One native SQLite bootstrap for phone and Watch delivery metadata. Synchronous
/// commits finish before HTTP dispatch; no audio, transcript or token is stored.
@MainActor
final class CevizDeliveryDatabase {
    enum Failure: Error { case unavailable }
    private var database: OpaquePointer?

    static func pairingIdentity(baseURL: String, token: String) -> String {
        let framed = "\(baseURL.utf8.count):\(baseURL)\(token)"
        return SHA256.hash(data: Data(framed.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    init(url: URL? = nil) throws {
        let file: URL
        if let url { file = url }
        else {
            file = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                              appropriateFor: nil, create: true)
                .appendingPathComponent("Ceviz", isDirectory: true).appendingPathComponent("conversations.sqlite")
        }
        var directory = file.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                               attributes: [.posixPermissions: 0o700])
        var resources = URLResourceValues()
        resources.isExcludedFromBackup = true
        try directory.setResourceValues(resources)
        guard sqlite3_open_v2(file.path, &database, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil) == SQLITE_OK else {
            sqlite3_close(database); database = nil
            throw Failure.unavailable
        }
        do {
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
            #if os(iOS)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: file.path)
            #endif
            try execute("PRAGMA synchronous = EXTRA")
            let version = try execute("PRAGMA user_version").first?.first
            guard version == "0" || version == "1" else { throw Failure.unavailable }
            try execute("""
                CREATE TABLE IF NOT EXISTS deliveries (
                    pairing_id TEXT NOT NULL, session_key TEXT NOT NULL, session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('unconfirmed','running','queued','completed','failed','aborted','reviewed')),
                    PRIMARY KEY (pairing_id, session_key)
                )
                """)
            try execute("PRAGMA user_version = 1")
        } catch {
            sqlite3_close(database); database = nil
            throw error
        }
    }

    deinit { sqlite3_close(database) }

    func transaction<T>(_ body: () throws -> T) throws -> T {
        try execute("BEGIN IMMEDIATE")
        do {
            let value = try body()
            try execute("COMMIT")
            return value
        } catch {
            try? execute("ROLLBACK")
            throw error
        }
    }

    @discardableResult
    func execute(_ sql: String, _ values: [String] = []) throws -> [[String]] {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else { throw Failure.unavailable }
        defer { sqlite3_finalize(statement) }
        for (index, value) in values.enumerated() {
            let result = value.withCString {
                sqlite3_bind_text(statement, Int32(index + 1), $0, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
            }
            guard result == SQLITE_OK else { throw Failure.unavailable }
        }
        var rows: [[String]] = []
        var result = sqlite3_step(statement)
        while result == SQLITE_ROW {
            rows.append((0..<sqlite3_column_count(statement)).map { index in
                sqlite3_column_text(statement, index).map { String(cString: $0) } ?? ""
            })
            result = sqlite3_step(statement)
        }
        guard result == SQLITE_DONE else { throw Failure.unavailable }
        return rows
    }
}
