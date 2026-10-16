"""World simulation for the spot_the_intersection scenario.

Holds the run's certified boards, meters each team's link characters, and
records each viewer's submission. A team locks once every member has submitted,
latching its character count, and link traffic after that is not metered. When
the round ends every team is scored (see :mod:`world_state`) and told its result
on its link channel. The answer is never revealed.
"""

from collections.abc import Sequence
from typing import Any, NamedTuple

from glossogen.engine.round_outcome_log import RoundOutcomeLog
from glossogen.engine.round_world import RoundWorld
from glossogen.engine.team_declaration import TeamSpec
from glossogen.runtime.scenario_world import MessageEvent, WorldContext
from glossogen.scenarios.spot_the_intersection.board_generation import RoundBoards
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject
from glossogen.scenarios.spot_the_intersection.ids import (
    ANSWER_LOCKED_MARKER,
    BUDGET_EXCEEDED_MARKER,
    BUDGET_LOW_MARKER,
    ROUND_LOST_MARKER,
    ROUND_RESULT_MARKER,
    ROUND_WON_MARKER,
)
from glossogen.scenarios.spot_the_intersection.outcome_reconstruction import (
    restore_outcomes_from_events,
)
from glossogen.scenarios.spot_the_intersection.seats import Seat, seats_by_agent_id
from glossogen.scenarios.spot_the_intersection.world_state import (
    IntersectionOutcome,
    TeamState,
    score_round,
)

_THRESHOLD_LOW = "low"
_THRESHOLD_EXCEEDED = "exceeded"


class SubmissionReceipt(NamedTuple):
    """What recording one viewer's submission did to its team."""

    correct: bool
    completed_team: bool
    members_submitted: int
    members_required: int
    team_characters: int


