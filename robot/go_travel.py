import os, sys, time, subprocess
os.environ.setdefault('REPLAY_MAX_DEG_PER_TICK','8.0'); os.environ.setdefault('REPLAY_GOTO_V','25')
sys.path.insert(0,'/home/rr/teleop/bin')
import redis as R, motion_recorder as M
r=R.Redis()
if any(r.get(f'servo_realman:{a}:error_msg') for a in ('left','right')):
    subprocess.run(['python','/home/rr/teleop/bin/resume_arms.py'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(1.5)
rp=M.MotionReplayer(); rp.start('Travel',1.0)
while rp.active: time.sleep(0.05)
print('  -> travel pose', rp.status()['state'])
