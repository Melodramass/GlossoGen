"""Generated rounds have the structure they declare, at every team size.

The sweep script runs the same checks over many more seeds before a cohort; these
hold a sample of them on every commit.
"""

import pytest

from glossogen.scenarios.spot_the_intersection.board_certification import (
    ObjectKind,
    certify_boards,
)
from glossogen.scenarios.spot_the_intersection.board_generation import (
    BoardGenerationError,
    BoardSettings,
    RoundBoards,
    generate_round,
    generate_rounds,
    planted_per_board,
)
from glossogen.scenarios.spot_the_intersection.board_rendering import render_board_line
from glossogen.scenarios.spot_the_intersection.knobs import MAX_TEAM_SIZE
from glossogen.scenarios.spot_the_intersection.single_board_guessers import single_board_hit_rates

SEEDS = range(8)
ROUNDS = 15


def settings_for(team_size: int, grid_size: int) -> BoardSettings:
    """The default preset's distributions at ``team_size``, decoys off below three viewers."""
    decoys = [1, 2, 3]
    if team_size < 3:
        decoys = [0]
    return BoardSettings(
        team_size=team_size,
        grid_size=grid_size,
        near_misses=True,
        decoy_count_values=decoys,
        decoy_count_weights=[1] * len(decoys),
        filler_count_values=[2, 4, 6],
        filler_count_weights=[1, 1, 1],
    )


def sample_rounds(team_size: int) -> list[RoundBoards]:
    """Every round of a few seeds on a grid twice the size of the largest board."""
    settings = settings_for(team_size=team_size, grid_size=8)
    rounds: list[RoundBoards] = []
    for seed in SEEDS:
        rounds.extend(generate_rounds(seed=seed, round_count=ROUNDS, settings=settings))
    return rounds


@pytest.mark.parametrize("team_size", range(2, MAX_TEAM_SIZE + 1))
def test_every_round_recertifies_from_its_own_lines(team_size: int) -> None:
    for round_boards in sample_rounds(team_size=team_size):
        result = certify_boards(
            board_lines=round_boards.board_lines,
            grid_size=round_boards.grid_size,
            declared=round_boards.declared,
            require_every_board=True,
        )

        assert result.failures == ()
        assert result.certificate == round_boards.certificate


@pytest.mark.parametrize("team_size", [2, 3, 4, 8, 12])
def test_rounds_hold_the_planted_structure(team_size: int) -> None:
    for round_boards in sample_rounds(team_size=team_size):
        kinds = [entry.kind for entry in round_boards.declared]
        sizes = {len(board) for board in round_boards.boards}

        assert sizes == {round_boards.board_size}
        assert kinds.count(ObjectKind.ANSWER) == 1
        if team_size >= 3:
            assert kinds.count(ObjectKind.NEAR_MISS) == team_size
            assert kinds.count(ObjectKind.STAND_IN) == team_size
        decoys = [entry for entry in round_boards.declared if entry.kind is ObjectKind.DECOY]
        assert len(decoys) == round_boards.decoy_count
        assert all(2 <= len(entry.seats) < team_size for entry in decoys)
        fillers = [entry for entry in round_boards.declared if entry.kind is ObjectKind.FILLER]
        assert all(len(entry.seats) == 1 for entry in fillers)


def test_board_size_is_the_planted_objects_plus_the_drawn_counts() -> None:
    for round_boards in sample_rounds(team_size=5):
        planted = planted_per_board(team_size=5, near_misses=True)

        assert round_boards.board_size == (
            planted + round_boards.decoy_count + round_boards.filler_count
        )


def test_the_same_seed_gives_the_same_boards() -> None:
    settings = settings_for(team_size=4, grid_size=6)

    first = generate_rounds(seed=42, round_count=5, settings=settings)
    second = generate_rounds(seed=42, round_count=5, settings=settings)

    assert first == second


def test_a_round_does_not_depend_on_how_many_rounds_the_run_has() -> None:
    """A fork that extends a run must replay its earlier rounds unchanged."""
    settings = settings_for(team_size=4, grid_size=6)

    short = generate_rounds(seed=42, round_count=3, settings=settings)
    alone = generate_round(seed=42, round_number=3, settings=settings)

    assert short[2] == alone


def test_different_seeds_give_different_boards() -> None:
    settings = settings_for(team_size=4, grid_size=6)

    assert generate_round(seed=1, round_number=1, settings=settings) != generate_round(
        seed=2, round_number=1, settings=settings
    )


def test_no_single_board_points_at_the_answer() -> None:
    settings = settings_for(team_size=4, grid_size=6)
    rounds: list[RoundBoards] = []
    for seed in range(150):
        rounds.extend(generate_rounds(seed=seed, round_count=ROUNDS, settings=settings))

    leaking = [rate for rate in single_board_hit_rates(rounds=rounds) if rate.leaks]

    assert leaking == []


def test_the_leak_check_catches_an_answer_listed_first() -> None:
    """The check has to be able to fail, or passing it means nothing."""
    settings = settings_for(team_size=4, grid_size=6)
    rounds = generate_rounds(seed=7, round_count=ROUNDS, settings=settings)
    reordered: list[RoundBoards] = []
    for round_boards in rounds:
        answer_line = render_board_line(obj=round_boards.certificate.answer)
        lines = tuple(
            (answer_line, *[line for line in board if line != answer_line])
            for board in round_boards.board_lines
        )
        reordered.append(round_boards._replace(board_lines=lines))

    leaking = {rate.guesser for rate in single_board_hit_rates(rounds=reordered) if rate.leaks}

    assert "listed_first" in leaking


def test_a_round_that_cannot_certify_raises_instead_of_being_played() -> None:
    settings = settings_for(team_size=8, grid_size=3)

    with pytest.raises(BoardGenerationError):
        generate_round(seed=42, round_number=1, settings=settings)
