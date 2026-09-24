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
import math
import time
from enum import Enum
from typing import Awaitable, Callable

from guide.config import Home, Station
from guide.hardware.base import Arm, Audio, Chassis, Hand
from guide.hardware.stop_runner import StopRunner


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
        stop_runner: StopRunner | None = None,
        home: Home | None = None,
    ):
        self.stations = stations
        self.chassis = chassis
        self.arm = arm
        self.hand = hand
        self.audio = audio
        self._on_change = on_change
        self.stop_runner = stop_runner
        self.home = home
        self.returning = False                   # heading to (or failed to reach) the charger
        # True while a run_stop playback may have left the arms out of the travel pose
        # (it was interrupted or failed) — the next drive tucks them first.
        self._arms_out = False

        self.state = State.IDLE
        self.current_index: int | None = None   # current / last station
        self.arrived = False                     # did we actually reach current_index?
        self.presented = False                   # has current_index's presentation started?
        self.status_text = "Idle"
        self._task: asyncio.Task | None = None   # the action sequence currently running

    # -- outward state snapshot (for the web UI) ---------------------------
    def snapshot(self) -> dict:
        return {
            "state": self.state.value,
            "status_text": self.status_text,
            "current_index": self.current_index,
            "arrived": self.arrived,
            "presented": self.presented,
            "returning": self.returning,
            "home": self.home.name if self.home else None,
            "current_station": (
                self.stations[self.current_index].id
                if self.current_index is not None else None
            ),
            "stations": [
                {"id": s.id, "name": s.name, "subtitle": s.subtitle, "order": s.order,
                 "has_audio": bool(s.audio),
                 "has_gesture": bool(s.run_stop or (s.gesture and s.gesture.arm != "none"))}
                for s in self.stations
            ],
        }

    async def _emit(self, text: str | None = None) -> None:
        if text is not None:
            self.status_text = text
            # one timestamped line per state change — the tour's log for later review
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [tour] {self.state.value:<10} "
                  f"stop={self.current_index} {text}", flush=True)
        if self._on_change:
            await self._on_change(self.snapshot())

    # -- operator commands -------------------------------------------------
    async def start(self) -> None:
        """Start the tour: drive to the first stop and stop there WITHOUT presenting — the
        operator then presses Next ("Start Guide1") to present it in place."""
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
        if self.returning:
            await self._start_return()          # retry a return that was paused/failed
            return
        if self.current_index is not None and self.arrived and not self.presented:
            # parked at a stop that waits for the operator (the first one): present it now
            await self._cancel_task()
            self._task = asyncio.create_task(self._present_here(self.stations[self.current_index]))
            return
        if self.current_index is None:
            nxt = 0
        elif not self.arrived:
            nxt = self.current_index   # never reached it (blocked/paused/e-stop) — retry, don't skip
        else:
            nxt = self.current_index + 1
        if nxt >= len(self.stations):
            if self.home:
                await self._start_return()      # after the last stop: back to the charger
                return
            self.state = State.IDLE
            self.current_index = None
            self.arrived = False
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

    async def pause(self) -> None:
        """Halt the current drive/narration but keep the tour position. If we hadn't
        arrived yet, the next Next retries the same stop instead of skipping it."""
        if self.state not in (State.NAVIGATING, State.PRESENTING):
            return
        await self._cancel_task()
        await asyncio.gather(self.chassis.cancel(), self.audio.stop(),
                             return_exceptions=True)
        self.state = State.WAITING
        if self.returning:
            await self._emit("Paused on the way to the charger")
            return
        where = self.stations[self.current_index].name
        await self._emit(f"Paused {'at' if self.arrived else 'before reaching'} {where}")

    async def stop_tour(self) -> None:
        """End the tour: cancel the current action, back to IDLE, position reset (not an e-stop)."""
        await self._cancel_task()
        await asyncio.gather(self.chassis.cancel(), self.audio.stop(),
                             return_exceptions=True)
        self.state = State.IDLE
        self.current_index = None
        self.arrived = False
        self.presented = False
        self.returning = False
        await self._emit("Tour ended")

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
            # keep the tour position so the operator can carry on (Next retries the stop
            # if we were interrupted before arriving)
            self.state = State.IDLE if self.current_index is None else State.WAITING
            await self._emit("Reset — ready")

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
        self.returning = False
        try:
            self.current_index = idx
            # 1) navigate
            self.state = State.NAVIGATING
            self.arrived = False
            self.presented = False
            await self._tuck_if_needed()
            await self._emit(f"Going to {station.name}")
            x, y, ori = await self._station_pose(station)
            ok = await self.chassis.navigate_to(x, y, ori)
            if not ok:
                self.state = State.WAITING
                await self._emit(f"Could not reach {station.name} (cancelled or blocked)")
                return

            self.arrived = True
            if idx == 0:
                # the first stop parks and waits: the operator starts it when the visitor is ready
                self.state = State.WAITING
                await self._emit(f"At {station.name} · press Start when ready")
                return
            await self._present_here(station)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a single-station error must not wedge the whole robot
            self.state = State.WAITING
            await self._emit(f"{station.name} error: {exc}")

    async def _station_pose(self, station: Station) -> tuple[float, float, float]:
        """The stop's pose as the robot's map has it NOW (by POI id), falling back to the
        config copy — so points re-marked in AutoXing take effect without a re-sync."""
        p = station.chassis_pose
        pose = (float(p["x"]), float(p["y"]), float(p["ori"]))
        try:
            live = await self.chassis.lookup_poi(station.id, station.poi_name or station.name)
        except Exception as exc:
            live = None
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [tour] POI lookup failed ({exc}); "
                  f"using config pose for {station.name}", flush=True)
        if not live:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [tour] WARNING {station.name} not found "
                  f"on the map (id {station.id}) — driving to the config pose", flush=True)
        if live:
            x, y, yaw_deg = live
            if math.hypot(x - pose[0], y - pose[1]) > 0.05:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [tour] {station.name}: map POI "
                      f"({x:.3f},{y:.3f}) differs from config ({pose[0]:.3f},{pose[1]:.3f}) "
                      f"— using the map", flush=True)
            pose = (x, y, math.radians(yaw_deg))
        return pose

    async def _tuck_if_needed(self) -> None:
        if self._arms_out and self.stop_runner:
            await self._emit("Tucking arms before driving")
            await self.stop_runner.tuck()
            self._arms_out = False

    async def _start_return(self) -> None:
        await self._cancel_task()
        self._task = asyncio.create_task(self._run_return())

    async def _run_return(self) -> None:
        h = self.home
        self.returning = True
        try:
            self.state = State.NAVIGATING
            await self._tuck_if_needed()
            await self._emit(f"Returning to {h.name}")
            x, y, yaw_deg = h.x, h.y, h.yaw_deg
            if h.poi_id:
                try:
                    x, y, yaw_deg = (await self.chassis.lookup_poi(h.poi_id, h.name)
                                     or (x, y, yaw_deg))
                except Exception:
                    pass        # map unreachable: fall back to the config copy
            ok = await self.chassis.go_home(x, y, yaw_deg)
            if not ok:
                self.state = State.WAITING
                await self._emit(f"Could not dock at {h.name} (cancelled or blocked)")
                return
            self.state = State.IDLE
            self.current_index = None
            self.arrived = False
            self.presented = False
            self.returning = False
            await self._emit(f"Tour complete — docked at {h.name}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state = State.WAITING
            await self._emit(f"Return to charger error: {exc}")

    async def _present_here(self, station: Station) -> None:
        # 2) present: audio + gesture concurrently
        self.state = State.PRESENTING
        self.presented = True
        await self._emit(f"Presenting: {station.name}")
        await self._present(station)
        # 3) wait for the operator
        self.state = State.WAITING
        await self._emit(f"Done · at {station.name} · waiting for Next")

    async def _present(self, station: Station) -> None:
        if station.run_stop and self.stop_runner:
            # the finalized ~/dex_guide playback owns gesture + narration for this stop
            self._arms_out = True
            await self.stop_runner.run(station.run_stop)
            self._arms_out = False
            return
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
