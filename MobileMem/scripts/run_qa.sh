export OPENAI_API_KEY="sk-COB3cTwcj65YUYBuPkoZMDdcmfy9J5trvrzPJtfFjjvNJYKx"
export OPENAI_API_BASE="https://www.DMXapi.com/v1"

python run_qa_synthesis.py \
    --trajectory_path ./data/user_01/processed/trajectory_state.pkl \
    --model gpt-5.2 \
    --output_path ./data/user_01/processed/qa_synthesis_results.json \
    --min_qa_pairs 2 \
    --max_qa_pairs 10 \
    --max_attempts 5 \
    --propagation_count 10 \
    --max_iters 50 \
    --random_seed 42 
    # --studio_project haste_qa_synthesis \
    # --studio_url http://localhost:3000 