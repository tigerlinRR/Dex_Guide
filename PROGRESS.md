# PROGRESS

Dex_Guide progress log (newest first).

## 2026-09-24 — MILESTONE: tablet-driven tours run end to end on the real robot

**What works:** a salesperson drives a full 4-stop tour from a tablet — Go to Guide1 →
Start → Guide2/3/4 present on arrival → Return to charger (docks). Every stop is reached
within 1–3 cm, each presents with torso lift + gestures + narration, and the robot docks.

**How it was achieved (two terminals, one contract):**
- *Motion terminal* (`robot/`, runtime `~/dex_guide`): Quest teleop recordings → trimmed,
  smoothed, bridged per-stop motions replayed through the teleop stack; narration wavs cued
  to gesture segments; travel pose between stops; audio self-heal after reboot; torso lift
  (1000 mm presenting / 800 mm driving, soft landing); silent sink wake. Contract:
  `run_stop.py GuideN` blocks, exit 0.
- *Console terminal* (`guide/`, `deploy/`, `configs/`): tablet UI + state machine with the
  user's flow; runs on the Jetson as a service; chassis via robot-api (moveTo with heading,
  goHome docking); stop poses read live from the robot's map (by id, then name); the tablet
  reaches it over the robot's own hotspot (company Wi-Fi blocks external devices);
  persistent timestamped tour log.

**Open:** lift not stopped/lowered when a stop is interrupted (proposal in CLAUDE.md, not
approved yet); heading unit unconfirmed; path-planning mode; depth-camera calibration;
Tailscale key expiry.

## 2026-09-24 — Live map poses, heading, first full tablet runs

- Full tours run from the tablet: every stop reached (1–3 cm), all four presented, docked
  back on the charger each time.
- Stop poses now come from the robot's map at drive time (by POI id, then by name — Guide1/4
  were re-created with new ids). Config coords are only a fallback.
- Map heading edits had no effect because only x,y was sent; `moveTo` now sends the POI heading
  (degrees assumed) and waits for the in-place turn. User reports Guide4 now faces correctly,
  but the log shows a 53deg gap between target and chassis-reported heading — unconfirmed,
  see CLAUDE.md.
- Path planning: `moveTo` has no track/route mode; `/api/startTask` does (runMode/routeMode),
  meanings unverified. Parked by the user.
- Jump straight to one stop (tap its number, confirm) works for testing single stops.

## 2026-09-23 — Operator console wired to the robot (tablet control)

### Flow (as the user defined it)
1. **Go to Guide1** — drives there and parks, no presentation.
2. **Start Guide1** — presents in place (`run_stop.py Guide1`).
3. **Next: Guide2/3/4** — drives, presents automatically on arrival, waits for Next.
4. **Return to charger** — robot-api `goHome` to POI "Charging pile - Dex Guide"; done when
   `isCharging` turns true.

### Console
- Rebuilt `guide/web/index.html` for a salesperson: one big context button, Pause /
  Stop talking while busy, stepper jump with a confirm tap, fixed STOP ROBOT, offline
  lock-out. "Replay this stop" was built and then removed at the user's request.
- Engine: never skips an unreached stop (`arrived`); pause keeps position; reset after
  e-stop resumes the tour; if a playback was interrupted, `go_travel.py` tucks the arms
  before the next drive. E-stop itself triggers no motion.
- Gesture + narration are delegated to the finalized `~/dex_guide/run_stop.py` (no arm code
  in `guide/`).

### Deployment / access
- Runs on the Jetson as systemd `dex-guide` (`~/Dex_Guide`, `deploy/push.sh`).
- **Tablet (Android A50) joins the robot's hotspot `dex-teleop` → `http://10.42.0.1:8600`.**
  The teleop hotspot takes the Jetson's only wifi radio, so Tailscale is offline while it
  runs; maintenance goes over wired `192.168.12.131`.
- Jetson lacks `python3.12-venv`: venv built `--without-pip`, deps installed with system pip.
- Persistent tour log `~/Dex_Guide/logs/guide.log` (journal is volatile on this unit).

### Verified
- Sim: full flow incl. pause / e-stop / retry / return; browser UI states.
- Robot: service up over the hotspot IP; `run_stop.py --list` from the service env; silent
  `paplay` as the service user; teleop stack + both arms error-free; chassis connected.

### Not yet verified (first supervised run)
- First real `moveTo` and `goHome` (docking). Arrival heading — `moveTo` takes `yaw` but its
  units are unconfirmed, so only x,y is sent for now.
- Chassis warns "depth camera (ihawk_downward_node) need calibration".

## 2026-09-23 — Tour gestures + narration finished for all 4 stops (`robot/`)

The per-stop gesture + narration playback is done and finalized. Runtime lives on the
Jetson under `~/dex_guide/`; a clean snapshot is committed here under `robot/`.

### How a stop plays
- **Entry point (the UI contract):** `python ~/dex_guide/run_stop.py Guide1|Guide2|Guide3|Guide4`
  — blocks until the stop finishes (audio + gesture + tuck to travel pose), exit 0 = ok.
  `run_tour.py` chains all four for testing. Recipes live in `stations.yaml`.
- Gestures play **through the teleop stack** (`~/teleop/bin/motion_recorder.py` replay:
  redis → servo_realman → canfd), from Quest teleop recordings `Wave/Talk/Left/Right`.
- Narration is a wav played to the WONDOM sink, kept in lock-step with the arm.

### Motion-authoring decisions (why the final shape)
- **Rejected: hand-drag "direct move" authoring** (`gesture_tool.py`, direct RealMan
  JSON `movej`/drag-teach — kept in `robot/` as the idea/tooling). It worked as a tech
  reserve, but off-robot `movej` streaming was jerky and the safety envelope was ours to
  babysit. **Chosen:** the colleague's Quest-teleop recordings replayed at 50 Hz canfd —
  smoother, and servo_realman owns the safety (per-tick clamp, e-stop latch). Its output
  test recordings were deleted.
