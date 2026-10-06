"""Build ATIF trajectories for a run's agents from its JSONL event log.

Walks the events directly instead of going through ``build_message_history``, because
the reconstructed pydantic-ai history drops timestamps, token usage and which turns
came from scenario injections.

A seat that changes model mid-run (an in-run ``AgentSwappedMidRun``, or a
re-registration under a different model after replace-agent / cross-run) produces one
trajectory per generation, since ATIF records one agent per trajectory. A
re-registration under the same model is a resume and continues the current
generation.
"""

from importlib.metadata import version
from pathlib import Path
from typing import Any, NamedTuple

from glossogen.atif_export.atif_models import (
    ATIF_SCHEMA_VERSION,
    AtifAgent,
    AtifFinalMetrics,
    AtifStep,
    AtifTrajectory,
)
from glossogen.atif_export.atif_step_builder import (
    build_agent_step,
    build_compaction_step,
    build_delivered_text_step,
    build_system_prompt_step,
)
from glossogen.evaluation.log_reader import extract_scenario_config, load_events
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    AgentSwappedMidRun,
    ContextCompacted,
    InjectionDelivered,
    LLMResponseReceived,
    SimulationEvent,
    ToolResultReceived,
    WorldEventDelivered,
)
from glossogen.token_pricing import find_pricing


class _Generation(NamedTuple):
    """One stretch of a seat played under a single model."""

    registration: AgentRegistered
    model: str
    provider: str
    events: list[SimulationEvent]


def build_agent_trajectories(
    events: list[SimulationEvent],
    run_id: str,
    scenario_name: str,
    agent_id: str,
    cutoff_round: int | None,
) -> list[AtifTrajectory]:
    """Every generation of ``agent_id`` in the run, each as one ATIF trajectory.

    ``cutoff_round`` is exclusive, as in thread export: ``R`` keeps rounds
    ``1..R-1``; ``None`` keeps the whole run.
    """
    agent_events = _select_agent_events(events=events, agent_id=agent_id, cutoff_round=cutoff_round)
    generations = _split_generations(agent_events=agent_events, agent_id=agent_id)
    if not generations:
        raise ValueError(f"No agent {agent_id!r} registered in run {run_id}")
    scenario_config = extract_scenario_config(events=events)
    return [
        _build_trajectory(
            generation=generation,
            generation_index=index,
            generation_count=len(generations),
            run_id=run_id,
            scenario_name=scenario_name,
            scenario_config=scenario_config,
            cutoff_round=cutoff_round,
        )
        for index, generation in enumerate(generations, start=1)
    ]


async def build_agent_trajectories_from_run_dir(
    run_dir: Path,
    scenario_name: str,
    agent_id: str,
    cutoff_round: int | None,
) -> list[AtifTrajectory]:
    """Load a run's JSONL and build ``agent_id``'s trajectories.

    ``run_id`` is derived as ``<scenario>/<run_dir_name>``.
    """
    events = await load_events(log_path=run_dir / f"{scenario_name}.jsonl")
    return build_agent_trajectories(
        events=events,
        run_id=f"{run_dir.parent.name}/{run_dir.name}",
        scenario_name=scenario_name,
        agent_id=agent_id,
        cutoff_round=cutoff_round,
    )


def registered_agent_ids(events: list[SimulationEvent]) -> list[str]:
    """Agent ids in the order they first registered."""
    agent_ids: list[str] = []
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id not in agent_ids:
            agent_ids.append(event.agent_id)
    return agent_ids


def _select_agent_events(
    events: list[SimulationEvent],
    agent_id: str,
    cutoff_round: int | None,
) -> list[SimulationEvent]:
    selected: list[SimulationEvent] = []
    for event in events:
        if getattr(event, "agent_id", None) != agent_id:
            continue
        if cutoff_round is not None and event.round_number >= cutoff_round:
            continue
        selected.append(event)
    return selected


def _split_generations(agent_events: list[SimulationEvent], agent_id: str) -> list[_Generation]:
    generations: list[_Generation] = []
    for event in agent_events:
        if isinstance(event, AgentRegistered):
            if generations and generations[-1].model == event.model:
                continue
            generations.append(
                _Generation(
                    registration=event, model=event.model, provider=event.provider, events=[]
                )
            )
        elif isinstance(event, AgentSwappedMidRun):
            if not generations:
                raise ValueError(f"Agent {agent_id!r} swapped before it registered")
            generations.append(
                _Generation(
                    registration=generations[-1].registration,
                    model=event.new_model,
                    provider=event.new_provider,
                    events=[],
                )
            )
        elif generations:
            generations[-1].events.append(event)
    return generations


