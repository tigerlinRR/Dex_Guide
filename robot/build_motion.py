#!/usr/bin/env python3
"""Build a station's continuous gesture motion from raw teleop recordings.

Pipeline, per source recording (e.g. Wave, Talk):
  1. trim  - drop the leading stillness and trailing settle captured while the
             operator was getting in/out of the pose (motion below a threshold).
  2. smooth - moving-average each joint to kill VR hand-tracking jitter.
Then assemble one continuous stream:
  wave(1.0x) -> cosine bridge -> talk(TALK_SPEED) [-> bridge -> talk ...]
The talk block is repeated until the motion covers COVER seconds (the narration
length plus margin); the player stops it the moment the audio ends, so an
overshoot is only ever trimmed, never heard as silence.

Different per-gesture speeds are baked into ONE recording by time-stretching the
slow gesture's timeline, so the whole thing plays back as a single replay at 1.0x
with no intermediate stop - that is what makes wave->talk seamless.

    python build_motion.py <out_name> <wave_rec> <talk_rec> [talk_speed] [cover_s]
    e.g. python build_motion.py Guide1_motion Wave Talk 0.3 27

Writes ~/teleop/recordings/<out_name>.json (format 1), played by play_station.py.
"""
import sys, json
sys.path.insert(0, '/home/rr/teleop/bin')
import numpy as np
import motion_recorder as M

HZ = 50.0

def smooth_cols(q, win=9):
    if len(q) < win:
        return q
    k = np.ones(win) / win; pad = win // 2; out = np.empty_like(q)
    for j in range(q.shape[1]):
        col = np.pad(q[:, j], pad, mode='edge')
        out[:, j] = np.convolve(col, k, mode='same')[pad:-pad]
    return out

def trim_smooth(name):
    """Return (frames_per_arm@50Hz, duration, gripper_events, arms) after trim+smooth."""
    d = json.load(open(M.recording_path(name))); rec = M.Recording(d)
    tr = rec.joint_tracks(); dur = rec.duration
    ticks = np.arange(0, dur, 1 / HZ)
    spd = np.zeros(len(ticks))
    for arm, (t, q) in tr.items():
        res = np.column_stack([np.interp(ticks, t, q[:, j]) for j in range(q.shape[1])])
        spd[1:] += np.abs(np.diff(res, axis=0)).sum(axis=1)
    spd *= HZ
    thr = max(90, spd.max() * 0.14)
    a = np.where(spd > thr)[0]
    lo = max(0.0, a[0] / HZ - 0.12); hi = min(dur, a[-1] / HZ + 0.12)
    src = np.arange(0, hi - lo, 1 / HZ)
    F = {}
    for arm, (t, q) in tr.items():
        cols = [np.interp(src + lo, t, q[:, j]) for j in range(q.shape[1])]
        F[arm] = smooth_cols(np.column_stack(cols))
    grip = {arm: [(e['t'] - lo, e['close']) for e in d['events']
                  if e['k'] == 'gripper' and e['arm'] == arm and lo <= e['t'] <= hi]
            for arm in tr}
    return F, hi - lo, grip, d['arms']

def seg(F, dur, speed):
    out_t = np.arange(0, dur / speed, 1 / HZ); src_t = out_t * speed
    src = np.arange(0, dur, 1 / HZ)
    return {arm: np.column_stack([np.interp(src_t, src[:F[arm].shape[0]], F[arm][:, j])
                                  for j in range(F[arm].shape[1])]) for arm in F}

def bridge(pa, pb, dur=1.2):
    n = int(dur * HZ); s = (1 - np.cos(np.linspace(0, np.pi, n))) / 2
    return {arm: np.array([pa[arm] * (1 - x) + pb[arm] * x for x in s]) for arm in pa}

def main():
    out_name = sys.argv[1]; wave_rec = sys.argv[2]; talk_rec = sys.argv[3]
    talk_speed = float(sys.argv[4]) if len(sys.argv) > 4 else 0.3
    cover = float(sys.argv[5]) if len(sys.argv) > 5 else 27.0

    Wf, Wd, Wg, arms = trim_smooth(wave_rec)
    if talk_rec == '-':                       # single gesture, played once (no loop/bridge)
        gspeed = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
        W = seg(Wf, Wd, gspeed); n = W['left'].shape[0]
        events = []
        for i in range(n):
            t = round(i / HZ, 4)
            for a in W:
                events.append({'t': t, 'k': 'joints', 'arm': a, 'joints': [round(float(v), 4) for v in W[a][i]]})
        for a in Wg:
            for gt, close in Wg[a]:
                events.append({'t': round(gt / gspeed, 4), 'k': 'gripper', 'arm': a, 'close': bool(close)})
        events.sort(key=lambda e: (e['t'], 0 if e['k'] == 'joints' else 1))
        d = {'format': 1, 'name': out_name, 'created': 'assembled', 'duration': round(n / HZ, 3),
             'arms': arms, 'counts': {}, 'events': events}
        d['max_deg_per_tick_1x'] = M.compute_max_deg_per_tick_1x(M.Recording(d).joint_tracks(), d['duration'])
        json.dump(d, open(M.recording_path(out_name), 'w'))
        print(f"{out_name}: dur={n/HZ:.1f}s  max_deg/tick1x={d['max_deg_per_tick_1x']:.2f}  layout: {wave_rec}({gspeed}x, once)")
        return
    Tf, Td, Tg, _ = trim_smooth(talk_rec)
    W = seg(Wf, Wd, 1.0); T = seg(Tf, Td, talk_speed)
    first = lambda S: {a: S[a][0] for a in S}
    last = lambda S: {a: S[a][-1] for a in S}

    ntalk = 1
    while Wd + 1.2 + ntalk * (Td / talk_speed + 1.2) < cover:
        ntalk += 1

    chain = [W]; end = last(W)
    for _ in range(ntalk):
        chain.append(bridge(end, first(T))); chain.append(T); end = last(T)
    allF = {a: np.concatenate([c[a] for c in chain], axis=0) for a in W}
    n = allF['left'].shape[0]

    events = []
    for i in range(n):
        t = round(i / HZ, 4)
        for a in allF:
            events.append({'t': t, 'k': 'joints', 'arm': a,
                           'joints': [round(float(v), 4) for v in allF[a][i]]})
    # gripper: wave block then each talk block, zero-order hold at real times
    def emit(grip, t0, speed):
        for a in grip:
            for gt, close in grip[a]:
                events.append({'t': round(t0 + gt / speed, 4), 'k': 'gripper', 'arm': a, 'close': bool(close)})
    emit(Wg, 0.0, 1.0); t = Wd
    for _ in range(ntalk):
        t += 1.2; emit(Tg, t, talk_speed); t += Td / talk_speed
    events.sort(key=lambda e: (e['t'], 0 if e['k'] == 'joints' else 1))

    d = {'format': 1, 'name': out_name, 'created': 'assembled', 'duration': round(n / HZ, 3),
         'arms': arms, 'counts': {}, 'events': events}
    d['max_deg_per_tick_1x'] = M.compute_max_deg_per_tick_1x(M.Recording(d).joint_tracks(), d['duration'])
    json.dump(d, open(M.recording_path(out_name), 'w'))
    print(f"{out_name}: dur={n/HZ:.1f}s  max_deg/tick1x={d['max_deg_per_tick_1x']:.2f}  "
          f"layout: wave(1.0x,{Wd:.1f}s) + {ntalk}x[bridge + talk({talk_speed}x,{Td/talk_speed:.1f}s)]")

if __name__ == '__main__':
    main()
