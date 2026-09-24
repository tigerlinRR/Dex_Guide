#!/usr/bin/env python3
"""Play one finalized tour stop by name, from stations.yaml.

    conda activate teleop
    python ~/dex_guide/run_stop.py Guide1        # or Guide2 / Guide3 / Guide4
    python ~/dex_guide/run_stop.py --list

Dispatches to play_station.py (continuous) or play_station_seq.py (timed segments)
per the stop's recipe. The teleop stack must be up.

Torso lift: on arrival the platform rises by LIFT_PRESENT_DELTA mm for the presentation
and lowers back to the driving height when it ends. Set LIFT_ENABLE=0 to disable.
Any lift error is swallowed so it can never break the presentation.
"""
import sys, subprocess, yaml, os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, 'stations.yaml')
sys.path.insert(0, HERE)

LIFT_ENABLE = os.environ.get('LIFT_ENABLE', '1') == '1'
LIFT_DRIVE_MM = float(os.environ.get('LIFT_DRIVE_MM', '800'))      # driving / resting height
LIFT_PRESENT_MM = float(os.environ.get('LIFT_PRESENT_MM', '1000'))  # raised for the presentation

def _raise():
    if not LIFT_ENABLE:
        return False
    try:
        import lift
        lift.move_to(LIFT_PRESENT_MM)
        return True
    except Exception as e:
        print(f"lift raise skipped: {e}", flush=True); return False

def _lower(did):
    if not did:
        return
    try:
        import lift
        lift.move_to(LIFT_DRIVE_MM)
    except Exception as e:
        print(f"lift lower skipped: {e}", flush=True)

def _present(s, name):
    if s['type'] == 'continuous':
        rc = subprocess.call(['python', os.path.join(HERE, 'play_station.py'), s['motion'], s['audio']])
        if s.get('travel_after'):
            subprocess.call(['python', os.path.join(HERE, 'go_travel.py')])
        return rc
    if s['type'] == 'seq':
        segs = [f"{seg['motion']}@{seg['cue']}" for seg in s['segments']]
        cmd = ['python', os.path.join(HERE, 'play_station_seq.py'), s['audio']] + segs
        print(f"[{name}] {s['type']}: {' '.join(cmd[2:])}")
        return subprocess.call(cmd)
    print(f"bad type {s['type']!r} for {name}"); return 2

def main():
    cfg = yaml.safe_load(open(CFG))['stations']
    if len(sys.argv) < 2 or sys.argv[1] in ('--list', '-l'):
        print("stops:", ", ".join(cfg))
        return 0
    name = sys.argv[1]
    if name not in cfg:
        print(f"unknown stop {name!r}; known: {', '.join(cfg)}"); return 2
    base = _raise()                       # platform up for the presentation
    try:
        return _present(cfg[name], name)
    finally:
        _lower(base)                      # back to the driving height

if __name__ == '__main__':
    sys.exit(main())
