# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-10-30

### Changed

- **Matter Hub and its bridges show as services, not devices.** They are software, so they now appear under **Services** on the Matter Bridge page, like other software-only integrations, instead of in the device list. Entity names and IDs, and automations that use them, don't change.

### Fixed

- Set up the Matter Hub and bridge devices in a way that keeps working with Home Assistant 2026.11, where the device details format changes.

## [1.1.1] - 2026-10-30

### Changed

- **Install from the Marketplace.** The README now explains how to install from the Marketplace that replaces HACS in Home Assistant 2026.11, with its own button. The HACS steps stay for Home Assistant 2026.10 and older, and an install you already have moves over by itself.

## [1.1.0] - 2026-10-30

### Added

- **Repair when the Matter Hub app is unavailable:** if the app is stopped or uninstalled, a repair under **Settings → System → Repairs** says so and points to Reconfigure. It goes away once Matter Hub answers again.

### Changed

- **Requires Home Assistant 2026.8 or newer.** 1.0.0 didn't load on 2025.2, and the device registry calls this release uses need 2026.8.
- **Bridges stay put while Matter Hub restarts.** A bridge's device is removed only after Matter Hub has left it out of three updates in a row (about a minute and a half), and never while Matter Hub lists no bridges at all. Before, one update during a restart could delete every bridge device, with its entity history and the areas and names you'd set.
- Bridge devices are linked to the Matter Hub device the way Home Assistant 2026.8 expects, ahead of the old way being removed in 2027.8.
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

[1.2.0]: https://github.com/bisman-automations/ha-matter-bridge/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/bisman-automations/ha-matter-bridge/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/bisman-automations/ha-matter-bridge/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/bisman-automations/ha-matter-bridge/releases/tag/v1.0.0
