"""Stop runner — hands a whole stop's presentation (gesture + narration) to the
finalized playback scripts in ~/dex_guide on the Jetson.

The console never drives the arms itself. It only decides WHEN to call:
  run(name)  -> `run_stop.py <name>`  (plays that stop's recipe from ~/dex_guide/stations.yaml)
  tuck()     -> `go_travel.py`        (arms back to the travel pose)
and kills the whole process group when the operator pauses / e-stops / ends the tour.
Both scripts need the teleop stack up (dex-teleop.service starts it on boot).
"""
from __future__ import annotations

import asyncio
import os
import signal

TELEOP_PY = os.environ.get("GUIDE_TELEOP_PY", "/home/rr/miniconda3/envs/teleop/bin/python")
PLAYBACK_DIR = os.environ.get("GUIDE_PLAYBACK_DIR", "/home/rr/dex_guide")


class StopRunner:
    async def run(self, name: str) -> None:
        raise NotImplementedError

    async def tuck(self) -> None:
        raise NotImplementedError


class RealStopRunner(StopRunner):
    async def run(self, name: str) -> None:
        await self._exec(os.path.join(PLAYBACK_DIR, "run_stop.py"), name)

    async def tuck(self) -> None:
        await self._exec(os.path.join(PLAYBACK_DIR, "go_travel.py"))

    async def _exec(self, script: str, *args: str) -> None:
        env = dict(os.environ)
        # the scripts spawn children as plain `python`, which must be the teleop env's
        env["PATH"] = os.path.dirname(TELEOP_PY) + os.pathsep + env.get("PATH", "")
        # own process group, so a cancel kills run_stop.py AND its player/pw-play children
        proc = await asyncio.create_subprocess_exec(
            TELEOP_PY, script, *args, env=env, cwd=PLAYBACK_DIR, start_new_session=True)
        try:
            rc = await proc.wait()
        except asyncio.CancelledError:
            await _kill_group(proc)
            raise
        if rc != 0:
            raise RuntimeError(f"{os.path.basename(script)} {' '.join(args)} exited {rc}")


async def _kill_group(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        await asyncio.wait_for(proc.wait(), timeout=2)
    except asyncio.TimeoutError:
        os.killpg(proc.pid, signal.SIGKILL)
        await proc.wait()
    except ProcessLookupError:
        pass


class SimStopRunner(StopRunner):
    """Dev-machine stand-in: just takes time, touches nothing."""

    def __init__(self, run_seconds: float = 6.0, tuck_seconds: float = 2.0):
        self.run_seconds = run_seconds
        self.tuck_seconds = tuck_seconds
        self.history: list = []

    async def run(self, name: str) -> None:
        self.history.append(("run", name))
        await asyncio.sleep(self.run_seconds)

    async def tuck(self) -> None:
        self.history.append(("tuck", None))
        await asyncio.sleep(self.tuck_seconds)
