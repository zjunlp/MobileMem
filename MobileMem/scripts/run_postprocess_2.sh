export OPENAI_API_KEY="sk-oapupQJhOlaBkqPMhgHrGfJqgnSpHjxeAz0PEQKT3l2LmdQb"
export OPENAI_API_BASE="https://www.DMXapi.com/v1"

python postprocess_qa.py \
    --input_path ./data/user_02/processed/qa_synthesis_results.json \
    --model gpt-5.2 \
    --output_path ./data/user_02/processed/qa_synthesis_results_post.json \
    --max_iters 10 \
    --random_seed 42 \
    --milvus_uri ./data/user_02/processed/qa_postprocess_milvus.db 