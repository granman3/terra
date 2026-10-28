#!/bin/bash
# Runs on enterprise after the v1 4B run (pid in $1) exits: tiny v2 alone (clean energy number),
# then the v2 4B run scored against it, retried at half batch if it fails (e.g. out of memory).
# Start: (nohup ./chain_v2.sh <pid> > out/chain_v2.log 2>&1 < /dev/null &)
cd /root/watts-per-token
while kill -0 "$1" 2>/dev/null; do sleep 30; done
echo "v1 done $(date)"
OUT=out/v2 PYTHONPATH=train_v2 .venv/bin/python train_v2/train.py data/train/dataset_v2.npz > out/v2_train.log 2>&1 \
  && echo "tiny v2 done $(date)" || echo "tiny v2 FAILED $(date)"
if OUT=out/big_v2 TINY=out/v2/mycelium.pt N_TRAIN=10000 PYTHONPATH=train_v2 .venv/bin/python train_v2/train_big.py data/train/dataset_v2.npz > out/big_v2.log 2>&1; then
  echo "big v2 done $(date)"
else
  echo "big v2 FAILED at batch 4, retrying at batch 2 $(date)"
  OUT=out/big_v2 TINY=out/v2/mycelium.pt N_TRAIN=10000 BATCH=2 ACCUM=8 PYTHONPATH=train_v2 .venv/bin/python train_v2/train_big.py data/train/dataset_v2.npz > out/big_v2_retry.log 2>&1 \
    && echo "big v2 done (batch 2) $(date)" || echo "big v2 FAILED again $(date)"
fi