class SpotTheIntersectionWorld(RoundWorld):
    """Per-team world that meters link characters and locks complete teams."""

    def __init__(
        self,
        rounds: Sequence[RoundBoards],
        team_specs: tuple[TeamSpec, ...],
        postmortem_channel_ids: frozenset[str],
        postmortem_globally_disabled: bool,
        competitive: bool,
        round_time_budget_seconds: int,
    ) -> None:
        super().__init__(
            team_specs=team_specs,
            round_budget_thresholds=(_THRESHOLD_EXCEEDED, _THRESHOLD_LOW),
            postmortem_channel_ids=postmortem_channel_ids,
            postmortem_globally_disabled=postmortem_globally_disabled,
        )
        self._rounds = tuple(rounds)
        self._competitive = competitive
        self._budget = round_time_budget_seconds
        self._seats = seats_by_agent_id(teams=team_specs)
        self._teams: dict[str, TeamState] = {
            spec.team_id: TeamState.fresh(
                team_id=spec.team_id,
                link_channel_id=spec.task.channel_id,
                member_agent_ids=tuple(role.agent_id for role in spec.roles),
            )
            for spec in team_specs
        }
        self._current: RoundBoards | None = None
        self._outcome_log: RoundOutcomeLog[IntersectionOutcome] = RoundOutcomeLog(
            team_ids=tuple(self._teams)
        )

    @property
    def team_ids(self) -> list[str]:
        """The teams this world tracks, in declared order."""
        return list(self._teams)

    @property
    def current_round_boards(self) -> RoundBoards | None:
        """The boards of the round in play, once one has started."""
        return self._current

    def round_boards(self, round_number: int) -> RoundBoards:
        """The certified boards of ``round_number``."""
        return self._rounds[round_number - 1]

    def seat_of(self, agent_id: str) -> Seat | None:
        """The seat ``agent_id`` holds, or ``None`` for an agent with no board."""
        return self._seats.get(agent_id)

    def has_submitted(self, agent_id: str) -> bool:
        """Whether ``agent_id`` has submitted this round."""
        seat = self._seats[agent_id]
        return agent_id in self._teams[seat.team_id].submissions_by_agent

    def record_submission(self, agent_id: str, obj: BoardObject) -> SubmissionReceipt:
        """Store one viewer's submission; lock its team once every member has submitted.

        Locking latches the team's character count synchronously, so nothing
        said after the last submission changes the score.
        """
        current = self._current
        if current is None:
            raise RuntimeError("no round is in play")
        team = self._teams[self._seats[agent_id].team_id]
        team.submissions_by_agent[agent_id] = obj
        characters = self.characters_used(team_id=team.team_id)
        completed = len(team.submissions_by_agent) == team.members_required
        if completed:
            team.locked = True
            team.characters_at_lock = characters
        return SubmissionReceipt(
            correct=obj == current.certificate.answer,
            completed_team=completed,
            members_submitted=len(team.submissions_by_agent),
            members_required=team.members_required,
            team_characters=characters,
        )

    def all_teams_done(self) -> bool:
        """Every team has locked its answer or spent its budget."""
        return all(team.locked or team.round_budget_exceeded for team in self._teams.values())

    def outcome_for(self, team_id: str, round_number: int) -> IntersectionOutcome | None:
        """``team_id``'s recorded outcome for ``round_number``, if scored."""
        return self._outcome_log.recorded_for(team_id=team_id, round_number=round_number)

    def previous_outcome(self, team_id: str) -> IntersectionOutcome | None:
        """``team_id``'s most recent outcome, or ``None`` before any round is scored."""
        outcomes = self._outcome_log.all_for(team_id=team_id)
        if not outcomes:
            return None
        return outcomes[-1]

    def mark_round_outcome(self, round_number: int) -> None:
        """Score ``round_number`` for every team, once."""
        current = self._current
        if current is None or current.round_number != round_number:
            return
        if any(
            self._outcome_log.recorded_for(team_id=team_id, round_number=round_number) is not None
            for team_id in self._teams
        ):
            return
        snapshots = [
            team.snapshot(
                answer=current.certificate.answer,
                characters_used=self.characters_used(team_id=team_id),
            )
            for team_id, team in self._teams.items()
        ]
        for outcome in score_round(
            round_number=round_number, snapshots=snapshots, competitive=self._competitive
        ):
            self._outcome_log.record(
                team_id=outcome.team_id, round_number=round_number, outcome=outcome
            )

    def finalize_round_sync(self, round_number: int) -> None:
        """Score the round just played if needed, then load ``round_number``."""
        if not 1 <= round_number <= len(self._rounds):
            raise ValueError(f"round {round_number} is outside 1..{len(self._rounds)}")
        if round_number >= 2:
            self.mark_round_outcome(round_number=round_number - 1)
        self._current = self._rounds[round_number - 1]
        # After the outcome above, which reads the counters of the round that ended.
        self.begin_round()

    def begin_round(self) -> None:
        """Clear the engine's per-round counters and every team's own state."""
        super().begin_round()
        for team in self._teams.values():
            team.reset_for_new_round()

    def restore_outcomes_from_events(self, events: list[Any]) -> None:
        """Seed every team's outcome history from a recorded event log on resume."""
        restore_outcomes_from_events(
            teams=self._teams,
            outcome_log=self._outcome_log,
            competitive=self._competitive,
            budget=self._budget,
            events=events,
        )

    async def announce_team_locked(self, team_id: str) -> None:
        """Tell the team its answer is locked."""
        team = self._teams[team_id]
        await self._world_context.send_update_to_channel(
            channel_id=team.link_channel_id,
            text=(
                f"{ANSWER_LOCKED_MARKER}. Every member has submitted; your team's answer is "
                "locked for this round. Results are revealed when the round ends."
            ),
        )

    async def emit_round_terminal_notification(self) -> None:
        """Tell each team its result once the round has ended."""
        current = self._current
        if current is None:
            return
        for team_id, team in self._teams.items():
            outcome = self.outcome_for(team_id=team_id, round_number=current.round_number)
            if outcome is None:
                continue
            await self._world_context.send_update_to_channel(
                channel_id=team.link_channel_id, text=_terminal_text(outcome=outcome)
            )

    def on_message(self, agent_id: str, channel_id: str, text: str, token_count: int) -> None:
        """Meter a link message until its team locks, then flag an exhausted budget."""
        team_id = self.team_for_task_channel(channel_id=channel_id)
        if team_id is None:
            return
        team = self._teams[team_id]
        if team.locked:
            # Charged before this check, post-lock chatter would cost a team
            # characters its score no longer counts.
            return
        super().on_message(
            agent_id=agent_id, channel_id=channel_id, text=text, token_count=token_count
        )
        if self._budget > 0 and self.characters_used(team_id=team_id) >= self._budget:
            team.round_budget_exceeded = True

    async def on_message_async(self, event: MessageEvent, context: WorldContext) -> None:
        """Announce a low or exhausted budget once each per round."""
        _ = context
        team_id = self.team_for_task_channel(channel_id=event.channel_id)
        if team_id is None or self._budget <= 0:
            return
        team = self._teams[team_id]
        used = self.characters_used(team_id=team_id)
        if team.round_budget_exceeded and self.claim_round_budget_threshold(
            team_id=team_id, round_budget_threshold=_THRESHOLD_EXCEEDED
        ):
            await context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. Your team has sent {used} characters; the budget "
                    f"was {self._budget}. This round can no longer be won."
                ),
            )
            return
        if used >= self._budget * 0.75 and self.claim_round_budget_threshold(
            team_id=team_id, round_budget_threshold=_THRESHOLD_LOW
        ):
            await context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=(
                    f"{BUDGET_LOW_MARKER}. {self._budget - used} of {self._budget} budget "
                    "characters remain."
                ),
            )


def _terminal_text(outcome: IntersectionOutcome) -> str:
    """The end-of-round result one team reads on its link."""
    characters = f"{outcome.characters_used} characters"
    if outcome.members_submitted < outcome.members_required:
        return (
            f"{ROUND_RESULT_MARKER}. Your team did not finish: only {outcome.members_submitted} "
            f"of {outcome.members_required} members submitted, and every member must submit."
        )
    if outcome.budget_exceeded:
        return (
            f"{ROUND_RESULT_MARKER}. Communication budget exceeded ({characters}); your team "
            "could not win this round."
        )
    correct_count = (
        f"{outcome.members_correct} of {outcome.members_required} members submitted the "
        "correct object"
    )
    if not outcome.competitive:
        if outcome.correct:
            return (
                f"{ROUND_RESULT_MARKER}. Correct: every member found the object, "
                f"using {characters}."
            )
        return f"{ROUND_RESULT_MARKER}. Incorrect: {correct_count}, using {characters}."
    if outcome.won:
        return (
            f"{ROUND_WON_MARKER}. Every member found the object, using {characters}, the fewest "
            "of the teams that got it right."
        )
    if outcome.correct:
        return (
            f"{ROUND_LOST_MARKER}. Every member found the object using {characters}; the other "
            "team used fewer."
        )
    return f"{ROUND_LOST_MARKER}. {correct_count}, using {characters}."
