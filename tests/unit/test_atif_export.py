"""Tests for building ATIF trajectories from a run's event log."""

import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from glossogen.atif_export.atif_models import AtifStepSource, AtifTrajectory
from glossogen.atif_export.atif_trajectory_builder import (
    build_agent_trajectories,
    build_run_trajectories,
    trajectory_file_name,
)
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    AgentSwappedMidRun,
    InjectionDelivered,
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    ToolResultReceived,
)
from glossogen.models.event_base import TokenUsage
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.run_export.runs_zip_archive import add_run_to_zip

RUN_ID = "veyru/1700000000"
START = datetime(2026, 1, 1, tzinfo=UTC)
ZERO_USAGE = TokenUsage(
    input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0
)
CYCLE_USAGE = TokenUsage(
    input_tokens=1_000_000,
    output_tokens=10_000,
    cache_read_input_tokens=800_000,
    cache_creation_input_tokens=100_000,
)


def _at(seconds: int) -> datetime:
    return START + timedelta(seconds=seconds)


def _started() -> SimulationStarted:
    return SimulationStarted(
        run_id=RUN_ID,
        scenario_name="veyru",
        scenario_description="",
        channel_ids=["link"],
        scenario_config={"round_count": 3},
        provider="anthropic",
        round_number=0,
        timestamp=_at(seconds=0),
    )


def _registered(agent_id: str, model: str, seconds: int) -> AgentRegistered:
    return AgentRegistered(
        agent_id=agent_id,
        role_name="Field Observer",
        system_prompt=f"You are {agent_id}.",
        channel_ids=["link"],
        tool_names=["read_channel", "send_message"],
        model=model,
        provider="anthropic",
        max_tokens=2048,
        round_number=0,
        timestamp=_at(seconds=seconds),
    )


def _injection(agent_id: str, round_number: int, seconds: int) -> InjectionDelivered:
    return InjectionDelivered(
        agent_id=agent_id,
        text=f"Round {round_number} begins.",
        round_number=round_number,
        timestamp=_at(seconds=seconds),
    )


def _response(
    agent_id: str,
    round_number: int,
    seconds: int,
    call_id: str,
    usage: TokenUsage,
) -> LLMResponseReceived:
    return LLMResponseReceived(
        agent_id=agent_id,
        thinking="plan the message",
        text="Sending the reading.",
        tool_calls=[
            ToolCallRequest(call_id=call_id, tool_name="send_message", arguments={"text": "hi"})
        ],
        stop_reason="tool_use",
        usage=usage,
        round_number=round_number,
        timestamp=_at(seconds=seconds),
    )


def _result(agent_id: str, round_number: int, seconds: int, call_id: str) -> ToolResultReceived:
    return ToolResultReceived(
        agent_id=agent_id,
        tool_name="send_message",
        call_id=call_id,
        arguments={"text": "hi"},
        result="sent",
        round_number=round_number,
        timestamp=_at(seconds=seconds),
    )


def _single_agent_run() -> list[SimulationEvent]:
    """Two rounds; round 1's tool result is logged before the response that made the call."""
    return [
        _started(),
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=1),
        _injection(agent_id="field_observer", round_number=1, seconds=2),
        _result(agent_id="field_observer", round_number=1, seconds=3, call_id="c1"),
        _response(
            agent_id="field_observer", round_number=1, seconds=4, call_id="c1", usage=ZERO_USAGE
        ),
        AgentRunCycleFailed(
            agent_id="field_observer",
            cycle=2,
            error_type="ModelHTTPError",
            message="overloaded",
            round_number=2,
            timestamp=_at(seconds=5),
        ),
        _injection(agent_id="field_observer", round_number=2, seconds=6),
        _response(
            agent_id="field_observer", round_number=2, seconds=7, call_id="c2", usage=CYCLE_USAGE
        ),
        _result(agent_id="field_observer", round_number=2, seconds=8, call_id="c2"),
    ]


def _only(trajectories: list[AtifTrajectory]) -> AtifTrajectory:
    assert len(trajectories) == 1
    return trajectories[0]


def _build(events: list[SimulationEvent], cutoff_round: int | None) -> list[AtifTrajectory]:
    return build_agent_trajectories(
        events=events,
        run_id=RUN_ID,
        scenario_name="veyru",
        agent_id="field_observer",
        cutoff_round=cutoff_round,
    )


def test_steps_are_numbered_in_event_order_starting_with_the_system_prompt() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    assert [step.step_id for step in trajectory.steps] == [1, 2, 3, 4, 5]
    assert [step.source for step in trajectory.steps] == [
        AtifStepSource.SYSTEM,
        AtifStepSource.USER,
        AtifStepSource.AGENT,
        AtifStepSource.USER,
        AtifStepSource.AGENT,
    ]
    assert trajectory.steps[0].message == "You are field_observer."
    assert trajectory.trajectory_id == f"{RUN_ID}/field_observer"
    assert trajectory.session_id == RUN_ID


