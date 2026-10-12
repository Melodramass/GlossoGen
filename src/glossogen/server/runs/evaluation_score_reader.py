"""Reading a run's per-metric scores out of its evaluation report.

Every run summary carries these scores, and some listings build a summary for
every run in a group (MCP ``list_runs``, the exports, the status filter). Over
4,738 local runs, reading every report took such a listing from 1.4s to 2.0s. The
scores are therefore held per report, keyed on its modification time and size, so
a run whose report has not changed costs one ``stat`` and a repeat listing takes
1.6s. ``write_report`` replaces a report atomically, so a rewritten report
presents a new key.
"""

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, ValidationError

from glossogen.server.runs.models import EvaluationScore

logger = logging.getLogger(__name__)

# About twice the local runs directory measured above. An entry measured 7.5 KB
# on average, so a full cache holds about 75 MB. A group with more evaluated runs
# than this re-reads reports on each listing that covers all of them.
MAX_CACHED_REPORTS = 10_000


class _ReportScores(BaseModel):
    """The part of an evaluation report the scores come from; every other field is skipped."""

    measurements: list[EvaluationScore]


class _CachedScores(NamedTuple):
    """One report's scores and the modification time and size of the file they came from."""

    modified_ns: int
    size: int
    scores: tuple[EvaluationScore, ...]


_CACHE: OrderedDict[Path, _CachedScores] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def read_evaluation_scores(report_path: Path) -> list[EvaluationScore] | None:
    """Return the report's scores in report order, or None when the run has no report.

    A report that cannot be read or parsed yields an empty list and one logged
    exception per version of the file, so one bad report costs that run its
    scores rather than failing the listing. Called from worker threads.
    """
    try:
        stat = report_path.stat()
    except FileNotFoundError:
        return None
    with _CACHE_LOCK:
        cached = _CACHE.get(report_path)
        if (
            cached is not None
            and cached.modified_ns == stat.st_mtime_ns
            and cached.size == stat.st_size
        ):
            _CACHE.move_to_end(report_path)
            return list(cached.scores)
    scores = _parse_scores(report_path=report_path)
    with _CACHE_LOCK:
        _CACHE[report_path] = _CachedScores(
            modified_ns=stat.st_mtime_ns, size=stat.st_size, scores=scores
        )
        _CACHE.move_to_end(report_path)
        while len(_CACHE) > MAX_CACHED_REPORTS:
            _CACHE.popitem(last=False)
    return list(scores)


def _parse_scores(report_path: Path) -> tuple[EvaluationScore, ...]:
    """Read the report's scores, or none when the file cannot be read or does not parse."""
    try:
        report = _ReportScores.model_validate_json(report_path.read_bytes())
    except (OSError, ValidationError):
        logger.exception("Failed to read evaluation scores from %s", report_path)
        return ()
    return tuple(report.measurements)
