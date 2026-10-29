"""Team-size scaling with oracle-communication arms on 12 x 6 layered tasks, Qwen3.8-27B non-thinking.

Arms (all recipe_reveal=frontier, private raw items, 30 virtual seconds per craft):

  solo         one agent
  n3_nocomm    3 agents, no messaging
  n3_comm      3 agents, broadcast and direct messages
  n10_nocomm   10 agents, no messaging
  n10_comm     10 agents, broadcast and direct messages
  nN_feed      N agents, no messaging; every observation names who started/finished which craft
  nN_oracle    nN_feed plus a coordinator plan (list schedule at the 3.0x / 9.0x ceiling) per agent

Every arm can wait on depot items (read_notifications(wait_for="depot")). The bank
is 16 tasks of 72 crafts (tasks_w12_l6.json, seeds 1001-1016). Requests cost
1 s + output tokens / 50 virtual seconds. No team token cap; the team gets
ACTIONS_PER_STEP actions per witness step.

Start start_server.sh on every node first, then:

  python run_batch.py --nodes c642-071 --prepare-only
  python run_batch.py --nodes c642-071 --smoke LABEL [LABEL ...]
  python run_batch.py --nodes c642-071 c608-021 [--arms ...] [--jobs-per-node 3]

Finished jobs are skipped and failed ones retried, so the same command resumes.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("TEXTCRAFT_OUT", ROOT)).resolve()
"""Batch directory holding plan.json and jobs/; TEXTCRAFT_OUT keeps separate batches apart."""
REPO = ROOT.parents[1]
BANK = ROOT / "tasks_w12_l6.json"
BANK_TASKS = 16
MODEL = os.environ.get("TEXTCRAFT_MODEL", "Qwen/Qwen3.8-27B")
SCENARIO = "textcraft_shared_workspace"
PORT = 8010
API_KEY = "glossogen-local"
ARMS = {
    "solo": (1, False),
    "n3_nocomm": (3, False),
    "n3_comm": (3, True),
    "n10_nocomm": (10, False),
    "n10_comm": (10, True),
    "n3_feed": (3, False),
    "n3_oracle": (3, False),
    "n10_feed": (10, False),
    "n10_oracle": (10, False),
}
# Oracle communication, delivered by the environment instead of messages: feed arms see
# who started, finished or undid each craft; oracle arms also get a list-schedule plan.
ORACLE = {arm: dict(team_feed=True, oracle_plan=arm.endswith("_oracle"))
          for arm in ARMS if arm.endswith(("_feed", "_oracle"))}
CRAFT_SECONDS = 30.0
ACTIONS_PER_STEP = 10.0
AGENT_MAX_TOKENS = 16384
"""Normal replies stay under ~1.3k tokens; a runaway reply returns, truncated, within the
OpenAI client's 600 s timeout instead of being dropped and retried."""
RUNAWAY_TOKENS = 4096
"""A released request with more output tokens than this is counted as a runaway."""
COMPACTION_THRESHOLD = 96000
WALL_SECONDS = int(os.environ.get("TEXTCRAFT_WALL_SECONDS", "5400"))
"""Wall-clock safety net per job; the virtual round has no cap."""
DEADLINE = float(os.environ.get("TEXTCRAFT_DEADLINE", "0"))
"""Epoch seconds when the allocation's jobs must be done (0: none). A job's wall cap shrinks
to fit before it; a job that then times out is retried in the next allocation."""
MIN_JOB_SECONDS = 900
PROCESS_GRACE = 300
MAX_AGENT_TURNS = 2000
CONSECUTIVE_FAILURE_LIMIT = 3


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def source_hashes() -> dict[str, str]:
    """Hash of every source file a run reads, so the plan names the code it ran on."""
    root = REPO / "src/glossogen"
    return {
        str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix in (".py", ".jinja", ".json")
        and "__pycache__" not in path.parts
    }


