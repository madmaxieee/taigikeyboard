// Who is allowed to drive the one composing engine.

@testable import TaigiInputMethodCore
import XCTest

/// Each case builds its own coordinator: `shared` is process-wide because the
/// engine state it guards is, and a test that mutated it would decide what
/// the next test starts from. What a handover does to the composition is the
/// core's (`macos/crates/taigi-macos-ffi/src/session.rs`, tokens tests).
@MainActor
final class ComposingSessionCoordinatorTests: XCTestCase {
    func testOnlyTheClaimingSessionCanDriveTheEngine() {
        let coordinator = TestFixtures.makeCoordinator()
        let focused = ComposingSessionToken()
        let background = ComposingSessionToken()

        coordinator.claim(focused)

        XCTAssertTrue(coordinator.owns(focused))
        XCTAssertFalse(
            coordinator.owns(background),
            """
            a controller still alive in another app must not reach the engine — it would \
            append to the composition the user is typing in the foreground one
            """,
        )
    }

    func testRelease_freesTheEngineForTheNextSession() {
        let coordinator = TestFixtures.makeCoordinator()
        let closing = ComposingSessionToken()
        let next = ComposingSessionToken()
        coordinator.claim(closing)

        XCTAssertTrue(coordinator.release(closing))

        XCTAssertFalse(
            coordinator.owns(closing),
            "a closed session must not keep ownership — every session after it would be mute",
        )
        XCTAssertTrue(
            coordinator.claim(next),
            "the next session must be able to take the engine the closed one held",
        )
    }

    /// The core addresses a session by its token's value: counted, so never
    /// repeated, and never 0 — what an unset proto field decodes to.
    func testTokensAreCountedFromOneAndNeverRepeat() {
        let tokens = (0 ..< 3).map { _ in ComposingSessionToken() }

        XCTAssertFalse(tokens.contains { $0.value == 0 })
        XCTAssertEqual(tokens.map(\.value), tokens.map(\.value).sorted())
        XCTAssertEqual(Set(tokens).count, 3)
    }

    func testResume_handsTheEngineToASoleWaitingSessionOnly() {
        let coordinator = TestFixtures.makeCoordinator()
        let first = RecordingInputSession(coordinator: coordinator)
        let second = RecordingInputSession(coordinator: coordinator)
        coordinator.registerActiveSession(first, for: first.token)
        coordinator.registerActiveSession(second, for: second.token)

        coordinator.resumeWaitingSession()
        XCTAssertEqual(first.ownershipTakes + second.ownershipTakes, 0, "two waiting sessions: a key must choose")

        coordinator.unregisterActiveSession(first.token)
        coordinator.resumeWaitingSession()
        XCTAssertEqual(first.ownershipTakes, 0)
        XCTAssertEqual(second.ownershipTakes, 1)
        XCTAssertTrue(coordinator.owns(second.token))
    }

    func testResume_leavesALiveOwnerAlone() {
        let coordinator = TestFixtures.makeCoordinator()
        let owner = RecordingInputSession(coordinator: coordinator)
        coordinator.registerActiveSession(owner, for: owner.token)
        owner.takeInputOwnership()
        let waiting = RecordingInputSession(coordinator: coordinator)
        coordinator.registerActiveSession(waiting, for: waiting.token)

        coordinator.resumeWaitingSession()

        XCTAssertTrue(coordinator.hasActiveOwner)
        XCTAssertEqual(waiting.ownershipTakes, 0, "an extra activation must not take a live owner's engine")
    }

    /// IMK can drop a controller without `inputControllerWillClose`; its weak
    /// entry must not count as a live owner or block the sole-waiting rule.
    func testADeallocatedOwner_isNoLiveOwner() {
        let coordinator = TestFixtures.makeCoordinator()
        do {
            let owner = RecordingInputSession(coordinator: coordinator)
            coordinator.registerActiveSession(owner, for: owner.token)
            owner.takeInputOwnership()
        }
        let waiting = RecordingInputSession(coordinator: coordinator)
        coordinator.registerActiveSession(waiting, for: waiting.token)

        XCTAssertFalse(coordinator.hasActiveOwner)
        coordinator.resumeWaitingSession()
        XCTAssertEqual(waiting.ownershipTakes, 1)
    }

    func testReregisteringAToken_replacesItsEarlierTarget() {
        let coordinator = TestFixtures.makeCoordinator()
        let earlier = RecordingInputSession(coordinator: coordinator)
        let later = RecordingInputSession(coordinator: coordinator, token: earlier.token)
        coordinator.registerActiveSession(earlier, for: earlier.token)
        coordinator.registerActiveSession(later, for: later.token)

        coordinator.resumeWaitingSession()

        XCTAssertEqual(earlier.ownershipTakes, 0)
        XCTAssertEqual(later.ownershipTakes, 1, "one token is one session, however often it activates")
    }
}

/// Takes ownership the way the controller does: by claiming its own token.
@MainActor
private final class RecordingInputSession: InputSessionTarget {
    let token: ComposingSessionToken
    private let coordinator: ComposingSessionCoordinator
    private(set) var ownershipTakes = 0

    init(coordinator: ComposingSessionCoordinator, token: ComposingSessionToken = ComposingSessionToken()) {
        self.coordinator = coordinator
        self.token = token
    }

    func takeInputOwnership() {
        ownershipTakes += 1
        coordinator.claim(token)
    }

    func performShortcutAction(_: ShortcutAction) {}
}
