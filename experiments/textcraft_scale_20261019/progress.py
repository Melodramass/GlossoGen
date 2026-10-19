"""One line per job with live progress read from its event log.

  python progress.py [LABEL_PREFIX ...]
"""

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def summarize(directory: Path) -> str:
    paths = list(directory.glob("runs/textcraft_shared_workspace/*/textcraft_shared_workspace.jsonl"))
    if not paths:
        return "no log"
    events = []
    for line in paths[0].read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    acts = [e for e in events if e["event_type"] == "workspace_action_executed"]
    crafts = [e for e in events if e["event_type"] == "workspace_craft_completed"]
    calls = collections.Counter(
        (e.get("tool_name"), (e.get("arguments") or {}).get("wait_for"))
        for e in events
        if e["event_type"] == "tool_call_invoked"
    )
    failures = sum(1 for e in events if e["event_type"] == "agent_run_cycle_failed")
    released = [e for e in events if e["event_type"] == "workspace_request_released"]
    virtual = max((e["completed_at_s"] for e in released), default=0.0)
    longest = max((e["output_tokens"] for e in released), default=0)
    resolved = [e for e in events if e["event_type"] == "workspace_round_resolved"]
    status = "running"
    if resolved:
        r = resolved[0]
        status = f"DONE success={r['success']} {r['trigger']} vt={r.get('virtual_elapsed_seconds')}"
    rejected = sum(1 for a in acts if not a["accepted"])
    sends = calls[("send_message", None)]
    depot_waits = calls[("read_notifications", "depot")]
    message_waits = calls[("read_notifications", "message")]
    observes = calls[("observe", None)]
    finishes = calls[("read_notifications", "next_round")]
    return (
        f"{status} landed={len(crafts)}/72 acts={len(acts)} rejected={rejected} "
        f"requests={len(released)} max_out={longest} vt={virtual:.0f}s sends={sends} depot_waits={depot_waits} "
        f"msg_waits={message_waits} observes={observes} finished={finishes} cycle_failures={failures}"
    )


def main() -> None:
    prefixes = sys.argv[1:]
    for directory in sorted((ROOT / "jobs").iterdir()):
        if prefixes and not any(directory.name.startswith(p) for p in prefixes):
            continue
        if not (directory / "runs").exists():
            continue
        print(f"{directory.name:16s} {summarize(directory)}")


if __name__ == "__main__":
    main()
