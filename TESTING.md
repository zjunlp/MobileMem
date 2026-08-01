# Testing

The regression suite protects the static page structure, the 360-image catalogue, and the desktop
and mobile interactions.

## One-time setup

```bash
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-test.txt
playwright install chromium
```

## Run the full suite

```bash
source .venv/bin/activate
npm test
```

When displayed images change, rebuild and review the deterministic manifest before testing:

```bash
npm run images:build
npm run images:check
```

Failed browser checks write diagnostic screenshots to `test-results/`.