- **Speed:** 1.0x replay is safe (the "1.0x e-stops" we saw were a false positive — a
  benign `not in servo mode` during the approach, not `emergency`). `REPLAY_MAX_DEG_PER_TICK=8.0`.
- **No forward-cup "捧胸" at a stop start:** point gestures start with a cosine bridge
  `travel→apex` (`*_point`), not a blocking `movej` approach.
- **Return before the audio ends:** each stop's return is a streamed bridge `apex→travel`
  (`Ret_from_*`), cued a few seconds before the narration finishes, so the arm is already
  tucking as the last words play — never after silence.
- **Collision-safe opening (Guide1):** the wave is the only place both arms swung to the
  centre. Guide1 is composed per-arm so only one arm is ever forward — right-hand wave
  (left stays at travel) → two-arm talk (arms stay on opposite sides) → two-arm point at
  ADAM. A `smooth_cols(15)` pass over the whole trajectory blends the bridge/gesture seams.

### Final per-stop recipes (`stations.yaml`)
- **Guide1** (continuous): right-hand wave → talk 0.4x → two-arm point at ADAM @18s → hold → return @21.5s.
- **Guide2**: point left (Adam+Scorpion) @1s → sweep right (Dusty) @15.4s → return @21s.
- **Guide3**: point right (sales/marketing) @0 → sweep left (R&D) @6.9s → return @13s.
- **Guide4**: point left @0 → return @13s.
- The **travel pose** (`gestures/travel.json`, user-posed, arms tucked, hands apart) is the
  rest/return/inter-stop pose; every stop ends there so the base can navigate safely.

### Also handled today
- **Audio self-heal:** after every reboot PipeWire sets the WONDOM card profile to `off`
  (no sink) and the sink name can gain a `.2` suffix. The play scripts now set
  `output:analog-stereo`, resolve the sink name live, unmute, and set volume. (`rr` is UID
  **2002** on this unit, not 1000.)
- Cue times came from silence-gap analysis of each narration wav (no ASR on the box) + tuning by ear.

### Next
- **Wire the UI** (user driving) → button/Next calls `run_stop.py <stop>`.
- **Base navigation between stops** is NOT wired yet — needs `robot-api :3000` `moveTo`
  between stops, then the full arrive → play → Next → drive loop.

## 2026-09-21 — Bring-up, remote access, audio verified, waypoints synced

### Network / bring-up
- Diagnosed and fixed the robot link: the original cable only negotiated 100M (cable/RJ45
  with just 4 wires) -> replaced, now 1000BaseT.
- Fixed IP config: the Mac's en0 was `192.168.11.50/16` while the robot is on
  `192.168.12.x/24` — ARP resolved but there was no IPv4 return path; setting the Mac to
  `192.168.12.50` made A/L/R/S all reachable.
- Device roles clarified: A=Jetson (`192.168.12.131`, dual-homed .25.131), L/R=left/right
  arms (.132/.133), **S=WS2812 LED-strip controller (.134)** (previously mis-identified).

### Remote access (works cable-free)
- SSH into the Jetson as user `rr`, passwordless sudo.
- The Jetson's wired net has no internet -> connected WiFi to `Richtech_Showroom` (auto-reconnect).
- Installed Tailscale 1.102.4 -> node `dex-guide-jetson` @ `100.82.223.73`, on the team
  tailnet, persistent across reboot. **Verified: with the cable unplugged, chassis/arm are
  still reachable over Tailscale** (Mac -> Tailscale -> Jetson -> local).
- TODO: disable Tailscale key expiry for this node (else it drops offline in ~6 months).

### Audio (the #1 unknown) — RESOLVED
- The robot-api wrapper only exposes setVolume, no play endpoint. The AutoXing SDK has
  startPlayAudio, but simpler: the robot has a real USB speaker (WONDOM) as a standard
  PipeWire sink; play a wav straight to it with `paplay`/`pw-play`.
- **Test tone verified audible.** Decision: audio via the robot's built-in speaker (user's
  call). Narration files (recorded or AI-generated) -> played on the Jetson to the WONDOM sink.

### Software
- Built the guide skeleton: FastAPI backend + responsive web console + interface-first
  hardware layer (sim + real). Semi-auto state machine ("Next" is human-triggered).
  **End-to-end verified in sim and in the browser.**
- RealChassis wired to :3000 (navigate = moveTo + poll state; cancel = motionFor Cancel).
  Read path verified against the live robot. **Navigation execution not yet triggered**
  (awaits on-site supervised first test).

### Waypoints
- User marked 5 tour stops (Guide1–Guide5) + dock (Charging pile - Dex Guide). Synced to
  `configs/stations.generated.yaml` (full-precision coordinates). **Gesture and audio pending.**

### Hardware notes
- Arms are **7-DOF** (not the 6-DOF elevator unit). Read joint angles over RealMan JSON/TCP
  `:8080` (drag-teach -> record). Recorded a standby pose -> `configs/arm_home.yaml`.
- User swapped the end-effector back to the LinkerHand dexterous hand; richtech.yaml still
  says omni_picker (stale — update it for the robot's own stack).

### Next
- **Record per-stop arm gestures** (drag-teach -> read joints -> bind to a waypoint).
- **Record/generate per-stop narration audio**; wire RealAudio to WONDOM playback on the Jetson.
- **On-site supervised first test** of chassis navigation (first moveTo) and arm motion.
- Update richtech.yaml `gripper_type`; confirm the LinkerHand is live on the tool bus.
