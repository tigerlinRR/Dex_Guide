# CLAUDE.md

Notes for a future Claude working in this repo. Style follows Dex_Elevator: record
only the non-obvious, easy-to-trip-over facts.

## What this is

**Dex_Guide** — turns the Richtech DEX robot into a **semi-automatic office tour
guide**. The base navigates to preset waypoints; at each stop it **plays a narration
clip through the built-in speaker and the arm makes a pointing gesture**, then **stops
and waits for an operator to press "Next"** (paced to a salesperson's conversation with
the visitor — it never auto-advances). Everything is driven from a responsive web console.

**This is a DIFFERENT DEX unit from Dex_Elevator** — IPs and some hardware differ, so
that code is reusable but must be re-mapped.

## Hardware (verified on the device)

- **Compute**: NVIDIA Jetson AGX Orin (hostname `jetson-agx-orin-d666`), Ubuntu, kernel 6.8-tegra.
- **Chassis**: AutoXing. Controlled through Richtech's Node/Express wrapper "robot-api" (below).
- **Arms**: dual RealMan RM, **7-DOF** (NOT the 6-DOF RM65 on the Dex_Elevator unit).
  Left `192.168.12.132`, right `192.168.12.133`, controller port `8080`.
  `/etc/richtech/richtech.yaml` holds the vendor init joint poses.
- **Hand**: LinkerHand dexterous hand on the arm's tool-side RS485 (user swapped from
  omni_picker back to LinkerHand 2026-09-21; **but richtech.yaml still says
  `gripper_type: omni_picker` — stale, needs updating**).
- **Speaker**: USB "WONDOM Audio", PipeWire sink
  `alsa_output.usb-WONDOM_WONDOM_Audio_20220112-00.analog-stereo`. Mic is a PowerConf.
- **"S" device (192.168.12.134) = WS2812 LED-strip controller** (ws281x plugin), not a
  sensor/SLAM host.
- **Cameras**: Orbbec Gemini 335 (front) + 335L (head).

## Addressing & access

Wired (Mac on the same switch): `192.168.12.x`; the robot's internal net is also `192.168.25.x`.
- Jetson: `192.168.12.131` (also .25.131). Only `:3000` (robot-api) and `:22` are exposed
  to the wired subnet.
- Arms: `.132`/`.133` port `8080` (RealMan JSON/TCP).
- The native AutoXing API lives on the internal `192.168.25.x` and is unreachable from the
  Mac subnet — use the `:3000` wrapper.
- **SSH**: user `rr` (**password NOT in the repo — ask the team / password manager**),
  has passwordless sudo.
- **Tailscale (cable-free, any network)**: node `dex-guide-jetson`, IP `100.82.223.73`,
  on the team tailnet. tailscaled starts on boot; WiFi `Richtech_Showroom` auto-connects.
  Path: Mac (on tailnet) -> Tailscale -> Jetson -> local -> arms/chassis/audio, no cable.
  **TODO**: disable key expiry for this node in the Tailscale admin console (else it drops
  offline in ~6 months).

## The robot-api wrapper (/opt/robot-api, PM2 name "robot-api", :3000)

Richtech's Express server exposing AutoXing's `@autoxing/robot-js-sdk` over HTTP. Endpoints:
`/api/health /state /moveTo(x,y) /goHome /motionFor(Forward/Back/TurnLeft/TurnRight/Cancel)
/startTask(pts[]) /poiList /setSpeed /setVolume /openBoxDoor /closeBoxDoor`.
- **No audio-play endpoint** (only setVolume). The SDK itself has startPlayAudio, but we
  don't use it — playing a wav straight to the WONDOM sink is cleaner.

## Audio (was the #1 risk, now resolved)

The robot can play our own files. On the Jetson, play a wav directly to the WONDOM sink:
`paplay --device=alsa_output.usb-WONDOM_WONDOM_Audio_20220112-00.analog-stereo <file>.wav`
(pw-play/aplay/sox are all present). Verified audible 2026-09-21. Richtech's own audio
plugin also uses this sink; PipeWire mixes, so there's no conflict.

## Arm read/control (no SDK needed, from any machine)

The RealMan controller speaks JSON/TCP on `:8080`. **Read joints (safe, no motion)**: send
`{"command":"get_joint_degree"}\r\n` -> joint angles in **milli-degrees** (/1000 = deg);
`get_current_arm_state` also returns pose[x,y,z,rx,ry,rz]. Motion commands (movej, etc.)
also go over this protocol, so gestures can likely be driven from off-robot — but **any
MOTION must be tested on-site under supervision first**. Reference implementations for the
arm/hand: `../Dex_Elevator/core/robot/realman.py` and `core/hand/linkerhand.py`.

## Codebase

Interface-first (like Dex_Elevator):
- `guide/hardware/base.py` — Chassis/Arm/Hand/Audio abstractions.
- `guide/hardware/sim.py` — runs the whole flow with no hardware (dev machine).
- `guide/hardware/real.py` — wires to the robot (RealChassis done against :3000; RealArm/Hand
  pending JSON/SDK wiring; RealAudio is a placeholder pending WONDOM playback).
- `guide/engine.py` — tour state machine (IDLE -> NAVIGATING -> PRESENTING -> WAITING ->
  ESTOP; **"Next" is human-triggered**).
- `guide/server.py` — FastAPI (REST + WebSocket) + `web/index.html` responsive console.
- `configs/stations.yaml` (example), `configs/stations.generated.yaml` (synced from the robot).
- `configs/arm_home.yaml` — recorded arm standby pose (7-DOF).
- `tools/import_pois.py` — pulls robot POIs into a stations config.

## Run (sim, any laptop)

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh                      # -> http://localhost:8600
```
Real backend: `GUIDE_BACKEND=real` (must be able to reach the robot; run on/near it).

## Waypoints (synced 2026-09-21)

5 tour stops Guide1–Guide5 (+ dock "Charging pile - Dex Guide"). Coordinates in
`configs/stations.generated.yaml`. **Gesture and audio per stop still to be recorded.**

## A gesture gotcha (from Dex_Elevator, re-verify here)

On the elevator DEX the **arm/chest face 180° from the base's front**. Pointing direction
must be reconciled with the chassis heading. Because gestures are captured by drag-teach
(WYSIWYG), **pose the arm in situ with the robot at the waypoint in its presentation
heading** for the most reliable result.

## Credentials

**This repo contains no passwords.** SSH/WiFi/admin passwords are held by the team /
password manager and **must never be committed**.
