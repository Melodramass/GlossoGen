#!/bin/bash
#SBATCH -J oracle-scale
#SBATCH -p gh-dev
#SBATCH -N 4
#SBATCH --ntasks-per-node=1
#SBATCH -t 2:00:00
#SBATCH -A CCR25051
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=lw33287@my.utexas.edu
#SBATCH --output=slurm/oracle-ghdev-%j.out
#SBATCH --error=slurm/oracle-ghdev-%j.out

# One 2 h gh-dev link of the oracle-communication grid; chain links with submit_chain.sh.
# Every node serves Qwen3.8-27B on :8010. The last SYNCODE_NODES nodes run syn-code,
# the rest run TextCraft. Both drivers skip finished jobs, so each link continues the last.
# ARMS / SYNCODE_ARMS pick the arms (default: the n10 arms plus the solo reference).
#   TextCraft: 16 tasks -> full/, JOBS_PER_NODE at a time. A job's wall cap shrinks to end
#              before the allocation does; a job cut short that way is retried by the next
#              link, one that reaches the full 5400 s is recorded as wall_capped.
#   syn-code:  4 w8_d2 instances on simulated time (replies 1 s + tokens/50, commands their run
#              time + 10 s per probe on one team channel), SYNCODE_SECONDS simulated seconds each
#              -> syn-code-env/runs/oracle_scaling_vt_qwen38. Wall time is only a safety net that
#              shrinks to fit the allocation; an episode it cuts short is rerun by the next link.
set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
LOGS=slurm/$SLURM_JOB_ID
mkdir -p "$LOGS"
PY=/work/11672/lwang33287/vista/agent/GlossoGen-scale/.venv/bin/python
SYN=/work/11672/lwang33287/vista/agent/syn-code-env
MODEL=Qwen/Qwen3.8-27B
SNAPSHOT=/scratch/11672/lwang33287/.cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0
SYNCODE_NODES=${SYNCODE_NODES:-2}
SYNCODE_SECONDS=${SYNCODE_SECONDS:-2400}
SYNCODE_PARALLEL=${SYNCODE_PARALLEL:-1}
SYNCODE_ARMS=${SYNCODE_ARMS:-n10_artifact,n10_chat,n10_feed,n10_oracle,solo}
ARMS=${ARMS-n10_comm n10_oracle n10_nocomm n10_feed solo}
END=$(date -d "$(squeue -h -j "$SLURM_JOB_ID" -o %e)" +%s 2> /dev/null || echo $(($(date +%s) + 7200)))
DEADLINE=$((END - 240))  # leave time to write results before Slurm kills the job
mapfile -t NODES < <(scontrol show hostnames "$SLURM_JOB_NODELIST")
TC_NODES=("${NODES[@]:0:${#NODES[@]}-SYNCODE_NODES}")
SC_NODES=("${NODES[@]: -SYNCODE_NODES}")
echo "[$(date)] end $(date -d @"$END") textcraft: ${TC_NODES[*]}  syn-code: ${SC_NODES[*]}"

# Absolute bash path: a bare `env` on PATH resolves to CooperBench/.tools/env on Vista.
srun --ntasks-per-node=1 --output="$LOGS/vllm-%N.log" /bin/bash -c \
  "SYNCODE_MODEL_PATH=$SNAPSHOT SYNCODE_SERVED_MODEL=$MODEL exec /bin/bash $SYN/runs/start_server_27b_prefix.sh" &
SERVERS=$!

if [ "$SYNCODE_NODES" -gt 0 ]; then
  (
    for node in "${SC_NODES[@]}"; do
      for _ in $(seq 1 120); do
        curl -sf -H 'Authorization: Bearer glossogen-local' "http://$node:8010/v1/models" | grep -q "$MODEL" && break
        sleep 10
      done
    done
    i=0
    for node in "${SC_NODES[@]}"; do
      python3 "$SYN/experiments/program_rebuild.py" \
        --bank "$SYN/banks/compositional_w8_d2_probe10s" \
        --out "$SYN/runs/oracle_scaling_vt_qwen38/shard$i" --model "$MODEL" --api-base "http://$node:8010/v1" \
        --arms "$SYNCODE_ARMS" \
        --shards "$SYNCODE_NODES" --shard-index "$i" --parallel "$SYNCODE_PARALLEL" \
        --virtual-seconds "$SYNCODE_SECONDS" --seconds 5400 --deadline "$DEADLINE" --launch-window 7200 \
        --tokens 30000000 --actions 800 --execute \
        >> "$LOGS/syncode-shard$i.log" 2>&1 &
      i=$((i + 1))
    done
    wait
  ) &
  SYNCODE=$!
fi

# run_batch waits up to 30 minutes for every server.
TEXTCRAFT_OUT=$PWD/full TEXTCRAFT_WALL_SECONDS=5400 TEXTCRAFT_DEADLINE=$DEADLINE \
  $PY run_batch.py --nodes "${TC_NODES[@]}" --jobs-per-node "${JOBS_PER_NODE:-2}" ${ARMS:+--arms $ARMS} \
  > "$LOGS/textcraft.log" 2>&1
echo "[$(date)] textcraft link exited $?"
[ -n "${SYNCODE:-}" ] && wait "$SYNCODE"
echo "[$(date)] syn-code link exited"
TEXTCRAFT_OUT=$PWD/full $PY progress.py > "$LOGS/textcraft_progress.txt" 2>&1
TEXTCRAFT_OUT=$PWD/full $PY summarize.py > "$LOGS/textcraft_summary.txt" 2>&1
python3 "$SYN/experiments/program_rebuild.py" --out "$SYN/runs/oracle_scaling_vt_qwen38" --summarize \
  > "$LOGS/syncode_summary.json" 2>&1
kill "$SERVERS" 2> /dev/null
