"""Submissions at a round's edges: after it was scored, and across a resume.

A submission arriving after the round was scored, while the clock is still
closing it, must not join a result it can no longer change. A run that stopped
partway through a round and is resumed must keep that round's submissions and
character count, or a viewer who already submitted could never complete its team.
"""

from pathlib import Path

import pytest

from glossogen.models.event import RoundEnded, ToolResultReceived
from glossogen.scenarios.spot_the_intersection.board_model import cell_label
from glossogen.scenarios.spot_the_intersection.ids import ALREADY_SUBMITTED_MARKER
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn
from glossogen.testing.simulation_harness import never_times_out, resume_simulation
from tests.scenarios.spot_the_intersection.conftest import (
    SCENARIO,
    TEAM_A,
    TEAM_B,
    TOOL,
    answer_of,
    one_round_scenario,
    play,
    say_on,
    submit,
    world_of,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_a_submission_after_the_round_was_scored_is_refused() -> None:
    scenario = one_round_scenario()
    world = world_of(scenario=scenario)
    answer = answer_of(scenario=scenario)
    world.finalize_round_sync(round_number=1)
    for agent_id in TEAM_A[:3]:
        world.record_submission(agent_id=agent_id, obj=answer)
    world.mark_round_outcome(round_number=1)
    scored = world.outcome_for(team_id="team_a", round_number=1)
    (tool,) = scenario.get_tools()

    reply = await tool.executor(
        TEAM_A[3],
        shape=answer.shape,
        color=answer.color,
        cell=cell_label(column=answer.column, row=answer.row),
    )

    assert reply.startswith("This round has ended")
    assert not world.has_submitted(agent_id=TEAM_A[3])
    assert world.outcome_for(team_id="team_a", round_number=1) == scored


async def test_a_resume_mid_round_keeps_its_submissions_and_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two members submit and the run stops; after the resume the other two complete the team."""
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    before: dict[str, list[ScriptedTurn]] = {
        TEAM_A[0]: [say_on(scenario=scenario, channel_id="link_a", text="abc"), submit(obj=answer)],
        TEAM_A[1]: [submit(obj=answer)],
    }
    played = await play(
        scenario=scenario, scripts=before, tmp_path=tmp_path / "source", monkeypatch=monkeypatch
    )
    lines = played.log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    stop = played.first_index(event_type=RoundEnded, round_number=1)
    resumed_dir = tmp_path / "resumed"
    resumed_dir.mkdir()
    (resumed_dir / f"{SpotTheIntersectionScenario.name()}.jsonl").write_text(
        "".join(lines[:stop]), encoding="utf-8"
    )

    after: dict[str, list[ScriptedTurn]] = {
        agent_id: [SayTurn(text="idle")] for agent_id in (*TEAM_A, *TEAM_B)
    }
    after[TEAM_A[0]] = [submit(obj=answer)]
    for agent_id in TEAM_A[2:]:
        after[agent_id] = [submit(obj=answer)]
    resumed_scenario = SpotTheIntersectionScenario.create_from_config(
        config=scenario.get_knobs().model_dump(mode="json")
    )
    resumed = await resume_simulation(
        scenario=resumed_scenario,
        scripts=after,
        run_dir=resumed_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    outcome = world_of(scenario=resumed.scenario).outcome_for(team_id="team_a", round_number=1)
    assert outcome is not None
    assert outcome.members_submitted == 4
    assert outcome.correct
    assert outcome.characters_used == 3
    resubmitted = [
        event.result
        for event in resumed.of_type(event_type=ToolResultReceived)
        if event.tool_name == TOOL and event.agent_id == TEAM_A[0]
    ]
    assert resubmitted[-1].startswith(ALREADY_SUBMITTED_MARKER)
