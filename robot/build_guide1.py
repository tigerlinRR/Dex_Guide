#!/usr/bin/env python3
"""Build Guide1_motion: right-hand wave -> two-arm talk -> left-hand point at ADAM -> return.

Collision-safe: the wave uses only the RIGHT arm (left stays at travel), so the hands
never meet at the centre during "Welcome...". Talk keeps the arms on opposite sides
(left ~ -82 deg, right ~ +94 deg), so it is safe. The point at ADAM uses only the LEFT
arm (right is back at travel). The left-point apex lands at point_at into the narration;
the return starts at return_at, before it ends.

    python build_guide1.py [point_at_s] [return_at_s] [talk_speed]   # 18.0 21.5 0.4
"""
import sys, json
sys.path.insert(0, '/home/rr/teleop/bin')
import numpy as np, motion_recorder as M
import importlib.util
spec = importlib.util.spec_from_file_location('bm', '/home/rr/dex_guide/build_motion.py')
bm = importlib.util.module_from_spec(spec); spec.loader.exec_module(bm)
HZ = 50.0
POINT_AT = float(sys.argv[1]) if len(sys.argv) > 1 else 18.0
RETURN_AT = float(sys.argv[2]) if len(sys.argv) > 2 else 21.5
TALK_SPEED = float(sys.argv[3]) if len(sys.argv) > 3 else 0.4
T_END = 24.0; n_total = int(T_END * HZ)
WIN_IN, WV_OUT, PT_IN, RET = 1.5, 1.0, 1.5, 2.5

Wf, Wd, Wg, arms = bm.trim_smooth('Wave')
Tf, Td, Tg, _ = bm.trim_smooth('Talk')
tp = json.load(open('/home/rr/dex_guide/gestures/travel.json')); travel = {a: np.array(tp[a]) for a in tp}
# the ADAM point is the full two-arm Left gesture (Guide2_out), resampled to 50 Hz
G2tr = M.Recording(json.load(open(M.recording_path('Guide2_out')))).joint_tracks()
Gd = json.load(open(M.recording_path('Guide2_out')))['duration']
G2 = {a: np.column_stack([np.interp(np.arange(0, Gd, 1 / HZ), G2tr[a][0], G2tr[a][1][:, j]) for j in range(7)]) for a in G2tr}

def br(pa, pb, dur):
    n = int(dur * HZ); s = (1 - np.cos(np.linspace(0, np.pi, n))) / 2
    return np.array([pa * (1 - x) + pb * x for x in s])
def hold(p, dur):
    return np.repeat(p[None, :], max(0, int(round(dur * HZ))), axis=0)

# talk playback window so the point apex (Guide2_out end) lands at POINT_AT
TALK_PLAY = max(0.5, POINT_AT - WIN_IN - Wd - WV_OUT - PT_IN - Gd)
Tseg = bm.seg(Tf, Td, TALK_SPEED)
Tseg = {a: Tseg[a][:int(TALK_PLAY * HZ)] for a in Tseg}

# ---- RIGHT: travel -> wave -> talk_right -> point(both-arm) -> hold -> return ----
right = np.concatenate([
    br(travel['right'], Wf['right'][0], WIN_IN), Wf['right'],
    br(Wf['right'][-1], Tseg['right'][0], WV_OUT), Tseg['right'],
    br(Tseg['right'][-1], G2['right'][0], PT_IN), G2['right'],
    hold(G2['right'][-1], RETURN_AT - POINT_AT),
    br(G2['right'][-1], travel['right'], RET),
])
right = np.concatenate([right, hold(travel['right'], (n_total - right.shape[0]) / HZ)])[:n_total]

# ---- LEFT: travel hold (through wave) -> talk_left -> point(both-arm) -> hold -> return ----
left = np.concatenate([
    hold(travel['left'], WIN_IN + Wd),
    br(travel['left'], Tseg['left'][0], WV_OUT), Tseg['left'],
    br(Tseg['left'][-1], G2['left'][0], PT_IN), G2['left'],
    hold(G2['left'][-1], RETURN_AT - POINT_AT),
    br(G2['left'][-1], travel['left'], RET),
])
left = np.concatenate([left, hold(travel['left'], (n_total - left.shape[0]) / HZ)])[:n_total]

n = min(left.shape[0], right.shape[0]); left, right = left[:n], right[:n]
# blend the seams (bridge<->gesture) so the arm never decelerates to a stop at a junction
left = bm.smooth_cols(left, 15)
right = bm.smooth_cols(right, 15)
apex_t = (WIN_IN + Wd + WV_OUT + Tseg['left'].shape[0] / HZ + PT_IN + Gd)
events = []
for i in range(n):
    t = round(i / HZ, 4)
    events.append({'t': t, 'k': 'joints', 'arm': 'left',  'joints': [round(float(v), 4) for v in left[i]]})
    events.append({'t': t, 'k': 'joints', 'arm': 'right', 'joints': [round(float(v), 4) for v in right[i]]})
for gt, close in Wg.get('right', []):
    events.append({'t': round(WIN_IN + gt, 4), 'k': 'gripper', 'arm': 'right', 'close': bool(close)})
tk0 = WIN_IN + Wd + WV_OUT
for a in ('left', 'right'):
    for gt, close in Tg.get(a, []):
        if gt / TALK_SPEED <= TALK_PLAY:
            events.append({'t': round(tk0 + gt / TALK_SPEED, 4), 'k': 'gripper', 'arm': a, 'close': bool(close)})
events.sort(key=lambda e: (e['t'], 0 if e['k'] == 'joints' else 1))

d = {'format': 1, 'name': 'Guide1_motion', 'created': 'g1v6', 'duration': round(n / HZ, 3),
     'arms': arms, 'counts': {}, 'events': events}
d['max_deg_per_tick_1x'] = M.compute_max_deg_per_tick_1x(M.Recording(d).joint_tracks(), d['duration'])
json.dump(d, open(M.recording_path('Guide1_motion'), 'w'))
import shutil; shutil.copy(M.recording_path('Guide1_motion'), '/home/rr/dex_guide/gestures_built/Guide1_motion.json')
print(f"Guide1_motion: dur={n/HZ:.1f}s mdt={d['max_deg_per_tick_1x']:.2f}  "
      f"right-wave -> talk({TALK_SPEED}x,{TALK_PLAY:.1f}s) -> ADAM@{apex_t:.1f}s -> return@{RETURN_AT}s")
