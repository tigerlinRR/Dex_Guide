# PROGRESS

Dex_Guide progress log (newest first).

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
