export OPENAI_API_KEY="sk-QBi0uv2TOLzq4ahy7Eot7mpEjanQAxtgu1WPWgRyQrxXw1EA"
export OPENAI_API_BASE="https://www.DMXapi.com/v1"
export NGROK_AUTHTOKEN="35W7w4OCDcTzGy4uFOKWQeajml7_qgCa4TZpWFKQGAYBGJUS"
 # --model gpt-5.2-2025-12-11 \
python run_synthesis.py \
    --persona_path ./data/user_01/processed/person.pkl \
    --model gpt-4.1 \
    --max_events 15 \
    --max_depth 2 \
    --output_path ./data/user_01/processed/trajectory_state_depth_2.pkl \
    --traj_server_port 5002 \
    --disable_ngrok
    #--studio_url http://localhost:3000 