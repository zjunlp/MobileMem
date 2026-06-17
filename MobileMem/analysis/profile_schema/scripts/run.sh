export OPENAI_API_KEY="YOUR_API_KEY"
export OPENAI_API_BASE="YOUR_API_BASE"

SCRIPT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

python "${SCRIPT_DIR}/analysis/profile_schema/create_profiles.py"
python "${SCRIPT_DIR}/analysis/profile_schema/run_synthesis.py"
python "${SCRIPT_DIR}/analysis/profile_schema/run_analysis.py"