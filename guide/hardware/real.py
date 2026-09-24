"""Real-robot adapters — wire into the robot.

**Chassis (RealChassis)**: wired to the AutoXing wrapper API on the Jetson
(http://<host>:3000). This is the only interface directly reachable from a Mac, so
navigation/cancel/state reads all go through it. Verified interface shapes:
  POST /api/moveTo    {x, y}         navigate to map coords (metres); heading field TBD on first on-site move
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
import urllib.request

from guide.hardware.base import Arm, Audio, Chassis, Hand

_NEEDS_ROBOT_SDK = (
    "Arm/hand need the RealMan SDK (Robotic_Arm) on the Jetson and cannot be reached "
    "directly from a Mac. Wire in Dex_Elevator's realman.py / linkerhand.py, or use the "
    "sim backend for now."
)


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
                 stall_s: float = 20.0, hard_cap_s: float = 120.0):
        self.base = f"http://{host}:{port}"
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

    async def health(self) -> dict:
        return await asyncio.to_thread(_http, "GET", f"{self.base}/api/health")

    # -- navigation (MOVES the robot — trigger only on-site, once safe) -----
    async def navigate_to(self, x: float, y: float, ori: float) -> bool:
        # NOTE: heading field name/units TBD on first on-site move; send only the
        # verified required x,y for now.
        await asyncio.to_thread(_http, "POST", f"{self.base}/api/moveTo",
                                {"x": float(x), "y": float(y)})
        loop = asyncio.get_event_loop()
        t0 = last_move = loop.time()
        last_pos = None
        while True:
            await asyncio.sleep(self.poll_s)
            st = await self.get_state()
            sx, sy = st.get("x"), st.get("y")
            speed = st.get("speed", 0)
            if sx is not None and sy is not None:
                dist = math.hypot(sx - x, sy - y)
                if dist < self.arrive_tol_m and abs(speed) < 1e-3:
                    return True
                # stall detection: position unchanged for a while and not arrived -> fail
                if last_pos and math.hypot(sx - last_pos[0], sy - last_pos[1]) > 0.01:
                    last_move = loop.time()
                last_pos = (sx, sy)
            now = loop.time()
            if now - last_move > self.stall_s:
                await self.cancel()
                return False
            if now - t0 > self.hard_cap_s:
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
