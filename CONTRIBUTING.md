# Contributing

1. Create a virtual environment and install the test requirements: `pip install -r requirements.txt`.
2. Add or update tests in `tests/` for every behavior change and run `pytest`.
3. Add an entry to `CHANGELOG.md` and bump `version` in `custom_components/matter_bridge/manifest.json` for releases.

Matter Hub's REST API lives in [RiDDiX/home-assistant-matter-hub](https://github.com/RiDDiX/home-assistant-matter-hub) under `packages/backend/src/api`. Never commit pairing codes, fabric data or credentials, including in test fixtures.
