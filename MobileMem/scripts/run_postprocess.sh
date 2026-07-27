export OPENAI_API_KEY="sk-COB3cTwcj65YUYBuPkoZMDdcmfy9J5trvrzPJtfFjjvNJYKx"
export OPENAI_API_BASE="https://www.DMXapi.com/v1"

python postprocess_qa.py \
    --input_path ./data/user_01/processed/qa_synthesis_results.json \
    --model gpt-5.1 \
    --output_path ./data/user_01/processed/qa_synthesis_results_post.json \
    --max_iters 10 \
    --random_seed 42 \
    --milvus_uri ./data/user_01/processed/qa_postprocess_milvus.db 