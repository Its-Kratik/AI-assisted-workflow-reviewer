#!/usr/bin/env bash
set -e

# Single CPU-only command for offline tests and evaluation
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

export PYTHONPATH="$DIR:$PYTHONPATH"
python3 evaluate.py "$@"
