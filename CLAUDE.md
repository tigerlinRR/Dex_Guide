# CLAUDE.md

## ⚠️ 语言规则（默认，必须遵守）

**在 Claude Code 里和用户的所有对话一律用中文**——包括最终回复、工具调用之间的进度说明、
提问和总结，从第一句到最后一句都不要切换成英文，哪怕刚写完英文代码或读了英文日志。
只有代码、命令、文件路径、日志原文和专有名词保留原文。
（代码、代码注释、提交信息、本文件其余部分保持仓库原有的英文风格。）

Notes for a future Claude working in this repo. Style follows Dex_Elevator: record
only the non-obvious, easy-to-trip-over facts.

**Always reply to the user in Chinese (中文)** — every message, including short progress
notes between tool calls. Code, comments and commit messages stay in English. The user has
had to correct this repeatedly.

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

## Tablet access & playback (2026-09-23)

- **The operator tablet joins the robot's own hotspot `dex-teleop` (5 GHz) and opens
  `http://10.42.0.1:8600`.** `dex-teleop-hotspot.service` (enabled) turns the Jetson's ONE
  wifi radio into that AP on boot, so the Jetson is then **off site WiFi, has no internet,
  and Tailscale shows offline** — reach it over wired `192.168.12.131` instead.
- The console runs on the Jetson as systemd `dex-guide` (`~/Dex_Guide`, deployed with
  `deploy/push.sh`; `JETSON=rr@192.168.12.131` when Tailscale is down).
- **Gesture + narration per stop are NOT done by this repo**: `run_stop:` in
  stations.generated.yaml hands each stop to the colleague's finalized
  `~/dex_guide/run_stop.py <name>` (teleop conda env; needs `dex-teleop.service` up,
  which starts on boot). `~/dex_guide` is theirs — don't edit it. If a playback is
  interrupted, the engine runs `~/dex_guide/go_travel.py` before the next drive.
- **Flow (user-defined 2026-09-23):** "Go to Guide1" drives there and PARKS without
  presenting → "Start Guide1" presents in place → Next drives to Guide2/3/4, which present
  automatically on arrival → after Guide4, "Return to charger". Rule in engine: stop index 0
  never auto-presents (`presented` flag); every other stop does.
- **After Guide4, Next = "Return to charger"**: robot-api `goHome` with the `home:` block in
  stations.generated.yaml (POI "Charging pile - Dex Guide", values verbatim, yaw in degrees);
  done when `isCharging` turns true. Unverified on the real robot.
- **Stop poses come from the robot's map at drive time** (POI lookup by `id` via
  `/api/poiList`, **then by unique `poi_name`** — a point deleted and re-created in AutoXing
  gets a NEW id, which happened to Guide1/Guide4 on 2026-09-24); the coords in
  stations.generated.yaml are only a fallback, and using them logs a WARNING. So re-marking a
  point in AutoXing takes effect on the next drive — no re-sync. (Before 2026-09-23 the config
  copy was used and went stale: the first live run drove precisely to the OLD points.)
- **Tour log**: `~/Dex_Guide/logs/guide.log` on the Jetson (systemd appends stdout there —
  the journal is volatile). Timestamped `[tour]` state changes, `[chassis]` moveTo/arrival/
  stall details, and run_stop.py's own output. **Jetson clock is CST (UTC+8).**
- UI rules the user set: no "replay" button (rejected as redundant); every step is
  operator-triggered except that Guide2–4 present automatically on arrival.
