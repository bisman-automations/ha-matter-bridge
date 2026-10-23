# Matter Bridge

Shows [Home Assistant Matter Hub](https://github.com/RiDDiX/home-assistant-matter-hub) as an integration under **Settings → Devices & services**, with a device for Matter Hub and one for each Matter bridge you created in it.

Matter Hub does the Matter work: it publishes your Home Assistant entities to Apple Home, Google Home, Alexa and other Matter controllers. This integration lets you watch and control those bridges from Home Assistant, so you can see bridge status on dashboards, get alerted when a bridge fails, and restart or re-sync a bridge from an automation.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bisman-automations&repository=ha-matter-bridge&category=integration)

## Requirements

* Home Assistant 2025.2 or newer
* Home Assistant Matter Hub, either:
  * the **Matter Hub app** (add-on) on Home Assistant OS or Supervised, or
  * Matter Hub in Docker or standalone, reachable over the network (port 8482 by default)

## Installation

1. In HACS, add `https://github.com/bisman-automations/ha-matter-bridge` as a custom repository (type **Integration**), or use the button above.
2. Install **Matter Bridge** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Matter Bridge**.

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
* **Asked for a username and password after setup**: authentication was turned on in Matter Hub. Enter the same credentials in the repair prompt.
* **Docker install not reachable**: make sure the address opens the Matter Hub UI in a browser on the same network as Home Assistant.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## License

Apache 2.0. Not affiliated with the Home Assistant Matter Hub project.
