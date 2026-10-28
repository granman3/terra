#!/bin/bash
# The whole v2 pipeline: dataset (Mac) -> tiny model (RTX 4080 on enterprise) -> replay week -> deck numbers.
# Run from the project root: train/run_v2.sh
set -euo pipefail
cd "$(dirname "$0")/.."
SERVER=${SERVER:-root@gpu-box}
REMOTE=/root/watts-per-token
UV="uv run -q --with pandas --with numpy --with pyarrow --with openpyxl --with xlrd --with holidays python"

n=$(ls data/raw/weather2/*.json | wc -l | tr -d ' ')
[ "$n" -eq 51 ] || { echo "only $n of 51 weather files; run train/fetch_weather.py first" >&2; exit 1; }

(cd train && $UV build_dataset.py) 2>&1 | grep -vE "Warning|dayof|r\[\"d" | tail -25
scp -q data/train/dataset_v2.npz "$SERVER:$REMOTE/data/train/"
scp -q train/train.py train/fetch_weather.py train/build_dataset.py train/decide.py train/train_big.py "$SERVER:$REMOTE/train_v2/"
ssh "$SERVER" "cd $REMOTE && OUT=out/v2 PYTHONPATH=train_v2 .venv/bin/python train_v2/train.py data/train/dataset_v2.npz 2>&1 | grep -v -i warn | grep -E 'epoch|params|train_seconds|train_energy|\"model\"' | head -20"
mkdir -p out/v2
for f in mycelium.onnx mycelium.pt metrics.json reliability.json decision_eval.json; do scp -q "$SERVER:$REMOTE/out/v2/$f" out/v2/; done
(cd train && $UV make_replay.py) 2>&1 | tail -1
uv run -q --with pandas --with pyarrow python deck/make_numbers.py > /dev/null
echo "v2 done: out/v2/metrics.json, data/train/replay_v2.json, deck/numbers.json"
