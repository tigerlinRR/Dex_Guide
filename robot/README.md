# robot/ — on-Jetson tour playback (finalized)

Snapshot of `~/dex_guide/` on the Jetson (`jetson-agx-orin-d666`, user `rr`). This is the
real per-stop gesture + narration playback for the office tour. It runs **through the teleop
stack** (`~/teleop/bin/motion_recorder.py` → redis → servo_realman → canfd), so the teleop
stack must be up and its `teleop` conda env active.

## Run

```bash
conda activate teleop
python ~/dex_guide/run_stop.py Guide1        # one stop: audio + gesture, blocks until done, exit 0 = ok
python ~/dex_guide/run_stop.py --list        # -> Guide1, Guide2, Guide3, Guide4
python ~/dex_guide/run_tour.py               # chain all four (testing)
```

`run_stop.py <stop>` is the **UI contract**: it blocks until the stop finishes (narration +
gesture + tuck to the travel pose), returns exit 0 on success, and self-heals — resumes a
latched arm, restores the WONDOM audio sink (broken by every reboot), retries once on a
servo latch.

## Files

- `stations.yaml` — per-stop recipe (gesture segments + narration cue seconds). **Edit here
  to retime**; the two players read it.
- `run_stop.py` / `run_tour.py` — entry points.
- `play_station.py` — continuous player (Guide1): narration syncs to the gesture start,
  motion runs until the audio ends, then tucks to travel.
- `play_station_seq.py` — timed-segment player (Guide2/3/4): narration first, each segment
  fires at its cue, the arm holds between segments.
- `build_*.py` — rebuild the per-stop motions from the raw recordings (trim prep, smooth,
  cosine bridges, apex split). `build_guide1.py` composes Guide1 per-arm.
- `go_travel.py` — move the arms to the travel pose.
- `gesture_tool.py` — earlier hand-drag / direct-RealMan-`movej` authoring path; kept as a
  tech reserve and arm-read utility, **not** how the tour plays.
- `gestures/travel.json` — the tucked rest/return/inter-stop pose (arms in, hands apart).
- `recordings/` — `Wave/Talk/Left/Right` are the raw Quest teleop recordings (source of
  truth); the rest are built per-stop motions. On the robot these live in
  `~/teleop/recordings/`; copy them there to run.

## Stops

| Stop  | Gesture timeline |
|-------|------------------|
| Guide1 | right-hand wave → talk 0.4x → two-arm point at ADAM @18s → hold → return @21.5s |
| Guide2 | point left (Adam+Scorpion) @1s → sweep right (Dusty) @15.4s → return @21s |
| Guide3 | point right (sales/marketing) @0 → sweep left (R&D) @6.9s → return @13s |
| Guide4 | point left @0 → return @13s |

Every stop ends at the travel pose so the base can navigate without the arms too wide.
Cue times were set from silence-gap analysis of each narration wav — tune by ear in
`stations.yaml`.

## Not wired yet

Base navigation between stops. A live tour still needs `robot-api :3000` `moveTo` to drive
Guide1 → Guide2 → … between plays (arrive → `run_stop` → operator Next → drive).

## Torso lift (added 2026-09-24)

`lift.py` drives the torso lift (right-arm controller .133, joint 7, mm feedback via
`get_lift_state`, velocity via `set_lift_speed`; +up/-down; hardware ceiling ~1130mm).
`run_stop.py` raises to `LIFT_PRESENT_MM` (1125, near the ceiling) for the presentation and
lowers to `LIFT_DRIVE_MM` (1050) when it ends — for all 4 stops, driven from the console.
`LIFT_ENABLE=0` disables it; any lift error is swallowed so it never breaks a presentation.
Lift only moves while the arms are idle (before/after the gesture), so there is no
controller contention.

```bash
python lift.py read | to <mm> | by <delta_mm>    # manual control (mm)
```
