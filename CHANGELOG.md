# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-10-26

### Changed

- Requires Home Assistant 2025.3 or newer. 1.0.0 didn't load on 2025.2.
- The README follows the same layout as the other bisman-automations integrations: a button that opens it in HACS, a button that starts setup, and troubleshooting steps for debug logs and diagnostics.
- The changelog no longer keeps an Unreleased section, and the agent notes follow the updated shared release rules.

### Fixed

- LICENSE has the full Apache License 2.0 text, so GitHub and HACS recognize the license.
- Diagnostics also redact the Matter Hub URL. This was added to main after v1.0.0 was tagged, so the published 1.0.0 doesn't include it.

## [1.0.0] - 2026-10-23

### Added

- **Connection**
  - **Matter Hub app:** found automatically on Home Assistant OS and Supervised (stable, alpha and testing channels) and reached through Home Assistant ingress, so no port needs to be opened.
  - **Docker / standalone:** connect to Matter Hub at a URL, with optional username and password.
  - **Reauthentication and reconfigure:** prompts for credentials when Matter Hub starts asking for them; the URL and credentials can be changed later.
- **Devices**
  - **Matter Hub:** status, running bridges, Home Assistant connection, uptime and a Restart all bridges button.
  - **Bridges:** one device per Matter Hub bridge with status, a Running switch, device and controller counts, Commissioned, failed entities and the pairing code.
  - **Actions:** Restart, Refresh devices, Force sync and Open pairing window buttons on every bridge.
  - **Automatic updates:** new bridges appear and deleted bridges are removed without reloading.
- **Project**
  - Diagnostics with pairing codes, fabric IDs and credentials redacted.
  - Tests, Hassfest and HACS validation, and draft releases from CHANGELOG.md.

[1.0.1]: https://github.com/bisman-automations/ha-matter-bridge/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/bisman-automations/ha-matter-bridge/releases/tag/v1.0.0