- **Heading**: until 2026-09-24 only x,y was sent, so map heading edits had no effect (Guide4
  kept facing the wrong way). RealChassis now sends the POI heading as `yaw` in **degrees
  (assumed** — same SDK's goHome takes degrees and docks; `GUIDE_MOVETO_YAW=deg|rad|off`).
  Arrival waits for `isTasking` to clear (the base turns in place at zero speed) and logs
  `heading actual/target/diff` — check that line after the first run to confirm the unit.
  `/api/state` reports `yaw` in radians.
  **Still unconfirmed (2026-09-24):** the first run with yaw logged actual 151.8deg vs target
  205.1deg (diff -53) although the user saw Guide4 facing correctly — that run came from the
  charger, not Guide3, so it may be the approach direction. The SDK forwards `{x,y,yaw}`
  verbatim to the chassis (no conversion). Decisive test: reach Guide4 from two directions
  and compare. `/api/state` yaw is coarse (1 decimal of radians).
- **Path planning**: `moveTo` is a bare direct move — no route/track options. Route options
  live in the SDK's task API (`runMode`, `routeMode`, `speed`, … default 1), reachable via
  robot-api `/api/startTask`, which forwards the body verbatim (no robot-api change needed).
  The meaning of each runMode/routeMode value is NOT in the SDK — check AutoXing docs first.
  User parked this on 2026-09-24 ("就这样吧").

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
- **After every reboot audio silently breaks**: PipeWire sets the WONDOM card profile to
  `off` (so no sink exists) and the sink name can gain a `.2` suffix. Fix: `pactl
  set-card-profile alsa_card.usb-WONDOM_WONDOM_Audio_20220112-00 output:analog-stereo`, then
  resolve the sink name live (`pactl list short sinks | grep -i wondom`), unmute, set volume.
  The `robot/play_station*.py` scripts already do this. Note `rr` is **UID 2002** here
  (`XDG_RUNTIME_DIR=/run/user/2002`), so don't hardcode `/run/user/1000`.

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
- `guide/hardware/real.py` — RealChassis against :3000 (`moveTo` + `goHome`, arrival by
  polling `/api/state`); RealAudio = `paplay` to WONDOM (unused when a stop has `run_stop:`);
  RealArm/Hand are intentionally unimplemented — the tour's arms go through `run_stop.py`.
- `guide/hardware/stop_runner.py` — calls `~/dex_guide/run_stop.py` / `go_travel.py` in the
  teleop env, in its own process group so pause/e-stop kill the player and pw-play too.
- `guide/engine.py` — tour state machine (IDLE -> NAVIGATING -> PRESENTING -> WAITING ->
  ESTOP; **"Next" is human-triggered**).
- `guide/server.py` — FastAPI (REST + WebSocket) + `web/index.html` responsive console.
- `configs/stations.yaml` (example), `configs/stations.generated.yaml` (synced from the robot).
- `configs/arm_home.yaml` — recorded arm standby pose (7-DOF).
- `tools/import_pois.py` — pulls robot POIs into a stations config.

## Tour gesture+narration playback (`robot/`, DONE for all 4 stops)

This is the real, working per-stop playback — separate from the `guide/` FastAPI skeleton.
Runtime lives on the Jetson at `~/dex_guide/`; a clean snapshot is in `robot/`.

- **Entry point (UI contract):** on the Jetson, `conda activate teleop; python
  ~/dex_guide/run_stop.py Guide1|Guide2|Guide3|Guide4`. Blocks until the stop finishes
  (audio + gesture + tuck to travel pose), exit 0 = ok. Self-heals (resumes a latched arm,
  fixes the audio sink, retries on a servo latch). `run_tour.py` chains all four.
- **Recipes:** `robot/stations.yaml` — per-stop gesture segments + narration cue times.
  Edit here to retime; no code change needed.
- **How it runs:** gestures replay **through the teleop stack** (`~/teleop/bin/motion_recorder.py`:
  redis → servo_realman → canfd), NOT the direct-JSON path below. Sources are the Quest
  teleop recordings `Wave/Talk/Left/Right`; `robot/build_*.py` trim/smooth/bridge them into
  the per-stop motions. Narration wav is played to the WONDOM sink in lock-step.
- **Key choices** (see PROGRESS 2026-09-23): 1.0x replay is safe (`REPLAY_MAX_DEG_PER_TICK=8.0`);
  point gestures start with a `travel→apex` cosine bridge (no `movej` "捧胸"); returns are
  `apex→travel` bridges cued *before* the narration ends; Guide1's opening is composed
  per-arm so the two hands never meet at centre (right-hand wave, left stays at travel).
- The **travel pose** (`robot/gestures/travel.json`) is the rest/return/inter-stop pose.
- **`gesture_tool.py`** is the earlier hand-drag / direct-RealMan-`movej` authoring path —
  kept as a tech reserve + arm-read/drag utility, but NOT how the final tour plays.
- **Wired to the UI (2026-09-23):** the console drives the base between stops and calls
  `run_stop.py` per stop — see `## Tablet access & playback`.

## Run (sim, any laptop)

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh                      # -> http://localhost:8600
```
Real backend: `GUIDE_BACKEND=real` (must be able to reach the robot; run on/near it).

## Waypoints (synced 2026-09-21)

5 tour stops Guide1–Guide5 (+ dock "Charging pile - Dex Guide"). Coordinates in
`configs/stations.generated.yaml`. **Gesture + narration DONE for Guide1–4** (see
`## Tour gesture+narration playback` and `robot/`); Guide5 was dropped by the user.
Base navigation is wired; its first real run (heading, docking) is still to be verified.

## A gesture gotcha (from Dex_Elevator, re-verify here)

On the elevator DEX the **arm/chest face 180° from the base's front**. Pointing direction
must be reconciled with the chassis heading. Because gestures are captured by drag-teach
(WYSIWYG), **pose the arm in situ with the robot at the waypoint in its presentation
heading** for the most reliable result.

## Credentials

**This repo contains no passwords.** SSH/WiFi/admin passwords are held by the team /
password manager and **must never be committed**.
