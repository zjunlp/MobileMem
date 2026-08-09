# Contributing

This repository is maintained as the public project page for MobileMem. Changes should be focused,
reviewable, and preserve the intended desktop and mobile presentation.

## Before submitting a change

1. Run `npm test` in the environment described in [TESTING.md](TESTING.md).
2. Keep content and component logic in the existing `assets/web/` modules rather than adding inline
   scripts or style overrides.
3. Rebuild the image manifest with `npm run images:build` whenever a displayed dataset image changes.
4. Keep the media inventory in [ASSETS.md](ASSETS.md) current when asset groups change.
5. Do not commit credentials, local absolute paths, private conversations, or unapproved personal
   data.

Visual changes should include desktop and mobile screenshots. Refactors that are intended to be
visual no-ops must keep the browser geometry and interaction regression checks green.
