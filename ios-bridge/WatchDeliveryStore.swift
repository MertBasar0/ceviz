import Foundation

/// Metadata only. The Watch's existing 15-minute recording artifact owns audio.
/// A prepared row proves no POST; an unconfirmed row never grants replay alone.
@MainActor
final class WatchDeliveryStore {
    enum Failure: Error { case invalidIdentity, capacity, missingRecord }
    enum Phase: String { case prepared, unconfirmed, accepted }
    struct Delivery {
        let identity: WatchCommandTransport.Identity
        let timestamp: String
        let parentID: String
        let ledgerID: String
        let phase: Phase
        let jobID: String

        var query: [String: Any] {
            var fields: [String: Any] = ["command_id": identity.commandID, "audio_digest": identity.digest,
                "client_timestamp": timestamp, "ledger_id": ledgerID]
            if !parentID.isEmpty { fields["continue_job_id"] = parentID }
            return fields
        }
    }

    private let database: CevizDeliveryDatabase
    private let pairing: String
    let journalID: String

    init(baseURL: String, token: String, databaseURL: URL? = nil) throws {
        pairing = CevizDeliveryDatabase.pairingIdentity(baseURL: baseURL, token: token)
        let database = try CevizDeliveryDatabase(url: databaseURL)
        self.database = database
        journalID = try database.transaction {
            try database.execute("CREATE TABLE IF NOT EXISTS watch_delivery_metadata (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), journal_id TEXT NOT NULL)")
            try database.execute("INSERT OR IGNORE INTO watch_delivery_metadata VALUES (1, ?)", [UUID().uuidString])
            guard let value = try database.execute("SELECT journal_id FROM watch_delivery_metadata WHERE singleton = 1").first?.first,
                  UUID(uuidString: value) != nil else { throw Failure.invalidIdentity }
            return value
        }
        // Additive, lazy schema: existing version-1 conversation readers safely
        // ignore this table. Do not migrate/copy audio or other legacy file data.
        try database.execute("""
            CREATE TABLE IF NOT EXISTS watch_deliveries (
                pairing_id TEXT NOT NULL, command_id TEXT NOT NULL, audio_digest TEXT NOT NULL,
                client_timestamp TEXT NOT NULL, captured_at REAL NOT NULL, parent_id TEXT NOT NULL,
                ledger_id TEXT NOT NULL DEFAULT '', phase TEXT NOT NULL CHECK(phase IN ('prepared','unconfirmed','accepted')),
                job_id TEXT NOT NULL DEFAULT '', PRIMARY KEY(pairing_id, command_id)
            )
            """)
    }

    func find(_ identity: WatchCommandTransport.Identity) throws -> Delivery? {
        let rows = try database.execute("""
            SELECT audio_digest, client_timestamp, parent_id, ledger_id, phase, job_id
            FROM watch_deliveries WHERE pairing_id = ? AND command_id = ?
            """, [pairing, identity.commandID])
        guard let row = rows.first else { return nil }
        guard row.count == 6, row[0] == identity.digest, let phase = Phase(rawValue: row[4]),
              ISO8601DateFormatter().date(from: row[1]) != nil else {
            throw Failure.invalidIdentity
        }
        switch phase {
        case .prepared:
            guard row[3].isEmpty && row[5].isEmpty else { throw Failure.invalidIdentity }
        case .unconfirmed:
            guard UUID(uuidString: row[3]) != nil && row[5].isEmpty else { throw Failure.invalidIdentity }
        case .accepted:
            guard UUID(uuidString: row[3]) != nil && !row[5].isEmpty else { throw Failure.invalidIdentity }
        }
        return Delivery(identity: identity, timestamp: row[1], parentID: row[2], ledgerID: row[3], phase: phase, jobID: row[5])
    }

    func reserve(_ identity: WatchCommandTransport.Identity, request: WatchCommandRequest, now: Date = Date()) throws -> Delivery {
        guard let timestamp = request.clientTimestamp, let captured = ISO8601DateFormatter().date(from: timestamp),
              UUID(uuidString: identity.commandID) != nil,
              WatchCommandTransport.identity(commandID: identity.commandID, request: request) == identity else {
            throw Failure.invalidIdentity
        }
        return try database.transaction {
            if let previous = try find(identity) {
                guard previous.timestamp == timestamp && previous.parentID == (request.continueJobId ?? "") else {
                    throw Failure.invalidIdentity
                }
                return previous
            }
            // Expired accepted/prepared entries cannot authorize another POST.
            // Keep every uncertain entry; capacity refusal must never erase it.
            try database.execute("DELETE FROM watch_deliveries WHERE phase IN ('accepted','prepared') AND captured_at <= ?",
                                 [String(now.addingTimeInterval(-WatchCommandTransport.maximumAge).timeIntervalSince1970)])
            let count = Int(try database.execute("SELECT count(*) FROM watch_deliveries").first?.first ?? "") ?? 512
            guard count < 512 else { throw Failure.capacity }
            try database.execute("""
                INSERT INTO watch_deliveries
                (pairing_id,command_id,audio_digest,client_timestamp,captured_at,parent_id,phase) VALUES (?,?,?,?,?,?,'prepared')
                """, [pairing, identity.commandID, identity.digest, timestamp,
                      String(captured.timeIntervalSince1970), request.continueJobId ?? ""])
            guard let delivery = try find(identity) else { throw Failure.missingRecord }
            return delivery
        }
    }

    func bindForDispatch(_ identity: WatchCommandTransport.Identity, ledgerID: String) throws -> Delivery {
        guard UUID(uuidString: ledgerID) != nil else { throw Failure.invalidIdentity }
        return try database.transaction {
            guard let existing = try find(identity), existing.phase == .prepared else { throw Failure.missingRecord }
            try database.execute("""
                UPDATE watch_deliveries SET ledger_id = ?, phase = 'unconfirmed'
                WHERE pairing_id = ? AND command_id = ? AND phase = 'prepared'
                """, [ledgerID, pairing, identity.commandID])
            guard let value = try find(identity), value.phase == .unconfirmed else { throw Failure.missingRecord }
            return value
        }
    }

    func acknowledge(_ identity: WatchCommandTransport.Identity, ledgerID: String, jobID: String) throws {
        guard !jobID.isEmpty, jobID.utf8.count <= 256 else { throw Failure.invalidIdentity }
        try database.transaction {
            guard let existing = try find(identity), existing.ledgerID == ledgerID,
                  existing.phase == .unconfirmed || (existing.phase == .accepted && existing.jobID == jobID) else {
                throw Failure.invalidIdentity
            }
            try database.execute("UPDATE watch_deliveries SET phase = 'accepted', job_id = ? WHERE pairing_id = ? AND command_id = ?",
                                 [jobID, pairing, identity.commandID])
        }
    }
}
