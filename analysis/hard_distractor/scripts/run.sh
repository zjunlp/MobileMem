SCRIPT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"
export OPENAI_API_KEY="YOUR_API_KEY"
export OPENAI_API_BASE="YOUR_API_BASE"

python "${SCRIPT_DIR}/analysis/hard_distractor/sample_data.py"
python "${SCRIPT_DIR}/analysis/hard_distractor/prepare_env.py"
python "${SCRIPT_DIR}/analysis/hard_distractor/run_synthesis.py"