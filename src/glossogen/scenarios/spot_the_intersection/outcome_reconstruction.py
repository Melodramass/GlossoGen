"""Rebuild per-team outcomes from a recorded event log on resume.

Used on resume, fork and replace-agent so the next round's briefing reports the
right previous result. Reads ``SpotTheIntersectionRoundStarted`` for each
round's answer as recorded, ``IntersectionSubmissionRecorded`` for each
member's submission and its team's character count at that moment,
``MessageSent`` on each team's link for a team that never locked, and
``RoundEnded`` for which rounds finished. Scoring goes through
:func:`score_round`, the rule the live world applies.

The answer comes from the log rather than from regenerating the round, so a run
recorded before a change to board generation is still scored on the boards it
played.
"""

from collections.abc import Sequence
from typing import Any

from glossogen.engine.round_outcome_log import RoundOutcomeLog
from glossogen.models.event import MessageSent, RoundEnded
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject
from glossogen.scenarios.spot_the_intersection.board_rendering import (
    parse_board_line,
    parse_cell_label,
)
from glossogen.scenarios.spot_the_intersection.events import (
    IntersectionSubmissionRecorded,
    SpotTheIntersectionRoundStarted,
)
from glossogen.scenarios.spot_the_intersection.world_state import (
    IntersectionOutcome,
    TeamSnapshot,
    TeamState,
    score_round,
    snapshot_from_submissions,
)


def restore_outcomes_from_events(
    teams: dict[str, TeamState],
    outcome_log: RoundOutcomeLog[IntersectionOutcome],
    competitive: bool,
    budget: int,
    events: list[Any],
) -> None:
    """Record an outcome for every round ``events`` shows finished.

    Raises ``ValueError`` for a finished round whose start was never recorded,
    since there is then no answer to score it against.
    """
    team_id_by_link = {team.link_channel_id: team.team_id for team in teams.values()}
    members = {team.team_id: frozenset(team.member_agent_ids) for team in teams.values()}
    submissions: dict[int, dict[str, list[IntersectionSubmissionRecorded]]] = {}
    characters: dict[int, dict[str, int]] = {}
    completed_rounds: set[int] = set()
    started: dict[int, SpotTheIntersectionRoundStarted] = {}
    for event in events:
        if isinstance(event, SpotTheIntersectionRoundStarted):
            started[event.round_number] = event
        elif isinstance(event, IntersectionSubmissionRecorded):
            submissions.setdefault(event.round_number, {}).setdefault(event.team_id, []).append(
                event
            )
        elif isinstance(event, MessageSent):
            team_id = team_id_by_link.get(event.message.channel_id)
            # The world's own notices on a link are not metered live either.
            if team_id is not None and event.message.sender_agent_id in members[team_id]:
                by_team = characters.setdefault(event.round_number, {})
                by_team[team_id] = by_team.get(team_id, 0) + len(event.message.text)
        elif isinstance(event, RoundEnded):
            completed_rounds.add(event.round_number)
    for round_number in sorted(completed_rounds):
        if any(
            outcome_log.recorded_for(team_id=team_id, round_number=round_number) is not None
            for team_id in teams
        ):
            continue
        round_started = started.get(round_number)
        if round_started is None:
            raise ValueError(f"round {round_number} ended but its start was never recorded")
        snapshots = [
            _snapshot(
                team=team,
                round_started=round_started,
                submissions=submissions.get(round_number, {}).get(team_id, []),
                unlocked_characters=characters.get(round_number, {}).get(team_id, 0),
                budget=budget,
            )
            for team_id, team in teams.items()
        ]
        for outcome in score_round(
            round_number=round_number, snapshots=snapshots, competitive=competitive
        ):
            outcome_log.record(team_id=outcome.team_id, round_number=round_number, outcome=outcome)


def _snapshot(
    team: TeamState,
    round_started: SpotTheIntersectionRoundStarted,
    submissions: Sequence[IntersectionSubmissionRecorded],
    unlocked_characters: int,
    budget: int,
) -> TeamSnapshot:
    """One team's scoring state for a finished round, from its recorded events.

    A team that locked is charged the count on its last submission, the latch
    the live world applied; one that did not is charged every link character.
    """
    characters = unlocked_characters
    if len(submissions) == team.members_required:
        characters = max(submission.team_characters for submission in submissions)
    objects = [
        _submitted_object(submission=submission, grid_size=round_started.grid_size)
        for submission in submissions
    ]
    return snapshot_from_submissions(
        team_id=team.team_id,
        members_required=team.members_required,
        submissions=objects,
        answer=parse_board_line(line=round_started.answer_line, grid_size=round_started.grid_size),
        budget_exceeded=budget > 0 and characters >= budget,
        characters=characters,
    )


def _submitted_object(submission: IntersectionSubmissionRecorded, grid_size: int) -> BoardObject:
    """The object a recorded submission named."""
    column, row = parse_cell_label(label=submission.cell, grid_size=grid_size)
    return BoardObject(shape=submission.shape, color=submission.color, column=column, row=row)
