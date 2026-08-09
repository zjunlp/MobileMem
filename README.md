# MobileMem Project Page

This repository contains the static project page for **MobileMem: On-Device Memory for
Continually Evolving Agents**. The page presents the research overview, an interactive memory
case, a curated application-sample browser, and reproducible quick-start guidance.

## Local preview

The site has no build step. Serve the repository root with any static HTTP server:

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000/>.

## Repository layout

- `index.html` — page structure and accessible content.
- `assets/web/css/` — page and component styles.
- `assets/web/js/` — isolated page, case-demo, quick-start, and application-browser logic.
- `assets/web/memweb/` — curated MobileMem preview images and dialogue trajectories.
- `scripts/` — deterministic image-manifest tooling.
- `tests/` — desktop and mobile browser regression checks.

## Development and testing

Install the JavaScript formatter and the isolated browser-test environment once:

```bash
npm ci
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-test.txt
playwright install chromium
```

Run the complete quality gate with:

```bash
npm test
```

See [TESTING.md](TESTING.md) for details about updating the deterministic image manifest and
collecting regression diagnostics.

## Content and privacy

The application browser includes a curated set of research samples in the page bundle. The media
inventory and deterministic image manifest are documented in [ASSETS.md](ASSETS.md).
The page-view counter and its network behavior are documented in [PRIVACY.md](PRIVACY.md).
