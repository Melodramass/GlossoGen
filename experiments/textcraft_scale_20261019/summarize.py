"""Per-arm table for the team-size scaling batch, paired with solo on each task.

Speedup is solo's virtual makespan over the arm's on the same task, counted on
tasks both solved; efficiency is speedup / agents. The oracle ceiling for
12 x 6 tasks with 30 s crafts is 3.0x at 3 agents and 9.0x at 10.

  python summarize.py            table
  python summarize.py --json     the per-job rows as JSON
"""

import argparse
import collections
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
ORACLE = {1: 1.0, 3: 3.0, 10: 9.0}


def crafts_by_agent(event_log: Path) -> collections.Counter[str]:
    counts: collections.Counter[str] = collections.Counter()
    for line in event_log.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event["event_type"] == "workspace_craft_completed":
            counts[event["agent_id"]] += 1
    return counts


def rows() -> list[dict[str, object]]:
    found = []
    for path in sorted((ROOT / "jobs").glob("*/result.json")):
        row = json.loads(path.read_text())
        if row.get("status") != "completed":
            continue
        if row.get("event_log"):
            counts = crafts_by_agent(REPO / str(row["event_log"]))
            total = sum(counts.values())
            row["busiest_share"] = max(counts.values()) / total if total else None
            row["agents_who_crafted"] = len(counts)
        found.append(row)
    return found


def median(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.median(values)


def fmt(value: float | None, pattern: str) -> str:
    if value is None:
        return "-"
    return pattern.format(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    table = rows()
    if args.json:
        print(json.dumps(table, indent=2))
        return
    solo = {
        r["task_id"]: r["virtual_elapsed_seconds"]
        for r in table
        if r["arm"] == "solo" and r.get("success")
    }
    arms = ["solo", "n3_nocomm", "n3_comm", "n10_nocomm", "n10_comm"]
    header = (
        f"{'arm':11s} {'done':>4s} {'solved':>6s} {'makespan':>8s} {'speedup':>7s} "
        f"{'eff':>5s} {'oracle':>6s} {'faster':>6s} {'busiest':>7s} {'crafters':>8s} "
        f"{'rejected':>8s} {'msgs':>5s} {'dwaits':>6s} {'Mtok_in':>7s} {'req':>5s}"
    )
    print(header)
    for arm in arms:
        group = [r for r in table if r["arm"] == arm]
        if not group:
            continue
        agents = int(group[0]["agents"])
        solved = [r for r in group if r.get("success")]
        speedups = [
            solo[r["task_id"]] / r["virtual_elapsed_seconds"]
            for r in solved
            if r["task_id"] in solo and r.get("virtual_elapsed_seconds")
        ]
        faster = sum(1 for s in speedups if s > 1)
        acts = [int(r["actions_used"]) for r in group]
        rejected = sum(int(r["failed_acts"]) for r in group) / max(1, sum(acts))
        speed = median(speedups)
        efficiency = None
        if speed is not None:
            efficiency = speed / agents
        print(
            f"{arm:11s} {len(group):4d} {len(solved):6d} "
            f"{fmt(median([r['virtual_elapsed_seconds'] for r in solved]), '{:8.0f}')} "
            f"{fmt(speed, '{:6.2f}x')} {fmt(efficiency, '{:5.2f}')} {ORACLE[agents]:5.1f}x "
            f"{faster:3d}/{len(speedups):<2d} "
            f"{fmt(median([r['busiest_share'] for r in group if r.get('busiest_share')]), '{:7.2f}')} "
            f"{fmt(median([r['agents_who_crafted'] for r in group if r.get('agents_who_crafted')]), '{:8.1f}')} "
            f"{rejected:8.2f} "
            f"{fmt(median([r['messages_sent'] for r in group]), '{:5.0f}')} "
            f"{fmt(median([r['waits_by_kind'].get('depot', 0) for r in group]), '{:6.0f}')} "
            f"{fmt(median([r['input_tokens'] / 1e6 for r in group]), '{:7.2f}')} "
            f"{fmt(median([r['requests'] for r in group]), '{:5.0f}')}"
        )


if __name__ == "__main__":
    main()
