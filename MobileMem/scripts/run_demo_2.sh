export OPENAI_API_KEY="sk-oapupQJhOlaBkqPMhgHrGfJqgnSpHjxeAz0PEQKT3l2LmdQb"
export OPENAI_API_BASE="https://www.DMXapi.com/v1"
export NGROK_AUTHTOKEN="35W7w4OCDcTzGy4uFOKWQeajml7_qgCa4TZpWFKQGAYBGJUS"
 # --model gpt-5.2-2025-12-11 \
python run_synthesis.py \
    --persona_path ./data/user_02/processed/person.pkl \
    --model gpt-4.1 \
    --max_events 15 \
    --max_depth 2 \
    --output_path ./data/user_02/processed/trajectory_state.pkl \
    --traj_server_port 5001 \
    --disable_ngrok
    #--studio_url http://localhost:3000 