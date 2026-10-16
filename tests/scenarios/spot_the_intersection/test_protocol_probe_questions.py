"""The protocol-probe boards are boards the default preset generates.

Each question's board is seat 1's board of one round of seed 3, at the default
preset's smallest, middle and largest board sizes. Seed 3 is not the presets'
seed, so a viewer in a run on the presets has never been sent these boards.
"""

import json

from glossogen.scenarios.spot_the_intersection.board_generation import generate_round
from glossogen.scenarios.spot_the_intersection.knobs import SpotTheIntersectionKnobs
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario

PROBE_SEED = 3
ROUND_BY_QUESTION_ID = {
    "viewer_00_smallest": 9,
    "viewer_01_middle": 6,
    "viewer_02_largest": 10,
}


def default_knobs() -> SpotTheIntersectionKnobs:
    """The default preset's validated knobs."""
    return SpotTheIntersectionKnobs.model_validate(
        SpotTheIntersectionScenario.load_knobs_preset(preset_name="knobs_default")
    )


def probe_boards() -> dict[str, str]:
    """Each question's board, keyed by question id."""
    scenario = SpotTheIntersectionScenario.create_from_config(
        config=default_knobs().model_dump(mode="json")
    )
    probe_config = scenario.get_protocol_probe_config()
    assert probe_config is not None
    questions = json.loads(probe_config.questions_path.read_text())
    return {question["id"]: question["inputs"]["my_board"] for question in questions}


def test_each_probe_board_is_seat_one_of_its_round() -> None:
    """Every question's board is the generated board, line for line in reading order."""
    knobs = default_knobs()
    expected = {}
    for question_id, round_number in ROUND_BY_QUESTION_ID.items():
        round_boards = generate_round(
            seed=PROBE_SEED, round_number=round_number, settings=knobs.board_settings()
        )
        expected[question_id] = "\n".join(f"- {line}" for line in round_boards.board_lines[0])

    assert probe_boards() == expected


def test_the_probe_boards_span_the_default_board_sizes() -> None:
    """The rounds give the default preset's smallest, middle and largest boards."""
    knobs = default_knobs()
    sizes = [
        generate_round(
            seed=PROBE_SEED, round_number=round_number, settings=knobs.board_settings()
        ).board_size
        for round_number in ROUND_BY_QUESTION_ID.values()
    ]

    assert sizes == [12, 15, 18]


def test_the_probe_seed_is_not_the_presets_seed() -> None:
    """No shipped preset plays the seed the probe boards come from."""
    for preset_name in SpotTheIntersectionScenario.knobs_preset_names():
        preset = SpotTheIntersectionScenario.load_knobs_preset(preset_name=preset_name)
        assert preset["seed"] != PROBE_SEED
