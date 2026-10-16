"""spot_the_intersection, driven through its real round loop.

Only the model is faked. The world, the game clock, the postmortem phase and
the round verdict all run for real.
"""

from pathlib import Path

import pytest

from glossogen.scenarios.spot_the_intersection.events import SpotTheIntersectionRoundStarted
from glossogen.testing.scenario_runtime import (
    assert_no_agent_crashed,
    assert_postmortem_never_ran,
    assert_postmortem_ran,
    assert_round_loop_completed,
    messages_on_primary,
    run_rounds,
)

SCENARIO = "spot_the_intersection"

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_it_plays_two_rounds_and_judges_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two rounds so a bug in the round transition has somewhere to show."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_round_loop_completed(result=result, round_count=2)
    assert_no_agent_crashed(result=result)
    assert (
        messages_on_primary(result=result, scenario_name=SCENARIO, preset_name="knobs_default") >= 2
    )
    started = result.of_type(event_type=SpotTheIntersectionRoundStarted)
    assert [event.round_number for event in started] == [1, 2]


async def test_a_larger_team_plays_its_rounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The roster is built from the knob, so a bigger team must run end to end."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_single_team",
        round_count=1,
        overrides={"team_size": 8, "grid_size": 7},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_round_loop_completed(result=result, round_count=1)
    assert_no_agent_crashed(result=result)
    (started,) = result.of_type(event_type=SpotTheIntersectionRoundStarted)
    assert len(started.boards) == 8


async def test_postmortem_opens_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        round_count=1,
        overrides={"postmortem_enabled": True},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_postmortem_ran(result=result, round_count=1)


async def test_postmortem_stays_shut_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        round_count=1,
        overrides={"postmortem_enabled": False},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_postmortem_never_ran(result=result)
    assert_round_loop_completed(result=result, round_count=1)
