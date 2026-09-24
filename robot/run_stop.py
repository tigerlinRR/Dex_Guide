#!/usr/bin/env python3
"""Play one finalized tour stop by name, from stations.yaml.

    conda activate teleop
    python ~/dex_guide/run_stop.py Guide1        # or Guide2 / Guide3 / Guide4
    python ~/dex_guide/run_stop.py --list

Dispatches to play_station.py (continuous) or play_station_seq.py (timed segments)
per the stop's recipe. The teleop stack must be up.
"""
import sys, subprocess, yaml, os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, 'stations.yaml')

def main():
    cfg = yaml.safe_load(open(CFG))['stations']
    if len(sys.argv) < 2 or sys.argv[1] in ('--list', '-l'):
        print("stops:", ", ".join(cfg))
        return 0
    name = sys.argv[1]
    if name not in cfg:
        print(f"unknown stop {name!r}; known: {', '.join(cfg)}"); return 2
    s = cfg[name]
    if s['type'] == 'continuous':
        cmd = ['python', os.path.join(HERE, 'play_station.py'), s['motion'], s['audio']]
        rc = subprocess.call(cmd)
        if s.get('travel_after'):
            subprocess.call(['python', os.path.join(HERE, 'go_travel.py')])
        return rc
    elif s['type'] == 'seq':
        segs = [f"{seg['motion']}@{seg['cue']}" for seg in s['segments']]
        cmd = ['python', os.path.join(HERE, 'play_station_seq.py'), s['audio']] + segs
    else:
        print(f"bad type {s['type']!r} for {name}"); return 2
    print(f"[{name}] {s['type']}: {' '.join(cmd[2:])}")
    return subprocess.call(cmd)

if __name__ == '__main__':
    sys.exit(main())
