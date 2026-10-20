#!/bin/bash
# Qwen3.5-27B on one GH200 in instruct (non-thinking) mode, model-card sampling for
# instruct general tasks: temperature 0.7, top_p 0.8, top_k 20, min_p 0,
# presence_penalty 1.5 (vLLM 0.27 ignores this key in --override-generation-config; requests run at 0), repetition_penalty 1.0.
set -eo pipefail
export HF_HOME=${HF_HOME:-/scratch/11672/lwang33287/.cache/huggingface}
export HF_HUB_OFFLINE=1
export VLLM_API_KEY=glossogen-local
export VLLM_USE_FLASHINFER_SAMPLER=0
# CONDA_SH= (empty) uses whatever vllm is already on PATH.
CONDA_SH=${CONDA_SH-/work/11672/lwang33287/vista/miniforge3/etc/profile.d/conda.sh}
if [ -n "$CONDA_SH" ]; then source "$CONDA_SH"; conda activate "${CONDA_ENV:-aiem}"; fi
exec vllm serve Qwen/Qwen3.5-27B \
  --served-model-name Qwen/Qwen3.5-27B \
  --port "${PORT:-8010}" \
  --max-model-len 131072 \
  --gpu-memory-utilization 0.95 \
  --language-model-only \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --max-num-seqs 32 \
  --enable-prefix-caching \
  --seed 0 \
  --default-chat-template-kwargs '{"enable_thinking":false}' \
  --override-generation-config '{"temperature":0.7,"top_p":0.8,"top_k":20,"min_p":0,"presence_penalty":1.5,"repetition_penalty":1.0}'
