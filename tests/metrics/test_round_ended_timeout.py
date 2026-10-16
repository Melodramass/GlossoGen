"""`round_ended_timeout`: rounds that ran out of wall clock instead of finishing.

The counterpart to `round_ended_idle`. Together they partition the run, and the
split is what says whether agents finished talking or were cut off — which
changes what every throughput number on that run means.
"""

import json
from pathlib import Path

import pytest

from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, isolated_run, score_metrics
from tests.metrics.conftest import METRIC_RUN_GROUP, ROUND_COUNT

pytestmark = METRIC_RUN_GROUP

METRIC = "round_ended_timeout"


async def test_a_run_where_every_round_finished_scores_zero(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero timeouts is an observation, so the measurement is still written.

    Both agents park on a poll well inside the round's limit, so nothing times
    out. Dropping the entry would make "no round was cut off" and "never
    evaluated" the same thing.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(0.0)
    assert measurement.per_round == []
    assert scored.judge.calls == []


async def test_it_counts_the_rounds_the_clock_cut_off(
    timed_out_postmortem_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The non-zero half, which a run that always ends on idle cannot reach.

    These agents never park, so nothing can end a round except its wall-clock
    limit. Without this the metric could return a constant zero and the test
    above would still pass, while every real timeout went unreported.
    """
    scored = await score_metrics(
        run=timed_out_postmortem_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(float(ROUND_COUNT))
    assert len(measurement.per_round) == ROUND_COUNT


async def test_idle_and_timeout_partition_the_run(
    timed_out_postmortem_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A round ends one way or the other, never both.

    Asserting each count alone would pass just as well if every round were
    counted twice, which is exactly what a shared trigger-detection bug would
    produce.
    """
    scored = await score_metrics(
        run=timed_out_postmortem_run,
        metric_names=[METRIC, "round_ended_idle"],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    timed_out = scored.measurement(metric_name=METRIC).score
    idle = scored.measurement(metric_name="round_ended_idle").score
    assert timed_out + idle == pytest.approx(float(ROUND_COUNT))


@pytest.mark.parametrize("metric_name", [METRIC, "round_ended_idle"])
async def test_a_run_predating_round_ended_events_says_so_instead_of_counting(
    metric_name: str,
    timed_out_postmortem_run: MetricRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A log with rounds but no `round_ended` lines cannot be counted either way.

    Its zero says the run is too old to score, in the summary, so it is not
    read as "no round ended this way". Stripping the lines from a copy of a run
    that did time out shows the fallback wins over the triggers it can no
    longer see.
    """
    run = isolated_run(run=timed_out_postmortem_run, tmp_path=tmp_path)
    kept_lines = [
        line
        for line in run.log_path.read_text().splitlines()
        if json.loads(line)["event_type"] != "round_ended"
    ]
    run.log_path.write_text("\n".join(kept_lines) + "\n")

    scored = await score_metrics(
        run=run,
        metric_names=[metric_name],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=metric_name)
    assert measurement.score == pytest.approx(0.0)
    assert measurement.per_round == []
    assert "predates" in measurement.summary
