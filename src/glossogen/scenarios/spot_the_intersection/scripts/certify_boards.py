r"""Certify spot_the_intersection boards across presets, team sizes and seeds.

For every shipped preset and every team size from 2 to the maximum, generates
``--seed-count`` seeds of every round, certifies each round again from its
rendered lines, and runs the single-board guessers over the lot. Prints one row
per (preset, team size) and exits non-zero if any round fails to generate or
re-certify, or any guesser beats chance by more than ``LEAK_Z_THRESHOLD``
standard errors.

Run it before launching a cohort on a new configuration. Each team size is
checked on the smallest grid the knobs accept for it, the tightest fit for its
boards:

    VIRTUAL_ENV= uv run --no-sync python -m \
      glossogen.scenarios.spot_the_intersection.scripts.certify_boards --seed-count 200
"""

import argparse
import math
import sys
from collections import Counter
from typing import Any, NamedTuple

from glossogen.scenarios.spot_the_intersection.board_certification import certify_boards
from glossogen.scenarios.spot_the_intersection.board_generation import (
    BoardGenerationError,
    RoundBoards,
    generate_rounds,
)
from glossogen.scenarios.spot_the_intersection.knobs import (
    MAX_TEAM_SIZE,
    SpotTheIntersectionKnobs,
    largest_board_size,
)
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario
from glossogen.scenarios.spot_the_intersection.single_board_guessers import (
    LEAK_Z_THRESHOLD,
    single_board_hit_rates,
)


class SweepRow(NamedTuple):
    """What one (preset, team size) configuration produced."""

    preset: str
    team_size: int
    grid_size: int
    rounds: int
    generation_errors: int
    recertification_failures: int
    attempts: Counter[int]
    worst_guesser: str
    worst_z_score: float
    problems: list[str]


def knobs_for(preset: dict[str, Any], team_size: int) -> SpotTheIntersectionKnobs:
    """The preset at ``team_size``, on the smallest grid the knobs accept.

    Decoys need three viewers, so a two-viewer team runs without them.
    """
    config = dict(preset)
    config["team_size"] = team_size
    if team_size < 3:
        config["decoy_count_values"] = [0]
        config["decoy_count_weights"] = [1]
    probe = SpotTheIntersectionKnobs.model_validate({**config, "grid_size": 26})
    config["grid_size"] = max(3, math.ceil(math.sqrt(2 * largest_board_size(knobs=probe))))
    return SpotTheIntersectionKnobs.model_validate(config)


def recertification_failures(rounds: list[RoundBoards], near_misses: bool) -> int:
    """Rounds whose own lines and declaration no longer certify."""
    failed = 0
    for round_boards in rounds:
        result = certify_boards(
            board_lines=round_boards.board_lines,
            grid_size=round_boards.grid_size,
            declared=round_boards.declared,
            require_every_board=near_misses,
        )
        if result.certificate is None or result.certificate != round_boards.certificate:
            failed += 1
    return failed


def sweep_configuration(
    preset_name: str, preset: dict[str, Any], team_size: int, seed_count: int
) -> SweepRow:
    """Generate, re-certify and probe every round of ``seed_count`` seeds."""
    knobs = knobs_for(preset=preset, team_size=team_size)
    rounds: list[RoundBoards] = []
    problems: list[str] = []
    generation_errors = 0
    for seed in range(seed_count):
        try:
            rounds.extend(
                generate_rounds(
                    seed=seed, round_count=knobs.round_count, settings=knobs.board_settings()
                )
            )
        except BoardGenerationError as error:
            generation_errors += 1
            problems.append(f"seed {seed}: {error}")
    recertified = recertification_failures(rounds=rounds, near_misses=knobs.near_misses)
    if recertified:
        problems.append(f"{recertified} round(s) failed re-certification")
    worst_guesser = ""
    worst_z_score = -math.inf
    for hit_rate in single_board_hit_rates(rounds=rounds):
        if hit_rate.z_score > worst_z_score:
            worst_guesser = hit_rate.guesser
            worst_z_score = hit_rate.z_score
        if hit_rate.leaks:
            problems.append(
                f"{hit_rate.guesser} names the answer on {hit_rate.rate:.1%} of boards "
                f"(chance {hit_rate.chance:.1%}, z={hit_rate.z_score:.1f} > {LEAK_Z_THRESHOLD})"
            )
    return SweepRow(
        preset=preset_name,
        team_size=team_size,
        grid_size=knobs.grid_size,
        rounds=len(rounds),
        generation_errors=generation_errors,
        recertification_failures=recertified,
        attempts=Counter(round_boards.attempts for round_boards in rounds),
        worst_guesser=worst_guesser,
        worst_z_score=worst_z_score,
        problems=problems,
    )


def print_row(row: SweepRow) -> None:
    """One line per configuration, then its problems indented beneath it."""
    redrawn = sum(count for attempts, count in row.attempts.items() if attempts > 1)
    most_attempts = max(row.attempts, default=0)
    print(
        f"{row.preset:20s} N={row.team_size:2d} grid={row.grid_size:2d} rounds={row.rounds:5d} "
        f"redrawn={redrawn:4d} max_attempts={most_attempts:3d} "
        f"errors={row.generation_errors} recertify_failures={row.recertification_failures} "
        f"worst_guesser={row.worst_guesser}(z={row.worst_z_score:+.1f})"
    )
    for problem in row.problems:
        print(f"    PROBLEM: {problem}")


def main() -> None:
    """Sweep every preset and team size; exit 1 on any problem."""
    parser = argparse.ArgumentParser(
        description="Certify spot_the_intersection boards across presets, team sizes and seeds."
    )
    parser.add_argument("--seed-count", type=int, required=True)
    args = parser.parse_args()
    any_problem = False
    for preset_name in SpotTheIntersectionScenario.knobs_preset_names():
        preset = SpotTheIntersectionScenario.load_knobs_preset(preset_name=preset_name)
        for team_size in range(2, MAX_TEAM_SIZE + 1):
            row = sweep_configuration(
                preset_name=preset_name,
                preset=preset,
                team_size=team_size,
                seed_count=args.seed_count,
            )
            print_row(row=row)
            any_problem = any_problem or bool(row.problems)
    if any_problem:
        print("FAILED: see PROBLEM lines above")
        sys.exit(1)
    print("OK: every round generated, re-certified, and no board gives the answer away")


if __name__ == "__main__":
    main()
