"""Per-team round state, the outcome a round leaves, and how a round is scored.

A team is correct only when every member submitted the round's answer, within
the character budget when one is set. Among correct teams, the fewest link
characters wins. ``score_round`` is the one place that rule lives, read by the
live world and by the event-log reconstruction alike.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple, Self

from glossogen.engine.fewest_characters_winner import fewest_characters_winners
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject


class IntersectionOutcome(NamedTuple):
    """One team's result for one round.

    ``agreed`` is whether every member submitted and all submitted the same
    object, right or wrong. ``won`` holds only in two-team runs, for the
    correct team (or tied teams) with the fewest characters. The ``opponent_*``
    fields describe the other team and are ``None`` with one team.
    """

    round_number: int
    team_id: str
    members_required: int
    members_submitted: int
    members_correct: int
    agreed: bool
    budget_exceeded: bool
    characters_used: int
    correct: bool
    won: bool
    competitive: bool
    opponent_correct: bool | None
    opponent_characters: int | None


class TeamSnapshot(NamedTuple):
    """A team's end-of-round state, ready to score."""

    team_id: str
    members_required: int
    members_submitted: int
    members_correct: int
    agreed: bool
    budget_exceeded: bool
    characters: int

    @property
    def correct(self) -> bool:
        """Every member submitted the answer, within budget."""
        return self.members_correct == self.members_required and not self.budget_exceeded


@dataclass
class TeamState:
    """What the world tracks for one team during a round."""

    team_id: str
    link_channel_id: str
    member_agent_ids: tuple[str, ...]
    submissions_by_agent: dict[str, BoardObject]
    locked: bool
    characters_at_lock: int
    round_budget_exceeded: bool

    @classmethod
    def fresh(cls, team_id: str, link_channel_id: str, member_agent_ids: tuple[str, ...]) -> Self:
        """A team at the start of a round: nothing submitted, nothing spent."""
        return cls(
            team_id=team_id,
            link_channel_id=link_channel_id,
            member_agent_ids=member_agent_ids,
            submissions_by_agent={},
            locked=False,
            characters_at_lock=0,
            round_budget_exceeded=False,
        )

    @property
    def members_required(self) -> int:
        """Every member must submit."""
        return len(self.member_agent_ids)

    def snapshot(self, answer: BoardObject, characters_used: int) -> TeamSnapshot:
        """This team's state for scoring.

        A locked team is charged what it had spent when its last member
        submitted, so nothing said afterwards changes its score.
        """
        characters = characters_used
        if self.locked:
            characters = self.characters_at_lock
        return snapshot_from_submissions(
            team_id=self.team_id,
            members_required=self.members_required,
            submissions=list(self.submissions_by_agent.values()),
            answer=answer,
            budget_exceeded=self.round_budget_exceeded,
            characters=characters,
        )

    def reset_for_new_round(self) -> None:
        """Clear the submissions, the lock and the budget flag."""
        self.submissions_by_agent = {}
        self.locked = False
        self.characters_at_lock = 0
        self.round_budget_exceeded = False


def snapshot_from_submissions(
    team_id: str,
    members_required: int,
    submissions: Sequence[BoardObject],
    answer: BoardObject,
    budget_exceeded: bool,
    characters: int,
) -> TeamSnapshot:
    """Summarise one team's submissions against the round's answer."""
    return TeamSnapshot(
        team_id=team_id,
        members_required=members_required,
        members_submitted=len(submissions),
        members_correct=sum(1 for submission in submissions if submission == answer),
        agreed=len(submissions) == members_required and len(set(submissions)) == 1,
        budget_exceeded=budget_exceeded,
        characters=characters,
    )


def score_round(
    round_number: int, snapshots: Sequence[TeamSnapshot], competitive: bool
) -> tuple[IntersectionOutcome, ...]:
    """Apply the correctness gate, then fewest-characters-wins, in team order."""
    winners = fewest_characters_winners(
        characters_by_eligible_team_id={
            snapshot.team_id: snapshot.characters for snapshot in snapshots if snapshot.correct
        }
    )
    outcomes: list[IntersectionOutcome] = []
    for snapshot in snapshots:
        opponent = _opponent_of(snapshot=snapshot, snapshots=snapshots, competitive=competitive)
        opponent_correct: bool | None = None
        opponent_characters: int | None = None
        if opponent is not None:
            opponent_correct = opponent.correct
            opponent_characters = opponent.characters
        outcomes.append(
            IntersectionOutcome(
                round_number=round_number,
                team_id=snapshot.team_id,
                members_required=snapshot.members_required,
                members_submitted=snapshot.members_submitted,
                members_correct=snapshot.members_correct,
                agreed=snapshot.agreed,
                budget_exceeded=snapshot.budget_exceeded,
                characters_used=snapshot.characters,
                correct=snapshot.correct,
                won=competitive and snapshot.team_id in winners,
                competitive=competitive,
                opponent_correct=opponent_correct,
                opponent_characters=opponent_characters,
            )
        )
    return tuple(outcomes)


def _opponent_of(
    snapshot: TeamSnapshot, snapshots: Sequence[TeamSnapshot], competitive: bool
) -> TeamSnapshot | None:
    """The other team's snapshot in a two-team run."""
    if not competitive:
        return None
    others = [other for other in snapshots if other.team_id != snapshot.team_id]
    if not others:
        return None
    return others[0]


def outcome_reason(outcome: IntersectionOutcome) -> str:
    """A one-line reason for the round result the clock records."""
    counts = (
        f"{outcome.members_correct}/{outcome.members_required} submitted the answer, "
        f"{outcome.characters_used} chars"
    )
    if outcome.members_submitted < outcome.members_required:
        return (
            f"only {outcome.members_submitted}/{outcome.members_required} members submitted "
            f"({counts})"
        )
    if outcome.budget_exceeded:
        return f"over budget ({counts})"
    if outcome.won:
        return f"won ({counts})"
    if outcome.correct and outcome.competitive:
        return f"correct but the other team used fewer characters ({counts})"
    if outcome.correct:
        return f"correct ({counts})"
    if not outcome.agreed:
        return f"members submitted different objects ({counts})"
    return f"every member submitted the same wrong object ({counts})"
