# MobileMem trajectory demo

This is a sample-only local viewer for two MobileMem trajectories:

- `u0`, session `0_0`, question `0_q_0`
- `u10`, session `10_0`, question `10_q_826`

It contains only the 24 images referenced by those two sessions. The full
dataset and the source ZIP archives are intentionally excluded.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run_local.sh
```

Open <http://127.0.0.1:8766>.

Set `MEMWEB_PORT` to use another port:

```bash
MEMWEB_PORT=9000 ./run_local.sh
```
