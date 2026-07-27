export OPENAI_API_KEY="sk-oapupQJhOlaBkqPMhgHrGfJqgnSpHjxeAz0PEQKT3l2LmdQb"
export OPENAI_API_BASE="https://www.DMXapi.com/v1"

python run_qa_synthesis.py \
    --trajectory_path ./data/user_02/processed/trajectory_state.pkl \
    --model gpt-5.2 \
    --output_path ./data/user_02/processed/qa_synthesis_results.json \
    --min_qa_pairs 2 \
    --max_qa_pairs 10 \
    --max_attempts 5 \
    --propagation_count 10 \
    --max_iters 50 \
    --random_seed 42 