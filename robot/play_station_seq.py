#!/usr/bin/env python3
"""Play a stop as a timed sequence of gesture segments cued to the narration.

    python play_station_seq.py <audio.wav> <seg1>@0 <seg2>@<t2> <seg3>@<t3> ...

The first segment starts the narration the instant it begins moving (its @time is
ignored). Each later segment fires when the narration reaches its @time (seconds
from narration start); between fires the arm HOLDS its last pose. Segments split
from one recording at matching poses join seamlessly.

Guide2 (Adam+Scorpion on the left, Dusty on the right):
    play_station_seq.py Guide2.wav Guide2_out@0 Guide2_swing@15.4 Guide2R_ret@22.4
    point left (hold) -> ~15.4s sweep to the right (hold) -> ~22.4s return.
"""
import os, sys, time, subprocess
os.environ.setdefault('REPLAY_MAX_DEG_PER_TICK', '8.0')
os.environ.setdefault('REPLAY_GOTO_V', '25')
sys.path.insert(0, '/home/rr/teleop/bin')
import redis as R
import motion_recorder as M

WONDOM_CARD = 'alsa_card.usb-WONDOM_WONDOM_Audio_20220112-00'

def wondom_sink():
    subprocess.run(['pactl', 'set-card-profile', WONDOM_CARD, 'output:analog-stereo'], stderr=subprocess.DEVNULL)
    out = subprocess.run(['pactl', 'list', 'short', 'sinks'], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if 'wondom' in ln.lower():
            return ln.split()[1]
    return None

def main():
    audio = sys.argv[1]
    segs = [(s.rsplit('@', 1)[0], float(s.rsplit('@', 1)[1])) for s in sys.argv[2:]]
    r = R.Redis(); t0 = time.time()
    ts = lambda m: print(f"[+{time.time()-t0:5.1f}s] {m}", flush=True)

    if any(r.get(f'servo_realman:{a}:error_msg') for a in ('left', 'right')):
        subprocess.run(['python', '/home/rr/teleop/bin/resume_arms.py'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
    sink = wondom_sink()
    if sink:
        for c in (['set-default-sink', sink], ['set-sink-mute', sink, '0'], ['set-sink-volume', sink, '85%']):
            subprocess.run(['pactl'] + c, stderr=subprocess.DEVNULL)
        subprocess.run(['sox', '-n', '-t', 'wav', '/tmp/beep.wav', 'synth', '0.2', 'sine', '660', 'gain', '-6'], stderr=subprocess.DEVNULL)
        subprocess.run(['pw-play', '--target', sink, '/tmp/beep.wav'], stderr=subprocess.DEVNULL)

    # narration starts first; every gesture segment (including the first) fires at its
    # @cue seconds into the narration, so e.g. Guide2_out@1 delays the point by 1s.
    audio_proc = subprocess.Popen(['pw-play', '--target', sink, audio]) if sink else None
    audio_start = time.time()
    alive = lambda: audio_proc is not None and audio_proc.poll() is None
    ts("narration started")

    def resume():
        subprocess.run(['python', '/home/rr/teleop/bin/resume_arms.py'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)

    def bad(detail):
        d = detail or ''
        return 'emergency' in d or 'too much' in d or 'latched' in d or 'failed' in d

    def play_seg(motion, attempt=1):
        # a servo latch ('joint_list change too much' / emergency) is intermittent on the
        # approach; resume and retry so one stop never derails the tour.
        rp = M.MotionReplayer()
        try:
            rp.start(motion, 1.0)
        except Exception as e:
            if attempt <= 2:
                ts(f"{motion} refused ({str(e).splitlines()[-1][:45]}) -> resume+retry"); resume(); return play_seg(motion, attempt + 1)
            ts(f"{motion} FAILED: {e}"); return False
        while rp.active:
            time.sleep(0.03)
        st = rp.status()
        if st['state'] == 'error' or bad(st['detail']):
            if attempt <= 2:
                ts(f"{motion} {st['state']} ({(st['detail'] or '')[:35]}) -> resume+retry"); resume(); return play_seg(motion, attempt + 1)
            ts(f"{motion} FAILED after retry: {st['detail']}"); return False
        ts(f"{motion} {st['state']} - holding"); return True

    for motion, cue in segs:
        while alive() and (time.time() - audio_start) < cue:
            time.sleep(0.03)
        ts(f"cue {cue:.1f}s -> {motion}")
        play_seg(motion)
    if alive():
        audio_proc.wait()
    ts("stop complete")

if __name__ == '__main__':
    main()
