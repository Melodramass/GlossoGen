"""Guesses at the answer from one board alone, to test whether a board gives it away.

Each guesser reads one board's lines, as a viewer does, and names one object.
Picking a line at random names the answer with probability ``1 / board_size``,
so a guesser that does measurably better has found something about how boards
are built that a viewer could exploit without talking. Other ways of exploiting
a board are not tested.

Every board of a round holds the same answer, so a round's boards are not
independent draws. The standard error is computed over rounds, which is why a
guesser favouring one cell does not look significant just because a team has
many viewers.
"""

import math
from collections import Counter
from collections.abc import Callable, Sequence
from typing import NamedTuple

from glossogen.scenarios.spot_the_intersection.board_generation import RoundBoards
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject
from glossogen.scenarios.spot_the_intersection.board_rendering import parse_board_line

# How many standard errors above chance a guesser must be to count as a leak.
LEAK_Z_THRESHOLD = 4.0


class GuesserHitRate(NamedTuple):
    """How often one guesser named the answer, beside what chance would give.

    ``standard_error`` is the standard error of ``rate - chance``, computed
    with each round as one cluster.
    """

    guesser: str
    hits: int
    boards: int
    chance: float
    standard_error: float

    @property
    def rate(self) -> float:
        """The fraction of boards on which the guess was the answer."""
        return self.hits / self.boards

    @property
    def z_score(self) -> float:
        """How many standard errors the rate sits above chance.

        The spread is zero only when every round shows the same excess, as a
        guesser right on every board of equal-sized boards does; any excess
        over chance is then infinitely significant.
        """
        excess = self.rate - self.chance
        if self.standard_error == 0:
            if excess > 0:
                return math.inf
            return 0.0
        return excess / self.standard_error

    @property
    def leaks(self) -> bool:
        """Whether the guesser beats chance by more than ``LEAK_Z_THRESHOLD`` errors."""
        return self.z_score > LEAK_Z_THRESHOLD


class _RoundTally(NamedTuple):
    hits: int
    boards: int
    expected_hits: float


class _Guesser(NamedTuple):
    name: str
    guess: Callable[[Sequence[BoardObject], int], BoardObject]


def _listed_first(board: Sequence[BoardObject], grid_size: int) -> BoardObject:
    _ = grid_size
    return board[0]


def _listed_last(board: Sequence[BoardObject], grid_size: int) -> BoardObject:
    _ = grid_size
    return board[-1]


def _most_common_look(board: Sequence[BoardObject], grid_size: int) -> BoardObject:
    _ = grid_size
    counts = Counter(obj.look for obj in board)
    return max(board, key=lambda obj: counts[obj.look])


def _rarest_look(board: Sequence[BoardObject], grid_size: int) -> BoardObject:
    _ = grid_size
    counts = Counter(obj.look for obj in board)
    return min(board, key=lambda obj: counts[obj.look])


def _most_common_color(board: Sequence[BoardObject], grid_size: int) -> BoardObject:
    _ = grid_size
    counts = Counter(obj.color for obj in board)
    return max(board, key=lambda obj: counts[obj.color])


def _most_common_shape(board: Sequence[BoardObject], grid_size: int) -> BoardObject:
    _ = grid_size
    counts = Counter(obj.shape for obj in board)
    return max(board, key=lambda obj: counts[obj.shape])


def _nearest_centre(board: Sequence[BoardObject], grid_size: int) -> BoardObject:
    centre = (grid_size - 1) / 2
    return min(board, key=lambda obj: abs(obj.column - centre) + abs(obj.row - centre))


def _most_crowded_row(board: Sequence[BoardObject], grid_size: int) -> BoardObject:
    _ = grid_size
    counts = Counter(obj.row for obj in board)
    return max(board, key=lambda obj: counts[obj.row])


GUESSERS: tuple[_Guesser, ...] = (
    _Guesser(name="listed_first", guess=_listed_first),
    _Guesser(name="listed_last", guess=_listed_last),
    _Guesser(name="most_common_look", guess=_most_common_look),
    _Guesser(name="rarest_look", guess=_rarest_look),
    _Guesser(name="most_common_color", guess=_most_common_color),
    _Guesser(name="most_common_shape", guess=_most_common_shape),
    _Guesser(name="nearest_centre", guess=_nearest_centre),
    _Guesser(name="most_crowded_row", guess=_most_crowded_row),
)


def single_board_hit_rates(rounds: Sequence[RoundBoards]) -> list[GuesserHitRate]:
    """Run every guesser on every board of ``rounds``, read back from its lines.

    Raises ``ValueError`` for fewer than two rounds: the standard error is
    clustered by round, and one round gives it no spread to measure.
    """
    if len(rounds) < 2:
        raise ValueError(f"the leak check needs at least two rounds (got {len(rounds)})")
    tallies: dict[str, list[_RoundTally]] = {guesser.name: [] for guesser in GUESSERS}
    for round_boards in rounds:
        answer = round_boards.certificate.answer
        boards = [
            [parse_board_line(line=line, grid_size=round_boards.grid_size) for line in lines]
            for lines in round_boards.board_lines
        ]
        expected_hits = sum(1 / len(board) for board in boards)
        for guesser in GUESSERS:
            hits = sum(
                1 for board in boards if guesser.guess(board, round_boards.grid_size) == answer
            )
            tallies[guesser.name].append(
                _RoundTally(hits=hits, boards=len(boards), expected_hits=expected_hits)
            )
    return [_hit_rate(guesser=name, tallies=rows) for name, rows in tallies.items()]


def _hit_rate(guesser: str, tallies: Sequence[_RoundTally]) -> GuesserHitRate:
    """Pool one guesser's rounds, with the excess's standard error clustered by round."""
    boards = sum(tally.boards for tally in tallies)
    hits = sum(tally.hits for tally in tallies)
    chance = sum(tally.expected_hits for tally in tallies) / boards
    excess = hits / boards - chance
    squared = sum(
        (tally.hits - tally.expected_hits - excess * tally.boards) ** 2 for tally in tallies
    )
    standard_error = math.sqrt(squared * len(tallies) / (len(tallies) - 1)) / boards
    return GuesserHitRate(
        guesser=guesser,
        hits=hits,
        boards=boards,
        chance=chance,
        standard_error=standard_error,
    )
