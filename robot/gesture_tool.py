#!/usr/bin/env python3
"""Hand-guide bimanual gesture recorder/replayer — 50Hz smooth (canfd), DEX RM75.
  home  [side] [speed]     move to HOME/start pose (default both, speed 12)
  record <name> <side>     drag-teach; auto-START on motion, auto-END after 2s still;
                           saved as resampled 50Hz + smoothed (side: left|right|both)
  replay <name> [radio]    reproduce via canfd 50Hz (smooth). default radio 50
  endpose <name> [speed]   just move to recorded END pose(s)
  read  <side>
Saved to ~/dex_guide/gestures/<name>.json
"""
import sys, os, json, time, signal, threading
import numpy as np
from Robotic_Arm.rm_robot_interface import RoboticArm, rm_thread_mode_e
from Robotic_Arm.rm_ctypes_wrap import rm_peripheral_read_write_params_t

IPS = {"left": "192.168.12.132", "right": "192.168.12.133"}
HOME = {"left":  [-19.33, -58.73, 123.59, 83.37, 46.58, 36.04, -81.34],
        "right": [51.50, -45.72, -3.39, -83.40, 40.68, -33.97, -161.25]}
PORT = 8080
DIR = os.path.expanduser("~/dex_guide/gestures"); os.makedirs(DIR, exist_ok=True)
HOME_FILE = os.path.join(DIR, "home.json")
def _load_home():
    if os.path.exists(HOME_FILE):
        try: return json.load(open(HOME_FILE))
        except Exception: pass
    return HOME
MOVE_THRESH = 0.5; STILL_END = 2.0; OUT_HZ = 50; SMOOTH_WIN = 7
_STOP = False
def _sig(*_):
    global _STOP; _STOP = True
signal.signal(signal.SIGTERM, _sig); signal.signal(signal.SIGINT, _sig)

HAND_SLAVE = {"left": 0x28, "right": 0x27}
FIST = [0, 60, 0, 0, 0, 0]; OPENH = [255, 60, 255, 255, 255, 255]
def _hand_on(a):
    a.rm_set_tool_voltage(3); a.rm_set_modbus_mode(1, 115200, 5); time.sleep(0.4)
def _hand_set(a, side, vals):
    sl = HAND_SLAVE[side]
    for i, v in enumerate(vals):
        for _ in range(3):
            if a.rm_write_single_register(rm_peripheral_read_write_params_t(port=1, address=i, device=sl, num=1), int(v)) == 0: break
            time.sleep(0.04)
        time.sleep(0.012)
def _hand_speed(a, side, speed):
    sl = HAND_SLAVE[side]
    for i in range(6):
        for _ in range(3):
            if a.rm_write_single_register(rm_peripheral_read_write_params_t(port=1, address=12 + i, device=sl, num=1), int(speed)) == 0: break
            time.sleep(0.04)
        time.sleep(0.012)

def connect(side):
    a = RoboticArm(rm_thread_mode_e.RM_TRIPLE_MODE_E)
    h = a.rm_create_robot_arm(IPS[side], PORT)
    if h is None or getattr(h, "id", 0) <= 0: raise SystemExit(f"connect FAILED {side}")
    a.rm_clear_system_err(); return a

def _j(a):
    c, j = a.rm_get_joint_degree(); return [float(x) for x in j] if c == 0 and j else None

def _sides(x): return ["left", "right"] if x == "both" else [x]

def home(side="both", speed=12):
    for s in _sides(side):
        a = connect(s); a.rm_movej(_load_home()[s], int(speed), 0, 0, 1)
        _hand_on(a); _hand_set(a, s, FIST); a.rm_delete_robot_arm()
    print("home done (fist at start)")