def config_for(arm: str, manifest: Path) -> dict[str, object]:
    """knobs_default with the scaling task, budgets and the arm's team shape."""
    base = json.loads(
        (REPO / f"src/glossogen/scenarios/{SCENARIO}/knobs_default.json").read_text()
    )
    agents, comms = ARMS[arm]
    config = dict(base)
    config.update(
        round_count=1,
        max_round_duration_seconds=WALL_SECONDS,
        agent_max_tokens=AGENT_MAX_TOKENS,
        compaction={"enabled": True, "token_threshold": COMPACTION_THRESHOLD},
        crafter_count=12,
        steps_per_agent=6,
        quantity_scale=2,
        resource_slack_fraction=0.0,
        dag_max_fan_in=2,
        dag_cross_edge_density=0.3,
        dag_raw_material_count=1,
        dag_max_raw_inputs=1,
        raw_ownership="private",
        task_manifest=str(manifest),
        pool_agent_count=agents,
        recipe_holders=None,
        actions_per_witness_step=ACTIONS_PER_STEP,
        team_token_limit=None,
        uncraft_enabled=True,
        comms_enabled=comms,
        round_time_budget_seconds=-1,
        virtual_clock=True,
        virtual_base_latency_s=1.0,
        virtual_output_tokens_per_second=50.0,
        craft_duration_s=CRAFT_SECONDS,
        recipe_reveal="frontier",
        depot_view="nonzero",
        **ORACLE.get(arm, {}),
    )
    return config


def prepare() -> dict[str, object]:
    """Write every job's manifest and config once; later calls reuse the plan."""
    plan_path = OUT / "plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        if plan["source_sha256"] != source_hashes():
            raise SystemExit(
                "src/glossogen changed since plan.json was written. "
                "Finish this batch on the code it started with, or start a new batch directory."
            )
        return plan
    sys.path.insert(0, str(REPO / "src"))
    from glossogen.scenarios.textcraft_shared_workspace.knobs import SharedWorkspaceKnobs
    from glossogen.scenarios.textcraft_shared_workspace.tasks import WorkspaceTask

    rows = json.loads(BANK.read_text())
    assert len(rows) == BANK_TASKS
    jobs = []
    for index, row in enumerate(rows):
        task = WorkspaceTask.model_validate(row)
        for arm in ARMS:
            label = f"{arm}_t{index:02d}"
            directory = OUT / "jobs" / label
            directory.mkdir(parents=True, exist_ok=True)
            manifest = directory / "task_manifest.json"
            dump(manifest, [row])
            config = config_for(arm=arm, manifest=manifest)
            knobs = SharedWorkspaceKnobs.model_validate(config)
            dump(directory / "config.json", config)
            jobs.append(
                dict(
                    label=label,
                    arm=arm,
                    task_index=index,
                    task_id=task.task_id,
                    agents=knobs.agent_count,
                    comms=knobs.comms_enabled,
                    work=len(task.witness),
                    directory=str(directory.relative_to(REPO)),
                )
            )
    plan = dict(
        model=MODEL,
        arms=list(ARMS),
        craft_seconds=CRAFT_SECONDS,
        actions_per_step=ACTIONS_PER_STEP,
        agent_max_tokens=AGENT_MAX_TOKENS,
        compaction_threshold=COMPACTION_THRESHOLD,
        wall_seconds=WALL_SECONDS,
        max_agent_turns=MAX_AGENT_TURNS,
        jobs=jobs,
        source_sha256=source_hashes(),
        bank=str(BANK.relative_to(REPO)),
    )
    dump(plan_path, plan)
    return plan


def base_url(node: str) -> str:
    """``host`` serves on PORT; ``host:port`` names its own port."""
    if ":" in node:
        return f"http://{node}/v1"
    return f"http://{node}:{PORT}/v1"