def test_tool_results_attach_to_their_call_regardless_of_log_order() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    for step in (trajectory.steps[2], trajectory.steps[4]):
        assert step.tool_calls is not None
        assert step.observation is not None
        assert [result.source_call_id for result in step.observation.results] == [
            call.tool_call_id for call in step.tool_calls
        ]
        assert step.observation.results[0].content == "sent"
        assert step.reasoning_content == "plan the message"


def test_only_responses_that_logged_usage_carry_metrics_and_totals_match() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    assert trajectory.steps[2].metrics is None
    metrics = trajectory.steps[4].metrics
    assert metrics is not None
    assert metrics.prompt_tokens == 1_000_000
    assert metrics.cached_tokens == 800_000
    assert metrics.cost_usd is not None
    final = trajectory.final_metrics
    assert final.total_prompt_tokens == metrics.prompt_tokens
    assert final.total_completion_tokens == metrics.completion_tokens
    assert final.total_cost_usd == metrics.cost_usd
    assert final.total_steps == len(trajectory.steps)


def test_failed_cycles_are_recorded_on_the_next_agent_step() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    assert "failed_cycles" not in trajectory.steps[2].extra
    assert trajectory.steps[4].extra["failed_cycles"] == [
        {"cycle": 2, "error_type": "ModelHTTPError", "message": "overloaded"}
    ]


def test_user_and_system_steps_carry_no_agent_only_fields() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=None))

    for step in trajectory.steps:
        if step.source == AtifStepSource.AGENT:
            continue
        assert step.model_name is None
        assert step.reasoning_content is None
        assert step.tool_calls is None
        assert step.observation is None
        assert step.metrics is None


def test_cutoff_round_is_exclusive() -> None:
    trajectory = _only(_build(events=_single_agent_run(), cutoff_round=2))

    assert {step.extra["round_number"] for step in trajectory.steps} == {0, 1}
    assert trajectory.extra["cutoff_round"] == 2


def test_a_swap_to_another_model_starts_a_new_trajectory() -> None:
    events = _single_agent_run() + [
        AgentSwappedMidRun(
            agent_id="field_observer",
            new_model="gpt-5.4",
            new_provider="openai",
            channel_visibility={},
            round_number=3,
            timestamp=_at(seconds=9),
        ),
        _injection(agent_id="field_observer", round_number=3, seconds=10),
    ]

    first, second = _build(events=events, cutoff_round=None)

    assert first.trajectory_id == f"{RUN_ID}/field_observer/gen1"
    assert second.trajectory_id == f"{RUN_ID}/field_observer/gen2"
    assert first.agent.model_name == "claude-sonnet-4-6"
    assert second.agent.model_name == "gpt-5.4"
    assert second.agent.extra["provider"] == "openai"
    assert [step.source for step in second.steps] == [AtifStepSource.SYSTEM, AtifStepSource.USER]
    assert trajectory_file_name(trajectory=second) == "field_observer.gen2.json"


def test_a_resume_re_registration_under_the_same_model_continues_the_trajectory() -> None:
    events = _single_agent_run() + [
        _registered(agent_id="field_observer", model="claude-sonnet-4-6", seconds=9),
        _injection(agent_id="field_observer", round_number=3, seconds=10),
    ]

    trajectory = _only(_build(events=events, cutoff_round=None))

    assert trajectory.steps[-1].message == "Round 3 begins."
    assert trajectory_file_name(trajectory=trajectory) == "field_observer.json"


def test_run_trajectories_cover_every_agent_in_registration_order() -> None:
    events = _single_agent_run() + [
        _registered(agent_id="stabilization_engineer", model="claude-sonnet-4-6", seconds=9),
    ]

    trajectories = build_run_trajectories(
        events=events, run_id=RUN_ID, scenario_name="veyru", cutoff_round=None
    )

    assert [trajectory.agent.extra["agent_id"] for trajectory in trajectories] == [
        "field_observer",
        "stabilization_engineer",
    ]


def test_raw_zip_includes_atif_trajectories_when_asked(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    run_dir.mkdir()
    lines = [event.model_dump_json() for event in _single_agent_run()]
    (run_dir / "veyru.jsonl").write_text("\n".join(lines) + "\n")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        add_run_to_zip(
            archive=archive,
            run_dir=run_dir,
            arc_root=PurePosixPath("veyru/1700000000"),
            scenario_name="veyru",
            include_logs=False,
            include_atif=True,
        )
    buffer.seek(0)
    names = set(zipfile.ZipFile(buffer).namelist())

    assert "veyru/1700000000/atif/field_observer.json" in names
    assert "veyru/1700000000/veyru.jsonl" in names


def test_raw_zip_skips_atif_for_a_run_with_no_event_log(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    run_dir.mkdir()
    (run_dir / "labels.json").write_text("[]")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        tally = add_run_to_zip(
            archive=archive,
            run_dir=run_dir,
            arc_root=PurePosixPath("veyru/1700000000"),
            scenario_name="veyru",
            include_logs=False,
            include_atif=True,
        )

    assert tally.file_count == 1