def _build_steps(generation: _Generation) -> list[AtifStep]:
    pricing = find_pricing(model=generation.model)
    results_by_call_id = {
        event.call_id: event for event in generation.events if isinstance(event, ToolResultReceived)
    }
    steps = [build_system_prompt_step(step_id=1, registration=generation.registration)]
    failed_cycles: list[AgentRunCycleFailed] = []
    for event in generation.events:
        step_id = len(steps) + 1
        if isinstance(event, (InjectionDelivered, WorldEventDelivered)):
            steps.append(build_delivered_text_step(step_id=step_id, event=event))
        elif isinstance(event, ContextCompacted):
            steps.append(build_compaction_step(step_id=step_id, event=event))
        elif isinstance(event, AgentRunCycleFailed):
            failed_cycles.append(event)
        elif isinstance(event, LLMResponseReceived):
            steps.append(
                build_agent_step(
                    step_id=step_id,
                    event=event,
                    model_name=generation.model,
                    pricing=pricing,
                    results_by_call_id=results_by_call_id,
                    failed_cycles=failed_cycles,
                )
            )
            failed_cycles = []
    return steps


def _build_final_metrics(steps: list[AtifStep]) -> AtifFinalMetrics:
    step_metrics = [step.metrics for step in steps if step.metrics is not None]
    costs = [metrics.cost_usd for metrics in step_metrics]
    total_cost_usd: float | None = None
    if all(cost is not None for cost in costs):
        total_cost_usd = sum(cost for cost in costs if cost is not None)
    return AtifFinalMetrics(
        total_prompt_tokens=sum(metrics.prompt_tokens for metrics in step_metrics),
        total_completion_tokens=sum(metrics.completion_tokens for metrics in step_metrics),
        total_cached_tokens=sum(metrics.cached_tokens for metrics in step_metrics),
        total_cost_usd=total_cost_usd,
        total_steps=len(steps),
    )


def _build_trajectory(
    generation: _Generation,
    generation_index: int,
    generation_count: int,
    run_id: str,
    scenario_name: str,
    scenario_config: dict[str, Any],
    cutoff_round: int | None,
) -> AtifTrajectory:
    registration = generation.registration
    trajectory_id = f"{run_id}/{registration.agent_id}"
    if generation_count > 1:
        trajectory_id = f"{trajectory_id}/gen{generation_index}"
    steps = _build_steps(generation=generation)
    return AtifTrajectory(
        schema_version=ATIF_SCHEMA_VERSION,
        session_id=run_id,
        trajectory_id=trajectory_id,
        agent=AtifAgent(
            name=f"glossogen:{scenario_name}/{registration.role_name}",
            version=version("glossogen"),
            model_name=generation.model,
            tool_definitions=[{"name": tool_name} for tool_name in registration.tool_names],
            extra={
                "agent_id": registration.agent_id,
                "provider": generation.provider,
                "channel_ids": registration.channel_ids,
                "max_tokens": registration.max_tokens,
            },
        ),
        steps=steps,
        final_metrics=_build_final_metrics(steps=steps),
        extra={
            "scenario_name": scenario_name,
            "scenario_config": scenario_config,
            "generation": generation_index,
            "cutoff_round": cutoff_round,
        },
    )


def build_run_trajectories(
    events: list[SimulationEvent],
    run_id: str,
    scenario_name: str,
    cutoff_round: int | None,
) -> list[AtifTrajectory]:
    """Every agent's trajectories, agents in registration order."""
    return [
        trajectory
        for agent_id in registered_agent_ids(events=events)
        for trajectory in build_agent_trajectories(
            events=events,
            run_id=run_id,
            scenario_name=scenario_name,
            agent_id=agent_id,
            cutoff_round=cutoff_round,
        )
    ]


def trajectory_file_name(trajectory: AtifTrajectory) -> str:
    """``<agent_id>.json``, or ``<agent_id>.gen<k>.json`` for a seat with several generations."""
    session_prefix = f"{trajectory.session_id}/"
    local_id = trajectory.trajectory_id.removeprefix(session_prefix)
    return f"{local_id.replace('/', '.')}.json"


def serialize_trajectory(trajectory: AtifTrajectory) -> str:
    """The ATIF JSON document, with unset optional fields omitted as the spec expects."""
    return trajectory.model_dump_json(indent=2, exclude_none=True)
