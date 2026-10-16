"""The labels a run's detail reports, read from its ``labels.json``.

A file that is not a JSON list of strings used to reach ``RunDetailResponse`` as-is,
which failed its validation; it now reads as no labels.
"""

from pathlib import Path

import orjson
import pytest

from glossogen.models.event import RunStatus, SimulationEnded, SimulationStarted
from glossogen.server.runs.detail_reader import load_run_detail

SCENARIO = "veyru"


def _write_run(run_dir: Path, labels_file: bytes) -> Path:
    run_dir.mkdir(parents=True)
    started = SimulationStarted(
        round_number=0,
        run_id=f"{SCENARIO}/{run_dir.name}",
        scenario_name=SCENARIO,
        scenario_description="",
        channel_ids=["link"],
        provider="anthropic",
        scenario_config={},
    )
    ended = SimulationEnded(
        round_number=0,
        reason=RunStatus.SCENARIO_COMPLETE,
        total_messages=0,
        total_cost_usd=0.0,
    )
    log_path = run_dir / f"{SCENARIO}.jsonl"
    log_path.write_bytes(
        started.model_dump_json().encode() + b"\n" + ended.model_dump_json().encode() + b"\n"
    )
    (run_dir / "labels.json").write_bytes(labels_file)
    return log_path


async def test_the_detail_reports_the_labels_its_file_holds(tmp_path: Path) -> None:
    log_path = _write_run(
        run_dir=tmp_path / SCENARIO / "1770000100",
        labels_file=orjson.dumps(["baseline", "budget=800"]),
    )

    detail = await load_run_detail(log_path=log_path, children=[])

    assert detail.labels == ["baseline", "budget=800"]


@pytest.mark.parametrize(
    "labels_file",
    [
        pytest.param(orjson.dumps({"not": "a list"}), id="an object"),
        pytest.param(orjson.dumps([1, 2]), id="numbers"),
    ],
)
async def test_a_labels_file_that_is_not_a_list_of_strings_reads_as_no_labels(
    tmp_path: Path, labels_file: bytes
) -> None:
    log_path = _write_run(run_dir=tmp_path / SCENARIO / "1770000100", labels_file=labels_file)

    detail = await load_run_detail(log_path=log_path, children=[])

    assert detail.labels == []
