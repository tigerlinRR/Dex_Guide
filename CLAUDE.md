# CLAUDE.md

## ⚠️ 语言规则（默认，必须遵守）

**在 Claude Code 里和用户的所有对话一律用中文**——包括最终回复、工具调用之间的进度说明、
提问和总结，从第一句到最后一句都不要切换成英文，哪怕刚写完英文代码或读了英文日志。
只有代码、命令、文件路径、日志原文和专有名词保留原文。用户已为此纠正过很多次。
（代码、代码注释、提交信息、本文件其余部分保持仓库原有的英文风格。）

Notes for a future Claude working in this repo. Style follows Dex_Elevator: record
only the non-obvious, easy-to-trip-over facts.

## What this is

**Dex_Guide** turns the Richtech DEX robot into a **semi-automatic office tour guide**,
operated by a salesperson from a tablet. **Status (2026-09-24): milestone done** — full
tours run end to end on the real robot (drive → gesture + narration → wait → … → dock).

**This is a DIFFERENT DEX unit from Dex_Elevator** — IPs and some hardware differ.

## How a tour runs (current)

Tablet → console (`guide/`, on the Jetson) → chassis via robot-api `:3000` + per-stop
playback via the colleague's `~/dex_guide/run_stop.py` (`robot/` in this repo).

| Operator presses | Robot does |
|---|---|
| **Go to Guide1** | drives to Guide1 and **parks without presenting** |
| **Start Guide1** | presents Guide1 in place |
| **Next: Guide2/3/4** | drives, **presents automatically on arrival**, waits |
| **Return to charger** | robot-api `goHome` → docks on "Charging pile - Dex Guide" |

Rules the user set — don't undo them:
- Every step is operator-triggered except that Guide2–4 present on arrival. Stop index 0
  never auto-presents (`presented` flag in the engine).
- **No "replay this stop" button** — built once, rejected as redundant.
- Tapping a stop number (then confirming) jumps straight there — used to test one stop.
- **Never skip an unreached stop**: after a pause / failed drive / e-stop, Next retries it.
- E-stop triggers no motion. If a playback was interrupted, the next drive first runs
  `~/dex_guide/go_travel.py` (arms to travel pose).

## Access & deployment

- **Tablet (Android A50) joins the robot's own hotspot `dex-teleop` (5 GHz) and opens
  `http://10.42.0.1:8600`.** `dex-teleop-hotspot.service` takes the Jetson's ONLY wifi
  radio on boot → the Jetson is off site WiFi, has **no internet**, and **Tailscale shows
  offline**. Maintain it over wired `192.168.12.131` (Mac on the same switch).
- Console = systemd `dex-guide` (`~/Dex_Guide`, `deploy/push.sh`; use
  `JETSON=rr@192.168.12.131` when Tailscale is down). Autostarts, restarts on failure.
  `dex-teleop`, `dex-teleop-hotspot`, `redis-server`, robot-api (PM2) also autostart; give
  the teleop stack a minute after boot before pressing anything.
- The Jetson lacks `python3.12-venv`: the venv is built `--without-pip` and deps installed
  with the system pip (`--python`). `deploy/install.sh` handles it.
- **Tour log**: `~/Dex_Guide/logs/guide.log` (systemd appends stdout; the journal is
  volatile on this unit). `[tour]` state changes, `[chassis]` moveTo / arrival (pos, heading
  target vs actual) / stall details, and run_stop.py's output. **Jetson clock is CST (UTC+8).**
- **Mac-side Python can't reach the robot's HTTP ports** (macOS local-network restriction);
  ssh works. Run robot-side checks over ssh on the Jetson.

## Chassis (robot-api `/opt/robot-api`, PM2 "robot-api", `:3000`)

Richtech's Express wrapper over AutoXing's `@autoxing/robot-js-sdk`. Endpoints:
`/api/health /state /moveTo /goHome /motionFor /startTask /poiList /setSpeed /setVolume`.
It is Richtech's service — don't modify it without asking.
- **Stop poses come from the robot's map at drive time**: POI lookup by `id`, then by unique
  `poi_name` (re-creating a point in AutoXing gives it a NEW id — happened to Guide1/Guide4).
  Coords in `configs/stations.generated.yaml` are only a fallback (logs a WARNING). So
  re-marking a point in AutoXing takes effect on the next drive with no re-sync; renaming a
  point or duplicating a name does NOT.
- `moveTo {x, y, yaw}`: yaw sent in **degrees (assumed)**, `GUIDE_MOVETO_YAW=deg|rad|off`.
  The SDK forwards it verbatim to the chassis. Arrival = within 0.25 m, zero speed and
  `isTasking` cleared (the base turns in place at zero speed; settle cap 15 s).
  `/api/state` `yaw` is radians, 1 decimal (coarse).
