#!/bin/bash
#SBATCH -J tc-scale-27b
#SBATCH -p gh
#SBATCH -N 4
#SBATCH --ntasks-per-node=1
#SBATCH -t 8:00:00
#SBATCH -A CCR25051
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=lw33287@my.utexas.edu
#SBATCH --output=slurm/tc-scale-%j.out
#SBATCH --error=slurm/tc-scale-%j.out

# Submit from a login node (compute nodes cannot sbatch):
#   cd /work/11672/lwang33287/vista/agent/GlossoGen-scale/experiments/textcraft_scale_20261019
#   mkdir -p slurm && sbatch textcraft_scale_gh.sbatch
# Every node serves Qwen3.5-27B on :8010; the driver on the first node spreads the
# 80 jobs over all of them. Finished jobs are skipped, so resubmitting resumes.
# Fewer nodes or another partition: change -N / -p / -t; ARMS limits the arms.
set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
LOGS=slurm/$SLURM_JOB_ID
mkdir -p "$LOGS"
PY=/work/11672/lwang33287/vista/agent/GlossoGen-scale/.venv/bin/python
NODES=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | tr '\n' ' ')
echo "[$(date)] nodes: $NODES"
# Absolute bash path: a bare `env` on PATH resolves to CooperBench/.tools/env on Vista.
srun --ntasks-per-node=1 --output="$LOGS/vllm-%N.log" /bin/bash start_server.sh &
SERVERS=$!
# run_batch waits up to 30 minutes for every server.
$PY run_batch.py --nodes $NODES --jobs-per-node "${JOBS_PER_NODE:-4}" ${ARMS:+--arms $ARMS} \
  > "$LOGS/batch.log" 2>&1
echo "[$(date)] batch exited $?"
$PY summarize.py > "$LOGS/summary.txt" 2>&1
kill "$SERVERS" 2> /dev/null
