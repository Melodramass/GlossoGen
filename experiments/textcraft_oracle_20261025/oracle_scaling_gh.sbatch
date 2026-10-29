#!/bin/bash
#SBATCH -J oracle-scale
#SBATCH -p gh
#SBATCH -N 9
#SBATCH --ntasks-per-node=1
#SBATCH -t 14:00:00
#SBATCH -A CCR25051
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=lw33287@my.utexas.edu
#SBATCH --output=slurm/oracle-scale-%j.out
#SBATCH --error=slurm/oracle-scale-%j.out

# Oracle-communication scaling grid, Qwen3.8-27B non-thinking, both environments.
# Submit from a login node (compute nodes cannot sbatch):
#   cd /work/11672/lwang33287/vista/agent/GlossoGen-scale/experiments/textcraft_oracle_20261025
#   mkdir -p slurm && sbatch oracle_scaling_gh.sbatch
# Every node serves the model on :8010. The last SYNCODE_NODES nodes run syn-code
# (one shard each); the rest run TextCraft through one multi-node driver.
#   TextCraft: 16 tasks x 9 arms (solo, n3/n10 x nocomm/comm/feed/oracle) -> full/
#   syn-code:  4 w8_d2 instances x 9 arms -> syn-code-env/runs/oracle_scaling_uncapped_qwen38
#              probe cap 8192 and 800 shell actions only guard runaways; report probes vs solo
# Both drivers skip finished jobs, so resubmitting resumes.
set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
LOGS=slurm/$SLURM_JOB_ID
mkdir -p "$LOGS"
PY=/work/11672/lwang33287/vista/agent/GlossoGen-scale/.venv/bin/python
SYN=/work/11672/lwang33287/vista/agent/syn-code-env
MODEL=Qwen/Qwen3.8-27B
SNAPSHOT=/scratch/11672/lwang33287/.cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0
SYNCODE_NODES=${SYNCODE_NODES:-3}
mapfile -t NODES < <(scontrol show hostnames "$SLURM_JOB_NODELIST")
TC_NODES=("${NODES[@]:0:${#NODES[@]}-SYNCODE_NODES}")
SC_NODES=("${NODES[@]: -SYNCODE_NODES}")
echo "[$(date)] textcraft: ${TC_NODES[*]}  syn-code: ${SC_NODES[*]}"

# Absolute bash path: a bare `env` on PATH resolves to CooperBench/.tools/env on Vista.
srun --ntasks-per-node=1 --output="$LOGS/vllm-%N.log" /bin/bash -c \
  "SYNCODE_MODEL_PATH=$SNAPSHOT SYNCODE_SERVED_MODEL=$MODEL exec /bin/bash $SYN/runs/start_server_27b_prefix.sh" &
SERVERS=$!

# syn-code driver does not wait for its server; wait here (model load is ~5-10 min).
for node in "${SC_NODES[@]}"; do
  for _ in $(seq 1 180); do
    curl -sf -H 'Authorization: Bearer glossogen-local' "http://$node:8010/v1/models" | grep -q "$MODEL" && break
    sleep 10
  done
done

i=0
for node in "${SC_NODES[@]}"; do
  python3 "$SYN/experiments/program_rebuild.py" --bank "$SYN/banks/compositional_w8_d2_uncapped" \
    --out "$SYN/runs/oracle_scaling_uncapped_qwen38/shard$i" --model "$MODEL" --api-base "http://$node:8010/v1" \
    --arms solo,n3_artifact,n3_chat,n3_feed,n3_oracle,n10_artifact,n10_chat,n10_feed,n10_oracle \
    --shards "$SYNCODE_NODES" --shard-index "$i" --parallel "${SYNCODE_PARALLEL:-2}" \
    --seconds 3600 --tokens 30000000 --actions 800 --launch-window 39600 --execute \
    > "$LOGS/syncode-$node.log" 2>&1 &
  i=$((i + 1))
done

# run_batch waits up to 30 minutes for every server.
TEXTCRAFT_OUT=$PWD/full TEXTCRAFT_WALL_SECONDS=5400 \
  $PY run_batch.py --nodes "${TC_NODES[@]}" --jobs-per-node "${JOBS_PER_NODE:-4}" ${ARMS:+--arms $ARMS} \
  > "$LOGS/textcraft.log" 2>&1
echo "[$(date)] textcraft batch exited $?"
wait $(jobs -p | grep -v "^$SERVERS$")
echo "[$(date)] syn-code shards exited"
TEXTCRAFT_OUT=$PWD/full $PY summarize.py > "$LOGS/textcraft_summary.txt" 2>&1
python3 "$SYN/experiments/program_rebuild.py" --out "$SYN/runs/oracle_scaling_uncapped_qwen38" --summarize \
  > "$LOGS/syncode_summary.json" 2>&1
kill "$SERVERS" 2> /dev/null
