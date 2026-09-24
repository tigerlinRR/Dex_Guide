"""Real-robot adapters — wire into the robot.

**Chassis (RealChassis)**: wired to the AutoXing wrapper API on the Jetson
(http://<host>:3000). This is the only interface directly reachable from a Mac, so
navigation/cancel/state reads all go through it. Verified interface shapes:
  POST /api/moveTo    {x, y, yaw}    navigate to map coords (metres); yaw unit assumed degrees (GUIDE_MOVETO_YAW)
  POST /api/motionFor {direction}    Forward/Back/TurnLeft/TurnRight/Cancel (jog / cancel)
  GET  /api/state     {x,y,yaw,speed,isTasking,...}   used to detect arrival
  GET  /api/poiList   registered POIs (with coordinates)

**Arm (RealArm) / Hand (RealHand)**: need the RealMan SDK (Robotic_Arm) on the Jetson,
runnable only on the robot itself. Reuse Dex_Elevator/core/robot/realman.py and
core/hand/linkerhand.py. NOTE: the arm controller ALSO speaks JSON/TCP on :8080, which
is reachable off-robot — reads work today; motion needs supervised on-site testing.

**Audio (RealAudio)**: the wrapper API has no play endpoint, so the server must run ON
the Jetson and plays the wav straight to the WONDOM PipeWire sink with `paplay`.
Use .wav (paplay/libsndfile on the Jetson may not decode mp3).
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
import urllib.request

from guide.hardware.base import Arm, Audio, Chassis, Hand

_NEEDS_ROBOT_SDK = (
    "Arm/hand need the RealMan SDK (Robotic_Arm) on the Jetson and cannot be reached "
    "directly from a Mac. Wire in Dex_Elevator's realman.py / linkerhand.py, or use the "
    "sim backend for now."
)


def _log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [chassis] {msg}", flush=True)


def _http(method: str, url: str, body: dict | None = None, timeout: float = 8.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, method=method, data=data,
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw else {}


class RealChassis(Chassis):
    """Chassis on the AutoXing wrapper API. navigate_to posts moveTo, then polls state
    to detect arrival."""

    def __init__(self, host: str = "192.168.12.131", port: int = 3000,
                 arrive_tol_m: float = 0.25, poll_s: float = 0.5,
                 stall_s: float = 20.0, hard_cap_s: float = 120.0, settle_s: float = 15.0):
        self.base = f"http://{host}:{port}"
        self.settle_s = settle_s
        self.yaw_unit = os.environ.get("GUIDE_MOVETO_YAW", "deg")
        self.arrive_tol_m = arrive_tol_m
        self.poll_s = poll_s
        self.stall_s = stall_s
        self.hard_cap_s = hard_cap_s

    # -- read-only (safe to call now) --------------------------------------
    async def get_state(self) -> dict:
        d = await asyncio.to_thread(_http, "GET", f"{self.base}/api/state")
        return d.get("state", {})

    async def list_pois(self) -> list[dict]:
        d = await asyncio.to_thread(_http, "GET", f"{self.base}/api/poiList")
        return d.get("poiList", {}).get("list", [])

    async def lookup_poi(self, poi_id: str, name: str | None = None
                         ) -> tuple[float, float, float] | None:
        pois = [p for p in await self.list_pois() if p.get("coordinates")]
        hits = [p for p in pois if p.get("id") == poi_id]
        if not hits and name:
            hits = [p for p in pois if p.get("name") == name]
            if len(hits) == 1:
                _log(f"POI id {poi_id} gone; using {name!r} by name (new id {hits[0]['id']})")
            elif len(hits) > 1:
                _log(f"POI {name!r} is ambiguous ({len(hits)} points share the name)")
                return None
        if not hits:
            return None
        c = hits[0]["coordinates"]
        return float(c[0]), float(c[1]), float(hits[0].get("yaw", 0.0))

    async def health(self) -> dict:
        return await asyncio.to_thread(_http, "GET", f"{self.base}/api/health")

    # -- navigation (MOVES the robot — trigger only on-site, once safe) -----
    async def navigate_to(self, x: float, y: float, ori: float) -> bool:
        # Heading: robot-api forwards `yaw` to the SDK's moveTo. Its unit is assumed DEGREES
        # (the same SDK's goHome takes POI yaw in degrees and docks fine); GUIDE_MOVETO_YAW
        # = deg | rad | off switches it. Each arrival logs target vs actual heading so a
        # wrong unit shows up immediately in the tour log.
        body = {"x": float(x), "y": float(y)}
        target_deg = math.degrees(ori) % 360
        if self.yaw_unit == "deg":
            body["yaw"] = round(target_deg, 2)
        elif self.yaw_unit == "rad":
            body["yaw"] = round(ori, 4)
        await asyncio.to_thread(_http, "POST", f"{self.base}/api/moveTo", body)
        _log(f"moveTo x={x:.3f} y={y:.3f} yaw={body.get('yaw', '-')}({self.yaw_unit}) sent")
        loop = asyncio.get_event_loop()
        t0 = last_move = loop.time()
        last_pos = None
        in_place_since = None
        while True:
            await asyncio.sleep(self.poll_s)
            st = await self.get_state()
            sx, sy = st.get("x"), st.get("y")
            speed = st.get("speed", 0)
            now = loop.time()
            if sx is not None and sy is not None:
                dist = math.hypot(sx - x, sy - y)
                if dist < self.arrive_tol_m and abs(speed) < 1e-3:
                    # in position — but with a heading the base still turns in place at zero
                    # linear speed, so also wait for the task to end (isTasking false),
                    # giving up after settle_s in case the flag never clears
                    in_place_since = in_place_since or now
                    if not st.get("isTasking") or now - in_place_since > self.settle_s:
                        yaw = st.get("yaw")
                        err = ""
                        if yaw is not None:
                            actual_deg = math.degrees(float(yaw)) % 360
                            diff = (actual_deg - target_deg + 180) % 360 - 180
                            err = f" heading actual={actual_deg:.1f}deg target={target_deg:.1f}deg diff={diff:+.1f}deg"
                        _log(f"arrived at ({sx:.3f},{sy:.3f}) dist={dist:.2f}m{err}"
                             + ("" if not st.get("isTasking") else " (isTasking still set)"))
                        return True
                    last_move = now   # turning in place is progress, not a stall
                else:
                    in_place_since = None
                # stall detection: position unchanged for a while and not arrived -> fail
                if last_pos and math.hypot(sx - last_pos[0], sy - last_pos[1]) > 0.01:
                    last_move = now
                last_pos = (sx, sy)
            if now - last_move > self.stall_s or now - t0 > self.hard_cap_s:
                why = "stalled" if now - last_move > self.stall_s else "timed out"
                _log(f"moveTo {why}: at {last_pos} target ({x:.3f},{y:.3f}) "
                     f"errors={st.get('chassisErrors')}")
                await self.cancel()
                return False

    async def go_home(self, x: float, y: float, yaw_deg: float) -> bool:
        # goHome takes the pile's POI values verbatim (yaw in degrees); arrival = charging
        await asyncio.to_thread(_http, "POST", f"{self.base}/api/goHome",
                                {"x": float(x), "y": float(y), "yaw": float(yaw_deg)})
        _log(f"goHome x={x:.3f} y={y:.3f} yaw={yaw_deg}deg sent")
        loop = asyncio.get_event_loop()
        t0 = last_move = loop.time()
        last_pos = None
        while True:
            await asyncio.sleep(self.poll_s)
            st = await self.get_state()
            if st.get("isCharging"):
                _log(f"docked, charging at ({st.get('x')},{st.get('y')})")
                return True
            sx, sy = st.get("x"), st.get("y")
            if sx is not None and sy is not None:
                if last_pos and math.hypot(sx - last_pos[0], sy - last_pos[1]) > 0.01:
                    last_move = loop.time()
                last_pos = (sx, sy)
            now = loop.time()
            # docking backs in slowly, so allow a longer stall than a plain moveTo
            if now - last_move > self.stall_s * 2 or now - t0 > self.hard_cap_s * 2:
                _log(f"goHome gave up: at {last_pos} errors={st.get('chassisErrors')}")
                await self.cancel()
                return False

    async def cancel(self) -> None:
        try:
            await asyncio.to_thread(_http, "POST", f"{self.base}/api/motionFor",
                                    {"direction": "Cancel"})
        except Exception:
            pass  # best-effort cancel; don't raise on a network blip


class RealArm(Arm):
    IPS = {"left": "192.168.12.132", "right": "192.168.12.133"}  # labels; port TBD

    async def go_to_joints(self, side, joints_deg) -> bool:
        raise NotImplementedError(_NEEDS_ROBOT_SDK)

    async def relax(self, side) -> None:
        raise NotImplementedError(_NEEDS_ROBOT_SDK)

    async def stop(self) -> None:
        raise NotImplementedError(_NEEDS_ROBOT_SDK)


class RealHand(Hand):
    async def pose(self, side, name) -> None:
        raise NotImplementedError(_NEEDS_ROBOT_SDK)


WONDOM_SINK = "alsa_output.usb-WONDOM_WONDOM_Audio_20220112-00.analog-stereo"
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RealAudio(Audio):
    """Plays a wav on the robot's built-in speaker via `paplay` (must run on the Jetson,
    as the desktop user so it can reach that user's PipeWire session). play() returns
    when the clip ends; stop() kills it."""

    def __init__(self, sink: str | None = None):
        self.sink = sink or os.environ.get("GUIDE_AUDIO_SINK", WONDOM_SINK)
        self._proc: asyncio.subprocess.Process | None = None

    async def play(self, path: str) -> bool:
        await self.stop()
        full = path if os.path.isabs(path) else os.path.join(_PROJECT_ROOT, path)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"audio file not found: {path}")
        proc = self._proc = await asyncio.create_subprocess_exec(
            "paplay", f"--device={self.sink}", full,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await proc.communicate()
        except asyncio.CancelledError:
            await self.stop()
            raise
        if self._proc is proc:
            self._proc = None
        rc = proc.returncode
        if rc < 0:
            return False            # killed by stop()
        if rc != 0:
            raise RuntimeError(f"paplay failed ({rc}): {err.decode(errors='replace').strip()}")
        return True

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                proc.kill()
