#!/usr/bin/env bash
# Convenience runner. Usage: ./run.sh [pipeline|api|dashboard|consume]
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python

case "${1:-pipeline}" in
  pipeline)  $PY src/pipeline.py "${@:2}" ;;
  api)       $PY src/step3_api.py ;;
  dashboard) .venv/bin/streamlit run src/dashboard.py ;;
  consume)   $PY src/consume_own_api.py ;;
  *) echo "usage: ./run.sh [pipeline|api|dashboard|consume]"
     echo "       ./run.sh pipeline --extract   re-pull from data.gov.sg"
     exit 1 ;;
esac
