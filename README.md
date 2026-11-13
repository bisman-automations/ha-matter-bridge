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

Shows [Home Assistant Matter Hub](https://github.com/RiDDiX/home-assistant-matter-hub) as an integration under **Settings → Devices & services**, with a service for Matter Hub and one for each Matter bridge you created in it.

Matter Hub does the Matter work: it publishes your Home Assistant entities to Apple Home, Google Home, Alexa and other Matter controllers. This integration lets you watch and control those bridges from Home Assistant, so you can see bridge status on dashboards, get alerted when a bridge fails, and restart or re-sync a bridge from an automation.

## Requirements

* Home Assistant 2026.8 or newer
* Home Assistant Matter Hub in Docker or standalone, reachable over the network at its web interface (port 8482 by default), or the Matter Hub app with local access allowed (Alpha app for now; see below).

## Installation

Requires **Home Assistant 2026.8 or newer**.

### Marketplace (Home Assistant 2026.11 and newer, recommended)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=bisman-automations&repository=ha-matter-bridge&category=integration)

1. Open the Marketplace and search for **Matter Bridge**, or select the button above to open this repository in the Marketplace.
2. Download **Matter Bridge** and restart Home Assistant.

New versions show up under **Settings > Updates**. Already installed Matter Bridge with
HACS? There's nothing to do: Home Assistant moves it into the Marketplace the
first time it starts on 2026.11.

### HACS (Home Assistant 2026.10 and older)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bisman-automations&repository=ha-matter-bridge&category=integration)

1. Open HACS and search for **Matter Bridge**, or select the button above to open this repository in HACS.
2. Download **Matter Bridge** and restart Home Assistant.

### Custom repository

If **Matter Bridge** does not appear in search:

1. In HACS open the menu, choose **Custom repositories**, and add `https://github.com/bisman-automations/ha-matter-bridge` as an **Integration**.
2. Download **Matter Bridge** and restart Home Assistant.

### Manual

Download `matter_bridge.zip` from the [latest release](https://github.com/bisman-automations/ha-matter-bridge/releases/latest), unzip it into `config/custom_components/matter_bridge/`, and restart Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up Matter Bridge.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=matter_bridge)

Or go to **Settings → Devices & services → Add integration → Matter Bridge**.

Setup asks for the address of the Matter Hub web interface. Leave it blank to use the Matter Hub app on this Home Assistant.

### Connecting to the Matter Hub app

The Matter Hub app lets Home Assistant connect once you allow local access. This is in the Alpha app now and comes to Stable and Testing in a later Matter Hub release.

1. Open the Matter Hub app's **Configuration** tab and turn on **Allow local access**. Setting a **Local API password** as well is recommended. Restart the app.
2. Add Matter Bridge. Leave **URL** and **Username** blank, and enter the Local API password if you set one; the app's user name, `hamh`, is filled in.
3. If more than one Matter Hub app is installed (Stable, Alpha, Testing), pick one under **Matter Hub app**.

Matter Bridge finds the app's address and port itself and follows the port if the app is reinstalled. With local access on, every program on the Home Assistant host can reach Matter Hub, and without a password each has full control of it, so set one you don't use elsewhere. While it's set, it replaces a password set under the app's **Settings**. With local access off, the app only lets the Supervisor in and setup shows **Matter Hub refused this connection**.

### Connecting to Docker or standalone Matter Hub

Enter the web interface address in **URL**, for example `http://192.0.2.50:8482`.

### Username and password

If you turned on authentication in Matter Hub's settings (or set `HAMH_HTTP_AUTH_USERNAME` / `HAMH_HTTP_AUTH_PASSWORD`), enter the same username and password. If Matter Hub has an IP allow list, add your Home Assistant host to it.

### Setups that used the Matter Hub app connection

Versions before 2.0.0 could connect through Home Assistant ingress. Those setups are not loaded after you update. A repair under **Settings → System → Repairs** asks for the address above and keeps the devices and entities you already have. You can also choose **Reconfigure** on the integration.

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
| Restart, Refresh devices, Force sync | Bridge actions from the Matter Hub UI |
| Open pairing window | Asks Matter Hub to let another controller pair with an already commissioned bridge |

Bridges you add in Matter Hub appear automatically. A bridge you delete is removed after three successful updates that leave it out (about a minute and a half). An update that cannot reach Matter Hub does not count. If you create that bridge again later, its entities come back.

To create bridges, change which entities they expose, or read a pairing code, use the Matter Hub web interface. The Matter Hub and bridge services have a **Visit** link that opens it. Home Assistant does not show the manual pairing code or the QR code: anyone who can read a state could otherwise add the bridge to their own controller.

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

Download diagnostics from the integration page. Pairing codes, QR payloads, passcodes, discriminators, fabric and node IDs, the Matter Hub URL and credentials are removed. A QR payload is removed even if Matter Hub adds it under a new name.

## Troubleshooting

* **Repair says Matter Bridge needs a URL**: this setup used the old app connection. Leave the URL blank in the repair to use the Matter Hub app again (allow local access first; see above), or enter the address of a Matter Hub in Docker; the devices and entities stay.
* **No Matter Hub app was found**: the URL was left blank, but this Home Assistant has no Matter Hub app installed (or isn't a Home Assistant OS or Supervised install). Enter the address of your Matter Hub instead.
* **Failed to connect**: check the address opens the Matter Hub web interface in a browser on the same network as Home Assistant, on port 8482 or the port you set.
* **Matter Hub refused this connection**: Matter Hub's IP allow list doesn't include this Home Assistant. For the app, turn on Allow local access and restart it (see above). For Docker or standalone, add this Home Assistant's address to its allow list.
* **A bridge you deleted in Matter Hub is still listed**: its service is removed after about a minute and a half, once Matter Hub has left it out of three successful updates in a row. An update that fails does not count.
* **A bridge you added again has no entities**: they come back on the next update after the old service was removed. Give it a couple of minutes.
* **Asked for a username and password after setup**: authentication was turned on in Matter Hub. Enter the same credentials in the repair prompt.
* **Where is the pairing code?**: open Matter Hub with the **Visit** link on the Matter Hub or bridge service, and read the code there. It is not an entity in Home Assistant. Don't share it.

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