- `goHome {x, y, yaw}` takes the pile POI values verbatim (yaw in degrees); done when
  `isCharging` turns true. **Verified: docks reliably.**
- `moveTo` is a bare direct move — no route/track mode. Route options (`runMode`,
  `routeMode`, `speed`, default 1) exist only in the task API, reachable via `/api/startTask`
  (forwards the body verbatim). Value meanings are not in the SDK — check AutoXing docs.
- Chassis has warned "depth camera (ihawk_downward_node) need calibration" throughout.

## Per-stop playback (`robot/`, owned by the colleague's terminal)

Runtime lives on the Jetson at `~/dex_guide/` (**theirs — don't edit it**); `robot/` is the
committed snapshot.
- **Contract:** `~/dex_guide/run_stop.py Guide1..4` (teleop conda env) blocks until the stop
  finishes — lift up, gesture + narration, arms to travel pose, lift down — exit 0 = ok.
  The console calls it via `guide/hardware/stop_runner.py` in its own process group.
- Gestures replay **through the teleop stack** (`~/teleop/bin/motion_recorder.py`: redis →
  servo_realman → canfd) from Quest teleop recordings; recipes (segments + narration cue
  times) in `robot/stations.yaml`. Details and rationale: `robot/README.md`, PROGRESS.
- **Torso lift** (`robot/lift.py`): on the right arm controller (`.133`, JSON
  `get_lift_state` / `set_lift_speed`). run_stop raises to 1000 mm for the presentation and
  lowers to 800 mm to drive. It is a **velocity** command — the stop (`set_lift_speed 0`)
  only happens in `move_to`'s `finally`. See Open issues.
- **Audio breaks after every reboot** (WONDOM card profile reset to `off`, sink name may
  gain `.2`). The play scripts self-heal it. `rr` is **UID 2002** (`/run/user/2002`).

## Hardware (verified on the device)

- **Compute**: Jetson AGX Orin `jetson-agx-orin-d666`, Ubuntu, kernel 6.8-tegra.
- **Arms**: dual RealMan, **7-DOF**; left `192.168.12.132`, right `192.168.12.133`, `:8080`
  JSON/TCP (`get_joint_degree` → milli-degrees). Any new MOTION: supervised test first.
- **Hand**: LinkerHand (richtech.yaml still says `gripper_type: omni_picker` — stale).
- **Speaker**: USB WONDOM (PipeWire sink). **S `192.168.12.134`** = WS2812 LED controller.
- **Network**: wired `192.168.12.x` (+ internal `192.168.25.x`, native AutoXing API, not
  reachable from the Mac). SSH user `rr`, passwordless sudo. Tailscale node
  `dex-guide-jetson` `100.82.223.73` (only when the hotspot is off).

## Codebase

- `guide/engine.py` — tour state machine (IDLE / NAVIGATING / PRESENTING / WAITING / ESTOP)
  with the flow rules above; return-to-charger; live POI pose lookup.
- `guide/hardware/` — `base.py` interfaces, `sim.py` (no hardware), `real.py` (RealChassis;
  RealAudio = paplay, unused when a stop has `run_stop:`; RealArm/Hand intentionally
  unimplemented), `stop_runner.py` (→ run_stop.py / go_travel.py).
- `guide/server.py` + `guide/web/index.html` — FastAPI REST/WebSocket + tablet console.
- `configs/stations.generated.yaml` — the real tour (POI ids/names, subtitles, `run_stop:`,
  `home:`). `configs/stations.yaml` is example data for sim.
- Sim on any laptop: `./run.sh` → `http://localhost:8600` (set
  `GUIDE_STATIONS=configs/stations.generated.yaml` for the real stops).

## Open issues (as of 2026-09-24)

1. **Lift can be left moving / raised when a stop is interrupted.** Pause, Stop talking,
   E-stop and End tour kill run_stop.py's process group; SIGTERM skips `move_to`'s
   `finally`, so `set_lift_speed 0` may never be sent, and the pre-drive tuck does not lower
   the lift. Proposed (not yet approved): after the kill, send `set_lift_speed 0`; before the
   next drive, lower to 800 mm alongside go_travel. Test the controller's own behaviour
   under supervision.
2. **Heading unconfirmed**: the first yaw run logged actual 151.8° vs target 205.1° though
   Guide4 looked right (it came from the charger, not Guide3). Test: reach Guide4 from two
   directions and compare.
3. Path planning mode (track vs free) — parked by the user; would mean moving to `/api/startTask`.
4. Chassis depth-camera calibration warning.
5. Tailscale key expiry not disabled for `dex-guide-jetson` / tablet `a50`.

## Credentials

**This repo contains no passwords.** SSH/WiFi/admin passwords are held by the team /
password manager and **must never be committed**.