def _resample_smooth(rows):
    # rows: [(t_abs, [j..])]; -> uniform OUT_HZ grid, linear interp, moving-average smooth
    if len(rows) < 3:
        t0=rows[0][0] if rows else 0
        return [{"t": round(r[0]-t0, 3), "j": [round(x, 3) for x in r[1]]} for r in rows]
    t = np.array([r[0] for r in rows]); t -= t[0]
    J = np.array([r[1] for r in rows])
    grid = np.arange(0.0, float(t[-1]), 1.0 / OUT_HZ)
    out = np.stack([np.interp(grid, t, J[:, k]) for k in range(J.shape[1])], axis=1)
    if len(grid) > SMOOTH_WIN:
        ker = np.ones(SMOOTH_WIN) / SMOOTH_WIN
        pad = SMOOTH_WIN // 2
        for k in range(out.shape[1]):
            padded = np.pad(out[:, k], pad, mode="edge")
            out[:, k] = np.convolve(padded, ker, mode="valid")[:len(grid)]
    return [{"t": round(float(grid[i]), 3), "j": [round(float(x), 3) for x in out[i]]} for i in range(len(grid))]

def record(name, side):
    sides = _sides(side); arms = {s: connect(s) for s in sides}
    for a in arms.values(): a.rm_start_drag_teach(0)
    # settle: wait until arms are STILL for ~1s (avoid triggering on residual home motion)
    print(f"[{name}/{side}] drag-teach ON. Settling...", flush=True)
    prev0={s:None for s in sides}; still_since=None
    while not _STOP:
        now=time.time(); mv=False
        for s,a in arms.items():
            j=_j(a)
            if j and prev0[s] and max(abs(x-y) for x,y in zip(j,prev0[s]))>MOVE_THRESH: mv=True
            prev0[s]=j
        if not mv:
            if still_since is None: still_since=now
            elif now-still_since>1.0: break
        else: still_since=None
        time.sleep(0.01)
    print(f"[{name}/{side}] READY - move the arm(s) now to START recording", flush=True)
    raw = {s: [] for s in sides}; prev = {s: None for s in sides}
    started = False; last_motion = None
    while not _STOP:
        now = time.time(); moved = False; cur = {}
        for s, a in arms.items():
            j = _j(a); cur[s] = j
            if j and prev[s] and max(abs(x - y) for x, y in zip(j, prev[s])) > MOVE_THRESH: moved = True
            prev[s] = j
        if not started:
            if moved:
                started = True; last_motion = now; print(">>> RECORDING", flush=True)
                for s in sides:
                    if cur[s]: raw[s].append((now, cur[s]))
        else:
            for s in sides:
                if cur[s]: raw[s].append((now, cur[s]))
            if moved: last_motion = now
            elif now - last_motion > STILL_END: print(">>> END (2s still)", flush=True); break
        time.sleep(0.008)   # ~poll fast
    for a in arms.values(): a.rm_stop_drag_teach()
    out = {"name": name, "side": side, "hz": OUT_HZ}
    for s in sides:
        rows = [r for r in raw[s] if r[0] <= (last_motion or 0) + 0.001] or raw[s]
        pts = _resample_smooth(rows)
        out[s] = {"n": len(pts), "start": pts[0]["j"] if pts else None,
                  "end": pts[-1]["j"] if pts else None, "points": pts}
    json.dump(out, open(os.path.join(DIR, f"{name}.json"), "w"))
    dur = out[sides[0]]["points"][-1]["t"] if out[sides[0]]["points"] else 0
    print("saved '%s': %s  dur=%.1fs" % (name, ", ".join(f"{s}={out[s]['n']}f" for s in sides), dur))
    for s in sides: print(f"  {s} end: {[round(x,1) for x in out[s]['end']]}")
    for a in arms.values(): a.rm_delete_robot_arm()

