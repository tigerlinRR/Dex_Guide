"""Hardware abstractions — the tour orchestration depends only on these four
interfaces, never on a concrete robot.

This lets sim (dev machine, no hardware) and the real robot (Jetson) be swapped, and
keeps the orchestration logic (guide/engine.py) fully testable. Style follows
Dex_Elevator/core/robot/base.py.

Four capabilities, each with a minimal interface:
  Chassis  base: navigate to a map pose; can be cancelled (used for e-stop).
  Arm      arm: replay a recorded joint-angle pose (captured via drag-teach).
  Hand     dexterous hand: strike a named gesture (point/open/...).
  Audio    audio: play an audio file; can be stopped.

Every method that physically moves the robot is async — navigation/playback take time,
and the orchestration must run things concurrently (audio while gesturing) and be
interruptible by an e-stop.
"""
from __future__ import annotations

import abc


class Chassis(abc.ABC):
    @abc.abstractmethod
    async def navigate_to(self, x: float, y: float, ori: float) -> bool:
        """Navigate to a map pose (metres, radians). Blocks until arrival, returns success."""

    @abc.abstractmethod
    async def cancel(self) -> None:
        """Immediately cancel the current move (e-stop)."""

    async def lookup_poi(self, poi_id: str, name: str | None = None
                         ) -> tuple[float, float, float] | None:
        """Current (x, y, yaw_deg) of a map POI — by id, else by a unique name (a point
        deleted and re-created in AutoXing gets a new id) — or None if not found. Lets the
        tour follow points re-marked on the robot's map without re-syncing the config."""
        return None

    async def go_home(self, x: float, y: float, yaw_deg: float) -> bool:
        """Drive back to the charging pile at (x, y, yaw in degrees, as the robot's POI list
        reports it) and dock. Blocks until charging, returns success."""
        raise NotImplementedError


class Arm(abc.ABC):
    @abc.abstractmethod
    async def go_to_joints(self, side: str, joints_deg: list[float]) -> bool:
        """Move an arm (left/right) to a recorded joint-angle pose. Returns arrival."""

    @abc.abstractmethod
    async def relax(self, side: str) -> None:
        """Return the arm to a standby/safe pose."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Immediately stop arm motion (e-stop)."""


class Hand(abc.ABC):
    @abc.abstractmethod
    async def pose(self, side: str, name: str) -> None:
        """Strike a named gesture (see Dex_Elevator LinkerHand.POSES: point/open/...)."""


class Audio(abc.ABC):
    @abc.abstractmethod
    async def play(self, path: str) -> bool:
        """Play an audio file, blocking until it finishes. Returns success."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Immediately stop playback (e-stop / skip)."""
