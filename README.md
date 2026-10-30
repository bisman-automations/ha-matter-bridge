<p align="center">
  <img src="https://raw.githubusercontent.com/bisman-automations/ha-matter-bridge/main/custom_components/matter_bridge/brand/icon.png" alt="Matter Bridge icon" width="128">
</p>

# Matter Bridge

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.8%2B-blue.svg)](https://www.home-assistant.io/)
[![GitHub Release](https://img.shields.io/github/v/release/bisman-automations/ha-matter-bridge)](https://github.com/bisman-automations/ha-matter-bridge/releases)
[![Test](https://github.com/bisman-automations/ha-matter-bridge/actions/workflows/test.yml/badge.svg)](https://github.com/bisman-automations/ha-matter-bridge/actions/workflows/test.yml)
[![Validate](https://github.com/bisman-automations/ha-matter-bridge/actions/workflows/validate.yml/badge.svg)](https://github.com/bisman-automations/ha-matter-bridge/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/bisman-automations/ha-matter-bridge)](LICENSE)

Shows [Home Assistant Matter Hub](https://github.com/RiDDiX/home-assistant-matter-hub) as an integration under **Settings → Devices & services**, with a device for Matter Hub and one for each Matter bridge you created in it.

Matter Hub does the Matter work: it publishes your Home Assistant entities to Apple Home, Google Home, Alexa and other Matter controllers. This integration lets you watch and control those bridges from Home Assistant, so you can see bridge status on dashboards, get alerted when a bridge fails, and restart or re-sync a bridge from an automation.

## Requirements

* Home Assistant 2026.8 or newer
* Home Assistant Matter Hub, either:
  * the **Matter Hub app** (add-on) on Home Assistant OS or Supervised, or
  * Matter Hub in Docker or standalone, reachable over the network (port 8482 by default)

## Installation

### HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bisman-automations&repository=ha-matter-bridge&category=integration)

1. Click the button above, or in HACS open the menu, choose **Custom repositories**, and add `https://github.com/bisman-automations/ha-matter-bridge` as an **Integration**.
2. Download **Matter Bridge** and restart Home Assistant.

Requires **Home Assistant 2026.8 or newer**.

### Manual

Download `matter_bridge.zip` from the [latest release](https://github.com/bisman-automations/ha-matter-bridge/releases/latest), unzip it into `config/custom_components/matter_bridge/`, and restart Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up Matter Bridge.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=matter_bridge)

Or go to **Settings → Devices & services → Add integration → Matter Bridge**.

Setup finds the Matter Hub app on its own when it is installed; otherwise point it at a Matter Hub URL.

### Connecting to the Matter Hub app

When the Matter Hub app is installed, setup offers it first. Pick it and submit; nothing else is needed.

The app only accepts requests from Home Assistant's ingress proxy, so the integration talks to it the same way the Matter Hub panel in the sidebar does. No port has to be opened, and it keeps working when the app restarts on a new internal port. The stable, alpha and testing channels of the app are all detected.

### Connecting to Docker or standalone Matter Hub

Choose **Matter Hub at a URL** and enter the web interface address, for example `http://192.168.1.50:8482`.

If you turned on authentication in Matter Hub's settings (or set `HAMH_HTTP_AUTH_USERNAME` / `HAMH_HTTP_AUTH_PASSWORD`), enter the same username and password. If Matter Hub has an IP allow list, add your Home Assistant host to it.

## Devices and entities

### Matter Hub

| Entity | Description |
| --- | --- |
| Status | `healthy`, `degraded` (a bridge is stopped or failed) or `unhealthy` (Matter Hub lost its Home Assistant connection) |
| Running bridges | Running bridge count; attributes list total, stopped and failed |
| Home Assistant connection | Whether Matter Hub's own connection to Home Assistant is up |
| Uptime | Seconds since Matter Hub started (disabled by default) |
| Restart all bridges | Restarts every bridge |

### Each bridge

| Entity | Description |
| --- | --- |
| Status | `starting`, `running`, `stopped` or `failed`, with the failure reason as an attribute |
| Running | Switch that starts or stops the bridge |
| Devices | Matter devices the bridge exposes |
| Controllers | Paired controllers (fabrics), with their names as an attribute |
| Commissioned | On once a controller has paired |
| Failed entities | Entities Matter Hub could not expose, with the reasons as an attribute |
| Pairing code | Manual pairing code, with the QR code payload as an attribute |
| Restart, Refresh devices, Force sync | Bridge actions from the Matter Hub UI |
| Open pairing window | Lets another controller pair with an already commissioned bridge |

Bridges you add in Matter Hub appear automatically, and bridges you delete are removed. Data refreshes every 30 seconds and right after every action.

To create bridges or change which entities they expose, use the Matter Hub UI: the bridge and hub devices have a **Visit** link that opens it.

## Example automation

```yaml
automation:
  - alias: "Restart a failed Matter bridge"
    triggers:
      - trigger: state
        entity_id: sensor.living_room_status
        to: failed
        for: "00:02:00"
    actions:
      - action: button.press
        target:
          entity_id: button.living_room_restart
```

## Diagnostics

Download diagnostics from the integration page. Pairing codes, passcodes, fabric and node IDs, the Matter Hub URL and credentials are redacted.

## Troubleshooting

* **"The Matter Hub app is not running"**: start the app, then retry setup. While the app is stopped, the entities show as unavailable and come back on their own.
* **Repair says the Matter Hub app isn't available**: start the app under **Settings → Apps**. If you uninstalled it or moved Matter Hub, choose **Reconfigure** on the integration.
* **A bridge you deleted in Matter Hub is still listed**: its device is removed after about a minute and a half, once Matter Hub has left it out of three updates in a row.
* **Asked for a username and password after setup**: authentication was turned on in Matter Hub. Enter the same credentials in the repair prompt.
* **Docker install not reachable**: make sure the address opens the Matter Hub UI in a browser on the same network as Home Assistant.

### Diagnostics and debug logs

When something goes wrong, download diagnostics from **Settings → Devices & services → Matter Bridge → ⋮ → Download diagnostics** and check the file before you share it.

For debug logs, use **Enable debug logging** on the integration page, or add this to `configuration.yaml` and restart:

```yaml
logger:
  logs:
    custom_components.matter_bridge: debug
```

Then open an [issue](https://github.com/bisman-automations/ha-matter-bridge/issues/new/choose) with the diagnostics, the log, and your Home Assistant and Matter Bridge versions.

Never post a bridge's pairing code or QR code in an issue: anyone with it can add the bridge to their own Matter controller.

## Development

Tests run inside a real Home Assistant through
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component).
You need Python 3.14 for the current Home Assistant.

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest
```

To test against the oldest supported Home Assistant (2026.8), use Python 3.14 and
`pip install -r requirements_test_min.txt` instead.

CI runs the same checks on every push and pull request, on both Home Assistant
versions, plus hassfest, HACS validation and the shared repo standards, using the
workflows in [bisman-automations/.github](https://github.com/bisman-automations/.github).
Releases are drafted from [CHANGELOG.md](CHANGELOG.md); see [CLAUDE.md](CLAUDE.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

Not affiliated with the Home Assistant Matter Hub project.
