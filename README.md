# Dex Office Tour Guide

Turns the Richtech DEX robot into an office tour guide: the base navigates to preset
waypoints; at each stop it plays a narration clip through the built-in speaker and the
arm makes a pointing gesture; then it stops and waits for a salesperson/operator to
press "Next" before moving on.

**Semi-automatic**: the robot always waits after a stop — "Next" is human-triggered, so
it fits the pace of a live conversation with the visitor.

## What runs today (SIM, no robot needed)

The full orchestration + web console runs on a dev machine. Hardware is simulated (logs
actions + simulates timing), touching no real robot. The real adapters
(`guide/hardware/real.py`) are marked with TODOs and wire into
[Dex_Elevator](../Dex_Elevator)'s control layer on-site.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh                       # -> http://localhost:8600
```

On a phone on the same Wi-Fi, open `http://<this-host-ip>:8600` to drive it.

## Layout

```
guide/
  hardware/
    base.py     four hardware interfaces: Chassis / Arm / Hand / Audio
    sim.py      sim implementations (run the flow on a dev machine)
    real.py     real-robot adapters (wire into Dex_Elevator; includes wiring notes)
  config.py     loads configs/stations.yaml
  engine.py     tour state machine: navigate -> present (audio + gesture) -> wait -> next
  server.py     FastAPI: REST commands + WebSocket live state + web page
  web/index.html responsive console (phone/desktop)
configs/stations.yaml           waypoint definitions (example data, replace on-site)
configs/stations.generated.yaml waypoints synced from the robot
configs/arm_home.yaml           recorded arm standby pose (7-DOF)
tools/import_pois.py            pull robot POIs into a stations config
audio/                          narration files (recorded/generated, placed here)
```

## What a station is

See `configs/stations.yaml`. Each station = chassis pose `chassis_pose{x,y,ori}` +
(optional) narration audio + (optional) arm gesture (`arm_joints_deg` recorded via
drag-teach + a hand-pose name). Data model follows Dex_Elevator/configs/stations.yaml.

## Switching to the real robot (on-site)

1. Move the code onto the robot's Jetson (system python3, not conda) and install
   Dex_Elevator's SDK.
2. Wire `guide/hardware/real.py` (chassis IP, arm IPs left .132 / right .133, audio).
3. `GUIDE_BACKEND=real ./run.sh`.

Audio plays through the robot's WONDOM USB speaker (a PipeWire sink on the Jetson).

See `CLAUDE.md` and `PROGRESS.md` for the full hardware/network notes and status.
