#!/usr/bin/env python3
"""Pull the robot's registered POIs and generate a guide stations config skeleton.

Read-only: does not move the robot. Exports the chassis's type==11 POIs (tour stops) to
configs/stations.generated.yaml, leaving audio/gesture blank to fill in on-site.

    python3 tools/import_pois.py [--host 192.168.12.131] [--out configs/stations.generated.yaml]
"""
from __future__ import annotations

import argparse
import json
import math
import urllib.request

TOUR_POI_TYPE = 11  # standby=10, charging pile=9, tour stop=11


def fetch_pois(host: str, port: int = 3000) -> list[dict]:
    url = f"http://{host}:{port}/api/poiList"
    with urllib.request.urlopen(url, timeout=8) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return d.get("poiList", {}).get("list", [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="192.168.12.131")
    ap.add_argument("--out", default="configs/stations.generated.yaml")
    ap.add_argument("--type", type=int, default=TOUR_POI_TYPE)
    args = ap.parse_args()

    pois = [p for p in fetch_pois(args.host) if p.get("type") == args.type]
    if not pois:
        print(f"No POIs with type=={args.type} found")
        return 1

    lines = [
        "# Auto-generated from the robot by tools/import_pois.py — real map coordinates.",
        "# Audio/gesture to be filled in on-site (record audio, drag-teach the arm pose).",
        "stations:",
    ]
    for i, p in enumerate(pois, 1):
        c = p["coordinates"]
        ori = round(math.radians(p.get("yaw", 0)), 4)  # yaw degrees -> radians
        lines += [
            f'  - id: "{p["id"]}"',
            f'    order: {i}',
            f'    name: "{p.get("name", "stop")}"',
            f'    chassis_pose: {{x: {c[0]:.4f}, y: {c[1]:.4f}, ori: {ori}}}',
            f'    audio: null            # TODO record on-site',
            f'    # gesture:             # TODO drag-teach the joint angles',
            f'    #   arm: right',
            f'    #   hand_pose: point',
            f'    #   arm_joints_deg: []',
            f'    dwell: manual',
            "",
        ]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {len(pois)} stops -> {args.out}")
    for p in pois:
        print(f"  - {p.get('name')}  {p['coordinates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
