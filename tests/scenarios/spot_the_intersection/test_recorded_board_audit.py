"""The recorded-run audit passes a clean run and catches a tampered one.

The audit reads only the event log, so it is tested by playing a scripted run and
then breaking the log it wrote: a board altered on its way to one viewer, a
recorded board that no longer matches what was sent, and a viewer sent no board.
A round this checkout cannot generate is a note, not a failure.
"""

from pathlib import Path

import pytest

from glossogen.models.event import InjectionDelivered, SimulationEvent
from glossogen.scenarios.spot_the_intersection import recorded_board_audit
from glossogen.scenarios.spot_the_intersection.board_generation import (
    BoardGenerationError,
    BoardSettings,
    RoundBoards,
)
from glossogen.scenarios.spot_the_intersection.events import SpotTheIntersectionRoundStarted
from glossogen.scenarios.spot_the_intersection.injection_rendering import BOARD_HEADER
from glossogen.scenarios.spot_the_intersection.recorded_board_audit import (
    AuditFinding,
    audit_events,
)
from glossogen.testing.scenario_runtime import run_rounds

SCENARIO = "spot_the_intersection"

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def played_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[SimulationEvent]:
    """The event log of a scripted two-round, two-team run."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    return result.events


async def test_a_clean_run_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit = audit_events(events=await played_events(tmp_path=tmp_path, monkeypatch=monkeypatch))

    assert audit.rounds_audited == 2
    assert audit.findings == ()
    assert audit.regenerated_differently == ()


async def test_a_board_changed_on_its_way_to_one_viewer_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = await played_events(tmp_path=tmp_path, monkeypatch=monkeypatch)
    tampered: list[SimulationEvent] = []
    for event in events:
        if (
            isinstance(event, InjectionDelivered)
            and event.agent_id == "viewer_b_2"
            and event.round_number == 1
            and "\n- " in event.text
        ):
            first, rest = event.text.split("\n- ", 1)
            event = event.model_copy(update={"text": f"{first}\n- {rest.split(chr(10), 1)[1]}"})
        tampered.append(event)

    audit = audit_events(events=tampered)

    problems = [finding.problem for finding in audit.findings if finding.round_number == 1]
    assert "viewer_b_2 was sent a board other than seat 2's" in problems
    assert "the teams were sent different boards" in problems


async def test_a_recorded_board_the_viewers_never_saw_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = await played_events(tmp_path=tmp_path, monkeypatch=monkeypatch)
    tampered: list[SimulationEvent] = []
    for event in events:
        if isinstance(event, SpotTheIntersectionRoundStarted) and event.round_number == 2:
            boards = [list(board) for board in event.boards]
            boards[0] = boards[0][1:]
            event = event.model_copy(update={"boards": boards})
        tampered.append(event)

    audit = audit_events(events=tampered)

    assert any(
        finding.round_number == 2 and "seat 1's" in finding.problem for finding in audit.findings
    )
    assert audit.regenerated_differently == (2,)


async def test_a_viewer_sent_no_board_is_the_only_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rest of that team's boards are not certified out of seat order."""
    events = await played_events(tmp_path=tmp_path, monkeypatch=monkeypatch)
    without_delivery = [
        event
        for event in events
        if not (
            isinstance(event, InjectionDelivered)
            and event.agent_id == "viewer_a_2"
            and event.round_number == 1
            and BOARD_HEADER in event.text
        )
    ]

    audit = audit_events(events=without_delivery)

    assert audit.findings == (AuditFinding(round_number=1, problem="viewer_a_2 got no board"),)


async def test_a_round_this_checkout_cannot_generate_is_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = await played_events(tmp_path=tmp_path, monkeypatch=monkeypatch)

    def cannot_generate(seed: int, round_number: int, settings: BoardSettings) -> RoundBoards:
        _ = (seed, settings)
        raise BoardGenerationError(f"round {round_number} did not certify")

    monkeypatch.setattr(recorded_board_audit, "generate_round", cannot_generate)

    audit = audit_events(events=events)

    assert audit.findings == ()
    assert [note.round_number for note in audit.not_regenerated] == [1, 2]
