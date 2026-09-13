#!/usr/bin/env bash
set -euo pipefail
mkdir -p build/tests
swiftc job-state/CVZJobState.swift ios-bridge/Models.swift tests/swift/JobStateTests.swift -o build/tests/job-state-tests
build/tests/job-state-tests
swiftc job-state/CVZJobState.swift apple-watch/Models.swift apple-watch/WatchResultTracking.swift tests/swift/WatchResultTests.swift -o build/tests/watch-result-tests
build/tests/watch-result-tests
swiftc apple-watch/WatchRecordingLifecycle.swift tests/swift/WatchRecordingTests.swift -o build/tests/watch-recording-tests
build/tests/watch-recording-tests
swiftc job-state/CVZJobState.swift ios-bridge/Models.swift watch-transport/WatchCommandTransport.swift tests/swift/WatchTransportTests.swift -o build/tests/phone-transport-tests
build/tests/phone-transport-tests
swiftc job-state/CVZJobState.swift apple-watch/Models.swift watch-transport/WatchCommandTransport.swift tests/swift/WatchTransportTests.swift -o build/tests/watch-transport-tests
build/tests/watch-transport-tests
swiftc job-state/CVZJobState.swift ios-bridge/Models.swift tests/swift/PhoneCommandTests.swift -o build/tests/phone-command-tests
build/tests/phone-command-tests
swiftc ios-bridge/CevizDeliveryDatabase.swift ios-bridge/ConversationModels.swift ios-bridge/ConversationSessionStore.swift tests/swift/ConversationTests.swift -lsqlite3 -o build/tests/conversation-tests
build/tests/conversation-tests
swiftc job-state/CVZJobState.swift ios-bridge/Models.swift watch-transport/WatchCommandTransport.swift ios-bridge/CevizDeliveryDatabase.swift ios-bridge/WatchDeliveryStore.swift ios-bridge/WatchDeliveryCoordinator.swift tests/swift/WatchDeliveryTests.swift -lsqlite3 -o build/tests/watch-delivery-tests
build/tests/watch-delivery-tests
swiftc job-state/CVZJobState.swift ios-bridge/Models.swift ios-bridge/BackendCapabilityGate.swift tests/swift/BackendCapabilityTests.swift -o build/tests/backend-capability-tests
build/tests/backend-capability-tests
swiftc job-state/CVZJobState.swift ios-bridge/Models.swift ios-bridge/BackendEndpointPolicy.swift ios-bridge/BackendCapabilityGate.swift ios-bridge/BackendConfig.swift tests/swift/BackendTransportTests.swift -o build/tests/backend-transport-tests
build/tests/backend-transport-tests
swiftc job-state/CVZJobState.swift ios-bridge/Models.swift ios-bridge/BackendEndpointPolicy.swift ios-bridge/WatchJobSnapshot.swift tests/swift/ConnectionRecoveryTests.swift -o build/tests/connection-recovery-tests
build/tests/connection-recovery-tests
swiftc job-state/CVZJobState.swift apple-watch/Models.swift ios-bridge/BackendEndpointPolicy.swift ios-bridge/WatchJobSnapshot.swift tests/swift/ConnectionRecoveryTests.swift -o build/tests/watch-snapshot-tests
build/tests/watch-snapshot-tests
