#!/usr/bin/env python3
"""Play one tour stop: gesture motion + narration, kept in lock-step.

    python play_station.py <motion_name> <audio.wav>
    e.g. python play_station.py Guide2_motion /home/rr/dex_guide/audio/Guide2.wav

Flow:
  1. resume any arm left with a stale error_msg (a benign 'not in servo mode' from
     an aborted run blocks the next replay otherwise).
  2. ensure the WONDOM sink exists (its card profile is reset to off across reboots),
     resolve its name live, unmute and set volume - so audio survives a restart.
  3. approach: the replay's goto_joints move brings the arms smoothly from wherever
     they are (the previous stop's end pose) to this motion's first pose. That IS the
     stop-to-stop transition, and it is a trapezoidal movej, i.e. smooth.
  4. start the narration the instant the gesture leaves the approach and begins.
  5. motion longer than audio -> audio ends first, we stop the motion where it is.
     motion shorter -> it finishes and the arms hold while the narration continues.

Runs in the `teleop` conda env; the teleop stack must be up (servo heartbeats).
"""
import os, sys, time, subprocess
os.environ.setdefault('REPLAY_MAX_DEG_PER_TICK', '8.0')   # allow up to 1.0x
os.environ.setdefault('REPLAY_GOTO_V', '25')              # snappy but smooth approach
sys.path.insert(0, '/home/rr/teleop/bin')
import redis as R
import motion_recorder as M

WONDOM_CARD = 'alsa_card.usb-WONDOM_WONDOM_Audio_20220112-00'

def wondom_sink():
    subprocess.run(['pactl', 'set-card-profile', WONDOM_CARD, 'output:analog-stereo'],
                   stderr=subprocess.DEVNULL)
    out = subprocess.run(['pactl', 'list', 'short', 'sinks'], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if 'wondom' in ln.lower():
            return ln.split()[1]
    return None

def main():
    motion = sys.argv[1]; audio = sys.argv[2]
    r = R.Redis(); t0 = time.time()
    ts = lambda m: print(f"[+{time.time()-t0:5.1f}s] {m}", flush=True)

    # 1. clear any stale error_msg so the replay is not refused
    if any(r.get(f'servo_realman:{a}:error_msg') for a in ('left', 'right')):
        subprocess.run(['python', '/home/rr/teleop/bin/resume_arms.py'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)

    # 2. audio device
    sink = wondom_sink()
    if not sink:
        ts("WARNING: WONDOM sink not found - motion will play without audio")
    else:
        subprocess.run(['pactl', 'set-default-sink', sink], stderr=subprocess.DEVNULL)
        subprocess.run(['pactl', 'set-sink-mute', sink, '0'], stderr=subprocess.DEVNULL)
        subprocess.run(['pactl', 'set-sink-volume', sink, '85%'], stderr=subprocess.DEVNULL)
        subprocess.run(['sox', '-n', '-t', 'wav', '/tmp/beep.wav', 'synth', '0.2', 'sine', '660', 'gain', '-6'],
                       stderr=subprocess.DEVNULL)
        subprocess.run(['pw-play', '--target', sink, '/tmp/beep.wav'], stderr=subprocess.DEVNULL)  # wake sink

    audio_proc = None
    alive = lambda: audio_proc is not None and audio_proc.poll() is None

    # 3-5. replay motion, sync + gate on audio
    rp = M.MotionReplayer()
    ts(f"{motion} approach (smooth movej from previous pose)")
    rp.start(motion, 1.0)
    while rp.active:
        st = rp.status()['state']
        if sink and audio_proc is None and st == 'playing':
            audio_proc = subprocess.Popen(['pw-play', '--target', sink, audio])
            ts("narration + gesture synced")
        if audio_proc is not None and not alive():
            rp.stop(); ts("narration ended -> stop motion"); break
        if 'emergency' in (rp.status()['detail'] or ''):
            ts("REAL e-stop: " + rp.status()['detail']); break
        time.sleep(0.04)
    ts(f"motion {rp.status()['state']}")
    if alive():
        audio_proc.wait(); ts("narration ended (motion finished first, arms holding)")
    ts("stop complete")

if __name__ == '__main__':
    main()
