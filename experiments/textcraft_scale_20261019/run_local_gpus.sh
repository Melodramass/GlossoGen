#!/bin/bash
# One vLLM replica of Qwen3.5-27B per visible GPU on ports 8010, 8011, ..., then the batch
# spread over all of them. Plain bash on any single machine; nothing here needs Slurm.
#
#   bash run_local_gpus.sh                       all 80 jobs
#   SMOKE=1 bash run_local_gpus.sh               t00 of each arm, then stop
#   GPUS=0,1 JOBS_PER_GPU=4 bash run_local_gpus.sh
#
# Needs: the repo's .venv (uv sync), a python with vllm on PATH (or CONDA_SH/CONDA_ENV for
# start_server.sh), and the weights under HF_HOME. Finished jobs are skipped on rerun.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PY=../../.venv/bin/python
GPUS=${GPUS:-$(nvidia-smi --query-gpu=index --format=csv,noheader | paste -sd, -)}
JOBS_PER_GPU=${JOBS_PER_GPU:-4}
LOGS=logs/$(date +%m%d-%H%M)
mkdir -p "$LOGS"
NODES=()
SERVERS=()
i=0
for gpu in ${GPUS//,/ }; do
  port=$((8010 + i))
  CUDA_VISIBLE_DEVICES=$gpu PORT=$port setsid bash start_server.sh > "$LOGS/vllm-gpu$gpu.log" 2>&1 &
  SERVERS+=($!)
  NODES+=("127.0.0.1:$port")
  i=$((i + 1))
done
trap 'kill -- ${SERVERS[@]/#/-} 2> /dev/null' EXIT
echo "[$(date)] servers on ${NODES[*]}; logs in $LOGS"
if [ -n "${SMOKE:-}" ]; then
  $PY run_batch.py --nodes "${NODES[@]}" --jobs-per-node "$JOBS_PER_GPU" \
    --smoke solo_t00 n3_nocomm_t00 n3_comm_t00 n10_nocomm_t00 n10_comm_t00 2>&1 | tee "$LOGS/batch.log"
else
  $PY run_batch.py --nodes "${NODES[@]}" --jobs-per-node "$JOBS_PER_GPU" 2>&1 | tee "$LOGS/batch.log"
fi
$PY summarize.py | tee "$LOGS/summary.txt"
