#!/bin/bash
# Queue LINKS gh-dev links of oracle_scaling_ghdev.sbatch, each starting after the previous
# one ends (afterany). Run on a login node; compute nodes cannot sbatch.
#   bash submit_chain.sh 3            # three new links
#   bash submit_chain.sh 2 1234567    # two more links after job 1234567
# gh-dev allows 3 submitted jobs per user (1 running), so queue at most 3 at a time and
# run this again as links finish. Extra variables pass through, e.g.
#   SYNCODE_SECONDS=3600 bash submit_chain.sh 3
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p slurm
LINKS=${1:-3}
PREV=${2:-}
for _ in $(seq 1 "$LINKS"); do
  DEP=()
  [ -n "$PREV" ] && DEP=(--dependency="afterany:$PREV")
  PREV=$(sbatch --parsable "${DEP[@]}" --export=ALL oracle_scaling_ghdev.sbatch)
  echo "submitted $PREV ${DEP[*]}"
done
