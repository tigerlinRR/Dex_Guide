"""Tour orchestration state machine — chains navigate -> present (audio + gesture
concurrently) -> wait for operator -> next station.

Core product decision: **semi-automatic**. After presenting a stop, the robot stays in
WAITING until the operator presses "Next" in the web console — paced to a salesperson's
conversation with the visitor. It never auto-advances.

States:
  IDLE         standby, not started / finished
  NAVIGATING   base is en route to a stop
  PRESENTING   arrived, playing audio + striking the gesture (both concurrent)
  WAITING      presentation done, stopped and waiting for "Next"
  ESTOP        e-stop, everything halted, must clear before starting again

All hardware calls go through asyncio; only one "action task" runs at a time; an e-stop
cancels it and halts all hardware. State changes are broadcast to the web UI (WebSocket)
via on_change.
"""
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Awaitable, Callable

from guide.config import Station
from guide.hardware.base import Arm, Audio, Chassis, Hand


class State(str, Enum):
    IDLE = "IDLE"
    NAVIGATING = "NAVIGATING"
    PRESENTING = "PRESENTING"
    WAITING = "WAITING"
    ESTOP = "ESTOP"


class TourEngine:
    def __init__(
        self,
        stations: list[Station],
        chassis: Chassis,
        arm: Arm,
        hand: Hand,
        audio: Audio,
        on_change: Callable[[dict], Awaitable[None]] | None = None,
    ):
        self.stations = stations
        self.chassis = chassis
        self.arm = arm
        self.hand = hand
        self.audio = audio
        self._on_change = on_change

        self.state = State.IDLE
        self.current_index: int | None = None   # current / last station
        self.status_text = "Idle"
        self._task: asyncio.Task | None = None   # the action sequence currently running

    # -- outward state snapshot (for the web UI) ---------------------------
    def snapshot(self) -> dict:
        return {
            "state": self.state.value,
            "status_text": self.status_text,
            "current_index": self.current_index,
            "current_station": (
                self.stations[self.current_index].id
                if self.current_index is not None else None
            ),
            "stations": [
                {"id": s.id, "name": s.name, "order": s.order,
                 "has_audio": bool(s.audio),
                 "has_gesture": bool(s.gesture and s.gesture.arm != "none")}
                for s in self.stations
            ],
        }

    async def _emit(self, text: str | None = None) -> None:
        if text is not None:
            self.status_text = text
        if self._on_change:
            await self._on_change(self.snapshot())

    # -- operator commands -------------------------------------------------
    async def start(self) -> None:
        """Start the tour from the first station (or restart after an e-stop)."""
        if self.state in (State.NAVIGATING, State.PRESENTING):
            return  # busy, ignore double-click
        if not self.stations:
            await self._emit("No stations configured — add them in stations.yaml")
            return
        await self._go_to_index(0)

    async def next(self) -> None:
        """Go to the next station. Valid only in WAITING (or IDLE) — pressed by the operator."""
        if self.state not in (State.WAITING, State.IDLE):
            return
        nxt = 0 if self.current_index is None else self.current_index + 1
        if nxt >= len(self.stations):
            self.state = State.IDLE
            self.current_index = None
            await self._emit("Tour complete — this was the last station")
            return
        await self._go_to_index(nxt)

    async def goto(self, station_id: str) -> None:
        """Jump straight to a given station (operator picks a stop)."""
        if self.state in (State.NAVIGATING, State.PRESENTING):
            return
        idx = next((i for i, s in enumerate(self.stations) if s.id == station_id), None)
        if idx is None:
            await self._emit(f"Unknown station: {station_id}")
            return
        await self._go_to_index(idx)

    async def stop_tour(self) -> None:
        """Gently end the tour: cancel the current action, return to IDLE (not an e-stop)."""
        await self._cancel_task()
        await self.chassis.cancel()
        await self.audio.stop()
        self.state = State.IDLE
        await self._emit("Tour stopped")

    async def estop(self) -> None:
        """E-stop: immediately halt the base, arms and audio."""
        await self._cancel_task()
        await asyncio.gather(
            self.chassis.cancel(), self.arm.stop(), self.audio.stop(),
            return_exceptions=True,
        )
        self.state = State.ESTOP
        await self._emit("Emergency stop — press Reset when safe")

    async def clear_estop(self) -> None:
        if self.state == State.ESTOP:
            self.state = State.IDLE
            await self._emit("Reset — idle")

    # -- internal: run one station's full action sequence ------------------
    async def _go_to_index(self, idx: int) -> None:
        await self._cancel_task()
        self._task = asyncio.create_task(self._run_station(idx))

    async def _cancel_task(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _run_station(self, idx: int) -> None:
        station = self.stations[idx]
        try:
            # 1) navigate
            self.state = State.NAVIGATING
            self.current_index = idx
            await self._emit(f"Going to {station.name}")
            p = station.chassis_pose
            ok = await self.chassis.navigate_to(
                float(p["x"]), float(p["y"]), float(p["ori"]))
            if not ok:
                self.state = State.WAITING
                await self._emit(f"Could not reach {station.name} (cancelled or blocked)")
                return

            # 2) present: audio + gesture concurrently
            self.state = State.PRESENTING
            await self._emit(f"Presenting: {station.name}")
            await self._present(station)

            # 3) wait for the operator
            self.state = State.WAITING
            await self._emit(f"Done · at {station.name} · waiting for Next")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a single-station error must not wedge the whole robot
            self.state = State.WAITING
            await self._emit(f"{station.name} error: {exc}")

    async def _present(self, station: Station) -> None:
        jobs = []
        if station.audio:
            jobs.append(self.audio.play(station.audio))
        g = station.gesture
        if g and g.arm != "none":
            jobs.append(self._do_gesture(g))
        if jobs:
            await asyncio.gather(*jobs)

    async def _do_gesture(self, g) -> None:
        sides = ["left", "right"] if g.arm == "both" else [g.arm]
        # set the hand shape first, then move the arm into the pointing pose
        for side in sides:
            await self.hand.pose(side, g.hand_pose)
        if g.arm_joints_deg:
            await asyncio.gather(*[
                self.arm.go_to_joints(side, g.arm_joints_deg) for side in sides])