def replay(name, radio=80):
    d = json.load(open(os.path.join(DIR, f"{name}.json"))); sides = _sides(d["side"])
    fr = {s: d[s]["points"] for s in sides}
    # which arms actually moved -> only those hands open
    mover = {}
    for s in sides:
        p = fr[s]
        total = sum(max(abs(p[i]["j"][k] - p[i-1]["j"][k]) for k in range(7)) for i in range(1, len(p)))
        mover[s] = total > 20
    arms = {s: connect(s) for s in sides}
    for s, a in arms.items():
        _hand_on(a); _hand_speed(a, s, 200); _hand_set(a, s, FIST)     # fist all to start
    hand_conn = {s: connect(s) for s in sides if mover[s]}             # separate conn for hand (no canfd stall)
    for s, a in hand_conn.items(): _hand_on(a)
    for s, a in arms.items(): a.rm_movej(fr[s][0]["j"], 25, 0, 0, 1)   # to start
    time.sleep(0.5)
    def _open(s):
        a = hand_conn[s]; _hand_speed(a, s, 110); _hand_set(a, s, OPENH)
    n = max(len(fr[s]) for s in sides); t0 = time.time(); opened = False
    for i in range(n):
        ft = fr[sides[0]][min(i, len(fr[sides[0]]) - 1)]["t"]
        while time.time() - t0 < ft: time.sleep(0.001)
        for s, a in arms.items():
            if i < len(fr[s]): a.rm_movej_canfd(fr[s][i]["j"], True, 0, 1, int(radio))
        if not opened and (time.time() - t0) > 0.4:
            for s in hand_conn: threading.Thread(target=_open, args=(s,), daemon=True).start()
            opened = True
    time.sleep(3.0)                                    # hold at end 3s
    for s, a in arms.items():
        if mover[s]: _hand_speed(a, s, 200); _hand_set(a, s, FIST)     # movers close back to fist
    for s, a in arms.items(): a.rm_movej(_load_home()[s], 20, 0, 0, 0) # return home
    time.sleep(4.0)
    for a in list(arms.values()) + list(hand_conn.values()): a.rm_delete_robot_arm()
    print("replay done (movers-only open, threaded, radio80)")

def endpose(name, speed=20):
    d = json.load(open(os.path.join(DIR, f"{name}.json")))
    for s in _sides(d["side"]):
        a = connect(s); a.rm_movej(d[s]["end"], int(speed), 0, 0, 0); a.rm_delete_robot_arm()
    time.sleep(4); print("endpose done")

def teach(side="both"):
    arms = {s: connect(s) for s in _sides(side)}
    for a in arms.values(): a.rm_start_drag_teach(0)
    print("drag-teach ON - position the arms, then run 'sethome'. SIGTERM to release.", flush=True)
    while not _STOP: time.sleep(0.2)
    for a in arms.values(): a.rm_stop_drag_teach()
    print("drag-teach OFF")

def sethome():
    h = {}
    for s in ["left", "right"]:
        a = connect(s); h[s] = [round(x, 3) for x in _j(a)]; a.rm_delete_robot_arm()
    json.dump(h, open(HOME_FILE, "w"))
    print("HOME saved:"); print("  left ", [round(x,1) for x in h["left"]]); print("  right", [round(x,1) for x in h["right"]])

def read(side):
    a = connect(side); print(f"[{side}] {[round(x,1) for x in _j(a)]}"); a.rm_delete_robot_arm()

if __name__ == "__main__":
    A = sys.argv[1:]
    if not A: print(__doc__); sys.exit(0)
    c = A[0]
    if c == "home": home(*(A[1:3]))
    elif c == "record": record(A[1], A[2])
    elif c == "replay": replay(A[1], *(A[2:3]))
    elif c == "endpose": endpose(A[1], *(A[2:3]))
    elif c == "teach": teach(*(A[1:2]))
    elif c == "sethome": sethome()
    elif c == "hand":
        side, pose = A[1], A[2]
        for s in (["left","right"] if side=="both" else [side]):
            a = connect(s); _hand_on(a); _hand_set(a, s, FIST if pose=="fist" else OPENH); a.rm_delete_robot_arm()
        print(f"hand {side} -> {pose}")
    elif c == "read": read(A[1])
    else: print(__doc__)