def wait_for_servers(nodes: list[str]) -> None:
    for node in nodes:
        deadline = time.monotonic() + 1800
        while True:
            try:
                request = urllib.request.Request(
                    f"{base_url(node)}/models",
                    headers={"Authorization": f"Bearer {API_KEY}"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    assert MODEL in [m["id"] for m in json.load(response)["data"]]
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"server not ready: {node}")
                time.sleep(10)
        print(f"READY {node}", flush=True)


class FailureStreak:
    """Failed jobs in a row across nodes; several mean the server is gone."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._consecutive = 0
        self.total = 0
        self.stop = threading.Event()

    def record(self, failed: bool) -> None:
        with self._lock:
            if not failed:
                self._consecutive = 0
                return
            self._consecutive += 1
            self.total += 1
            if self._consecutive >= self._limit:
                self.stop.set()


def run_process(
    command: list[str], directory: Path, env: dict[str, str], timeout: float
) -> tuple[int, bool]:
    """Run one job's process with the outer timeout; returns (returncode, timed_out)."""
    dump(directory / "command.json", command)
    with (directory / "console.log").open("w") as output:
        process = subprocess.Popen(
            command, cwd=REPO, env=env, stdout=output, stderr=subprocess.STDOUT
        )
        try:
            return process.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                return process.wait(timeout=15), True
            except subprocess.TimeoutExpired:
                process.kill()
                return process.wait(), True


def read_events(directory: Path) -> tuple[list[dict[str, object]], list[Path]]:
    paths = list((directory / "runs" / SCENARIO).glob(f"*/{SCENARIO}.jsonl"))
    events = []
    for path in paths:
        for line in path.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events, paths


def outcome_of(job: dict[str, object], directory: Path) -> dict[str, object]:
    """Read the event log into the fields every arm reports."""
    events, paths = read_events(directory=directory)
    kinds = [e["event_type"] for e in events]
    resolved = [e for e in events if e["event_type"] == "workspace_round_resolved"]
    failures = [e for e in events if e["event_type"] == "agent_run_cycle_failed"]
    ended = "simulation_ended" in kinds
    valid = ended and len(resolved) == 1
    responses = [e for e in events if e["event_type"] == "llm_response_received"]
    acts = [e for e in events if e["event_type"] == "workspace_action_executed"]
    calls = [e for e in events if e["event_type"] == "tool_call_invoked"]
    waits = [e for e in events if e["event_type"] == "wait_registered"]
    outcome: dict[str, object] = dict(valid=valid, cycle_failures=len(failures))
    if resolved:
        r = resolved[0]
        outcome.update(
            success=r["success"],
            stop_reason=r["trigger"],
            targets_satisfied=r["targets_satisfied"],
            virtual_elapsed_seconds=r.get("virtual_elapsed_seconds"),
            actions_by_agent=r["actions_used"],
        )
    usage = [e.get("usage") or {} for e in responses]
    outcome.update(
        actions_used=len(acts),
        accepted_crafts=sum(
            1 for a in acts if a["accepted"] and not str(a["command"]).startswith("uncraft ")
        ),
        failed_acts=sum(1 for a in acts if not a["accepted"]),
        uncrafts=sum(1 for a in acts if a["accepted"] and str(a["command"]).startswith("uncraft ")),
        messages_sent=sum(1 for c in calls if c.get("tool_name") == "send_message"),
        observes=sum(1 for c in calls if c.get("tool_name") == "observe"),
        waits_by_kind={
            kind: sum(1 for w in waits if w.get("wait_for") == kind)
            for kind in sorted({str(w.get("wait_for")) for w in waits})
        },
        requests=len(responses),
        runaway_requests=sum(
            1
            for e in events
            if e["event_type"] == "workspace_request_released"
            and int(e["output_tokens"]) > RUNAWAY_TOKENS
        ),
        input_tokens=sum(int(u.get("input_tokens") or 0) for u in usage),
        output_tokens=sum(int(u.get("output_tokens") or 0) for u in usage),
        event_log=str(paths[0].relative_to(REPO)) if len(paths) == 1 else None,
    )
    return outcome


def run_job(job: dict[str, object], node: str, streak: FailureStreak) -> dict[str, object]:
    directory = REPO / str(job["directory"])
    result_path = directory / "result.json"
    if result_path.exists():
        previous = json.loads(result_path.read_text())
        if previous["status"] in ("completed", "wall_capped"):
            return previous
    if streak.stop.is_set():
        return {**job, "status": "not_started"}
    wall = WALL_SECONDS
    if DEADLINE:
        wall = min(WALL_SECONDS, int(DEADLINE - time.time() - PROCESS_GRACE))
        if wall < MIN_JOB_SECONDS:
            return {**job, "status": "not_started"}
    shutil.rmtree(directory / "runs", ignore_errors=True)
    env = dict(os.environ)
    env["SELF_HOSTED_BASE_URLS"] = json.dumps({MODEL: base_url(node)})
    env["SELF_HOSTED_API_KEY"] = API_KEY
    env["LANGFUSE_PUBLIC_KEY"] = ""
    env["LANGFUSE_SECRET_KEY"] = ""
    command = [
        str(REPO / ".venv/bin/python"), "-m", "glossogen", "run", SCENARIO,
        "--model", MODEL, "--provider", "self-hosted",
        "--runs-dir", str(directory / "runs"),
        "--config", str(directory / "config.json"),
        "--max-agent-turns", str(MAX_AGENT_TURNS),
        f"max_round_duration_seconds={wall}",
    ]  # fmt: skip
    print(f"START {node} {job['label']} agents={job['agents']}", flush=True)
    started = time.monotonic()
    returncode, timed_out = run_process(
        command=command, directory=directory, env=env, timeout=wall + PROCESS_GRACE
    )
    outcome = outcome_of(job=job, directory=directory)
    valid = bool(outcome.pop("valid")) and returncode == 0 and not timed_out
    status = "infrastructure_failure"
    if valid:
        status = "completed"
    # The round has no virtual cap, so a round_timeout is the wall-clock safety net, not a result:
    # cut short by the allocation it is retried; at the full WALL_SECONDS it is final but kept apart.
    if valid and outcome.get("stop_reason") == "round_timeout":
        status = "wall_capped"
        if wall < WALL_SECONDS:
            status = "allocation_truncated"
    result = {
        **job,
        **outcome,
        "node": node,
        "wall_cap_seconds": wall,
        "status": status,
        "seconds": round(time.monotonic() - started, 3),
        "returncode": returncode,
        "outer_timeout": timed_out,
    }
    dump(result_path, result)
    streak.record(failed=not valid)
    print(
        f"END {node} {job['label']} {result['status']} {result['seconds']}s "
        f"success={result.get('success')} stop={result.get('stop_reason')} "
        f"virtual={result.get('virtual_elapsed_seconds')}",
        flush=True,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--nodes", nargs="+", required=True, help="host (port 8010) or host:port")
    parser.add_argument("--arms", nargs="+", choices=list(ARMS), default=list(ARMS))
    parser.add_argument("--tasks", type=int, default=BANK_TASKS, help="first N tasks only")
    parser.add_argument("--jobs-per-node", type=int, default=3)
    parser.add_argument("--smoke", nargs="+")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    plan = prepare()
    jobs = [
        job
        for job in plan["jobs"]
        if job["arm"] in args.arms and int(job["task_index"]) < args.tasks
    ]
    if args.prepare_only:
        print(f"PLAN {len(plan['jobs'])} jobs; selected {len(jobs)}", flush=True)
        return
    streak = FailureStreak(limit=CONSECUTIVE_FAILURE_LIMIT)
    if args.smoke:
        jobs = [job for job in plan["jobs"] if job["label"] in args.smoke]
        args.nodes = args.nodes[:1]
    wait_for_servers(args.nodes)
    pending: queue.Queue[dict[str, object]] = queue.Queue()
    # Largest teams first, so the long jobs do not trail at the end.
    for job in sorted(jobs, key=lambda j: (-int(j["agents"]), j["label"])):
        pending.put(job)

    def worker(node: str) -> list[dict[str, object]]:
        done = []
        while True:
            try:
                job = pending.get_nowait()
            except queue.Empty:
                return done
            done.append(run_job(job, node, streak))

    slots = [node for node in args.nodes for _ in range(args.jobs_per_node)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(slots)) as pool:
        results = [row for batch in pool.map(worker, slots) for row in batch]
    completed = sum(1 for r in results if r.get("status") == "completed")
    print(f"DONE {completed}/{len(results)} completed", flush=True)


if __name__ == "__main__":
    main()
