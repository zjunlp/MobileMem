export OPENAI_API_KEY="sk-COB3cTwcj65YUYBuPkoZMDdcmfy9J5trvrzPJtfFjjvNJYKx"
export OPENAI_API_BASE="https://www.DMXapi.com/v1"
export NGROK_AUTHTOKEN="35W7w4OCDcTzGy4uFOKWQeajml7_qgCa4TZpWFKQGAYBGJUS"
 # --model gpt-5.2-2025-12-11 \
python run_synthesis.py \
    --persona_path person_v4_no_grounded_session.pkl \
    --model gpt-4.1-mini \
    --max_events 15 \
    --max_depth 2 \
    --output_path gpt_4o_mini_trajectory_state.pkl \
    --traj_server_port 5000 \
    --disable_ngrok \
    --studio_url http://localhost:3000 