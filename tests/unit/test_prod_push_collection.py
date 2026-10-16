"""Which local runs ``push-to-prod`` and ``sync-metadata-to-prod`` pick up, and their labels.

A run is picked up only when its ``labels.json`` reads as a list of strings. The
labels read there travel on the ``LocalRun``, so the metadata sync diffs against
the same list the filter accepted rather than reading the file a second time.
"""

from pathlib import Path

from glossogen.prod_push import PushSpec, collect_local_runs


def _spec(runs_dir: Path, labels: frozenset[str]) -> PushSpec:
    return PushSpec(
        runs_dir=runs_dir,
        labels=labels,
        scenarios=None,
        require_report=False,
        dry_run=True,
        concurrency=1,
    )


def _run_dir(runs_dir: Path, run_dir_name: str) -> Path:
    run_dir = runs_dir / "veyru" / run_dir_name
    run_dir.mkdir(parents=True)
    return run_dir


def test_a_run_carries_the_labels_its_file_holds(tmp_path: Path) -> None:
    (_run_dir(runs_dir=tmp_path, run_dir_name="100") / "labels.json").write_text(
        '["baseline", "budget=800"]'
    )

    runs = collect_local_runs(spec=_spec(runs_dir=tmp_path, labels=frozenset()))

    assert [(run.run_id, run.labels) for run in runs] == [("veyru/100", ["baseline", "budget=800"])]


def test_a_run_with_a_missing_or_broken_labels_file_is_skipped(tmp_path: Path) -> None:
    _run_dir(runs_dir=tmp_path, run_dir_name="100")
    (_run_dir(runs_dir=tmp_path, run_dir_name="200") / "labels.json").write_text(
        '{"labels": ["baseline"]}'
    )
    (_run_dir(runs_dir=tmp_path, run_dir_name="300") / "labels.json").write_text("[]")

    runs = collect_local_runs(spec=_spec(runs_dir=tmp_path, labels=frozenset()))

    assert [run.run_id for run in runs] == ["veyru/300"]


def test_a_run_missing_a_required_label_is_skipped(tmp_path: Path) -> None:
    (_run_dir(runs_dir=tmp_path, run_dir_name="100") / "labels.json").write_text('["baseline"]')
    (_run_dir(runs_dir=tmp_path, run_dir_name="200") / "labels.json").write_text(
        '["baseline", "cross_team"]'
    )

    runs = collect_local_runs(spec=_spec(runs_dir=tmp_path, labels=frozenset({"cross_team"})))

    assert [run.run_id for run in runs] == ["veyru/200"]
