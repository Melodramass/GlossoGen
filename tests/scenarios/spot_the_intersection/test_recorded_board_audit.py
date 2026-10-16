"""The recorded-run audit passes a clean run and catches a tampered one.

The audit reads only the event log, so it is tested by playing a scripted run and
then breaking the log it wrote: a board altered on its way to one viewer, and a
recorded board that no longer matches what was sent.
"""

from pathlib import Path

import pytest

from glossogen.models.event import InjectionDelivered, SimulationEvent
from glossogen.scenarios.spot_the_intersection.events import SpotTheIntersectionRoundStarted
from glossogen.scenarios.spot_the_intersection.recorded_board_audit import audit_events
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
