# Dex Office Tour Guide

Turns the Richtech DEX robot into a semi-automatic office tour guide. A salesperson walks
with the visitor and drives the tour from a tablet: the robot drives to each stop, raises
its torso, plays a narration through its speaker while the arms point at what it is
describing, then waits for the salesperson before moving on. After the last stop it
returns to its charger.

**Status (2026-09-24): working end to end on the real robot.** Open issues: `CLAUDE.md`.

## Operating a tour

1. Tablet → Wi-Fi **`dex-teleop`** (the robot's own hotspot) → open **`http://10.42.0.1:8600`**.
2. **Go to Guide1** — the robot drives there and waits.
3. **Start Guide1** — it presents Guide1.
4. **Next: Guide2 / Guide3 / Guide4** — it drives and presents on arrival.
5. **Return to charger** — it drives back and docks.

Pause / Stop talking while it is busy, **STOP ROBOT** at any time (a software stop — the
physical e-stop is the real safety device). Tap a stop number and confirm to jump to it.
Stop positions and headings are read from the robot's map, so re-marking a point in
AutoXing takes effect on the next drive (keep the names Guide1–Guide4).

## How it is built

```
tablet ──Wi-Fi hotspot──▶ console on the Jetson (guide/, systemd dex-guide, :8600)
                             ├─ chassis: robot-api :3000 → AutoXing (moveTo / goHome / poiList)
                             └─ each stop: ~/dex_guide/run_stop.py GuideN  (robot/)
                                   lift up → gestures (teleop stack replay) + narration → lift down
```

```
guide/             console: engine.py (tour state machine), server.py (FastAPI + WebSocket),
                   web/index.html (tablet UI), hardware/ (sim + real adapters, stop_runner)
configs/           stations.generated.yaml = the real tour (stops, charger, run_stop names)
robot/             per-stop gesture + narration playback (snapshot of ~/dex_guide on the Jetson)
audio/             narration scripts + wav files
deploy/            systemd unit, install.sh (on the Jetson), push.sh (from the Mac)
```

## Develop / deploy

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
GUIDE_STATIONS=configs/stations.generated.yaml ./run.sh    # sim → http://localhost:8600

JETSON=rr@192.168.12.131 ./deploy/push.sh                 # deploy (Mac wired to the robot)
```

Tour log on the robot: `~/Dex_Guide/logs/guide.log`. See `CLAUDE.md` (facts and gotchas)
and `PROGRESS.md` (history).
