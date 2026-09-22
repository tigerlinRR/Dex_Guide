"""Sim hardware — touches no robot, just records actions and simulates timing.

Lets the whole tour flow run end-to-end on a dev machine: navigation, gestures and
audio all use asyncio.sleep to simulate real durations, and every action is appended
to `history` for assertions/replay. Mirrors Dex_Elevator/core/robot/sim.py.

E-stop semantics: cancel/stop set an interrupt flag; any in-progress sleep exits ASAP.
"""
from __future__ import annotations

import asyncio
import time

from guide.hardware.base import Arm, Audio, Chassis, Hand


def _log(history: list, kind: str, detail: object) -> None:
    history.append((round(time.time(), 3), kind, detail))


async def _interruptible_sleep(seconds: float, flag: "asyncio.Event") -> bool:
    """Sleep for `seconds`, but return False early if `flag` (interrupt) is set."""
    try:
        await asyncio.wait_for(flag.wait(), timeout=seconds)
        return False  # interrupted
    except asyncio.TimeoutError:
        return True   # slept normally


class SimChassis(Chassis):
    def __init__(self, nav_seconds: float = 4.0):
        self.nav_seconds = nav_seconds
        self.pose = (0.0, 0.0, 0.0)
        self.history: list = []
        self._interrupt = asyncio.Event()

    async def navigate_to(self, x: float, y: float, ori: float) -> bool:
        self._interrupt.clear()
        _log(self.history, "navigate_start", (x, y, ori))
        ok = await _interruptible_sleep(self.nav_seconds, self._interrupt)
        if ok:
            self.pose = (x, y, ori)
            _log(self.history, "navigate_done", (x, y, ori))
        else:
            _log(self.history, "navigate_cancelled", (x, y, ori))
        return ok

    async def cancel(self) -> None:
        _log(self.history, "cancel", None)
        self._interrupt.set()


class SimArm(Arm):
    def __init__(self, move_seconds: float = 2.0):
        self.move_seconds = move_seconds
        self.history: list = []
        self._interrupt = asyncio.Event()

    async def go_to_joints(self, side: str, joints_deg: list[float]) -> bool:
        self._interrupt.clear()
        _log(self.history, "arm_move_start", (side, joints_deg))
        ok = await _interruptible_sleep(self.move_seconds, self._interrupt)
        _log(self.history, "arm_move_done" if ok else "arm_move_stopped", side)
        return ok

    async def relax(self, side: str) -> None:
        self._interrupt.clear()
        _log(self.history, "arm_relax_start", side)
        await _interruptible_sleep(self.move_seconds, self._interrupt)
        _log(self.history, "arm_relax_done", side)

    async def stop(self) -> None:
        _log(self.history, "arm_stop", None)
        self._interrupt.set()


class SimHand(Hand):
    def __init__(self, move_seconds: float = 0.8):
        self.move_seconds = move_seconds
        self.history: list = []

    async def pose(self, side: str, name: str) -> None:
        _log(self.history, "hand_pose", (side, name))
        await asyncio.sleep(self.move_seconds)


class SimAudio(Audio):
    """Each clip simulates 6 s by default. On the real robot, replace with real
    file duration / real playback."""

    def __init__(self, default_seconds: float = 6.0):
        self.default_seconds = default_seconds
        self.history: list = []
        self._interrupt = asyncio.Event()

    async def play(self, path: str) -> bool:
        self._interrupt.clear()
        _log(self.history, "audio_play_start", path)
        ok = await _interruptible_sleep(self.default_seconds, self._interrupt)
        _log(self.history, "audio_play_done" if ok else "audio_play_stopped", path)
        return ok

    async def stop(self) -> None:
        _log(self.history, "audio_stop", None)
        self._interrupt.set()
