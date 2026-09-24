"""Load configs/stations.yaml — the tour waypoint definitions.

A station = chassis pose + (optional) narration audio + (optional) arm gesture. The
data model follows Dex_Elevator/configs/stations.yaml (arm_joints_deg + chassis_pose);
the guide adds audio and a hand-pose name on top. Most fields are filled in by on-site
calibration/recording; the code only reads them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


import yaml


@dataclass
class Gesture:
    arm: str = "none"                      # left | right | both | none
    arm_joints_deg: list[float] | None = None   # joint angles recorded via drag-teach
    hand_pose: str = "open"                # LinkerHand preset name: point/open/...


@dataclass
class Station:
    id: str
    order: int
    name: str                              # display name, e.g. "Research Office"
    chassis_pose: dict                     # {x, y, ori}, SLAM map coords
    subtitle: str = ""                     # one-line hint for the operator, e.g. "Demo area"
    audio: str | None = None               # narration file path (relative to project root)
    gesture: Gesture | None = None
    dwell: str = "manual"                  # manual = stop and wait for the operator to press Next
    run_stop: str | None = None            # stop name in ~/dex_guide/stations.yaml; if set, its
                                           # run_stop.py playback replaces audio + gesture here


def _parse_station(raw: dict) -> Station:
    g = raw.get("gesture")
    gesture = None
    if g:
        gesture = Gesture(
            arm=g.get("arm", "none"),
            arm_joints_deg=g.get("arm_joints_deg"),
            hand_pose=g.get("hand_pose", "open"),
        )
    return Station(
        id=raw["id"],
        order=int(raw.get("order", 0)),
        name=raw.get("name", raw["id"]),
        subtitle=raw.get("subtitle", ""),
        chassis_pose=raw["chassis_pose"],
        audio=raw.get("audio"),
        gesture=gesture,
        dwell=raw.get("dwell", "manual"),
        run_stop=raw.get("run_stop"),
    )


@dataclass
class Home:
    name: str
    x: float
    y: float
    yaw_deg: float                         # degrees, as the robot's POI list reports it
    poi_id: str | None = None              # re-read from the map at runtime when set


def load_home(path: str) -> Home | None:
    """The charging pile the tour returns to after the last stop (optional)."""
    with open(path, "r", encoding="utf-8") as f:
        h = (yaml.safe_load(f) or {}).get("home")
    if not h:
        return None
    return Home(name=h.get("name", "Charger"), x=float(h["x"]), y=float(h["y"]),
                yaw_deg=float(h["yaw_deg"]), poi_id=h.get("poi_id"))


def load_stations(path: str) -> list[Station]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    stations = [_parse_station(s) for s in data.get("stations", [])]
    stations.sort(key=lambda s: s.order)
    # ids must be unique: skip-to / go-to a station addresses it by id.
    ids = [s.id for s in stations]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"stations.yaml has duplicate ids: {sorted(dupes)}")
    return stations


DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "configs", "stations.yaml",
)
