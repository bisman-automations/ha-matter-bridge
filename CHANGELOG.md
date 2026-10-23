# Changelog

All notable changes to the **ha-matter-bridge** Home Assistant integration will be documented in this file.

## [1.0.0] - 2026-10-23

### Connection
* **Matter Hub app:** found automatically on Home Assistant OS and Supervised (stable, alpha and testing channels) and reached through Home Assistant ingress, so no port needs to be opened.
* **Docker / standalone:** connect to Matter Hub at a URL, with optional username and password.
* **Reauthentication and reconfigure:** prompts for credentials when Matter Hub starts asking for them; the URL and credentials can be changed later.

### Devices
* **Matter Hub:** status, running bridges, Home Assistant connection, uptime and a Restart all bridges button.
* **Bridges:** one device per Matter Hub bridge with status, a Running switch, device and controller counts, Commissioned, failed entities and the pairing code.
* **Actions:** Restart, Refresh devices, Force sync and Open pairing window buttons on every bridge.
* **Automatic updates:** new bridges appear and deleted bridges are removed without reloading.

### Project
* Diagnostics with pairing codes, fabric IDs, the Matter Hub URL and credentials redacted.
* Tests, Hassfest and HACS validation, and draft releases from CHANGELOG.md.
