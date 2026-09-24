#!/usr/bin/env python3
"""Torso lift control for the tour (closed-loop, mm).

The lift hangs off the RIGHT arm controller (192.168.12.133, joint 7). It has real
position feedback (`get_lift_state` -> height mm) and a velocity command
(`set_lift_speed`). Positive speed raises, negative lowers.

    python lift.py read              # print current height (mm)
    python lift.py to <mm>           # go to an absolute height, closed-loop
    python lift.py by <delta_mm>     # raise (+) / lower (-) relative

Safe range clamped to [SAFE_MIN, SAFE_MAX]. Speed capped low for a stationary torso.
"""
import socket, json, sys, time

IP = '192.168.12.133'
SAFE_MIN = int(__import__('os').environ.get('LIFT_MIN_MM', '850'))
SAFE_MAX = int(__import__('os').environ.get('LIFT_MAX_MM', '1160'))
SPEED = int(__import__('os').environ.get('LIFT_SPEED', '30'))   # abs speed while moving

def cmd(c):
    s = socket.create_connection((IP, 8080), timeout=3); s.settimeout(3)
    s.sendall((json.dumps(c) + '\r\n').encode()); b = b''
    while b'\n' not in b:
        chunk = s.recv(1024)
        if not chunk:
            break
        b += chunk
    s.close(); return json.loads(b.decode().strip())

def height():
    return int(cmd({'command': 'get_lift_state'}).get('height', 0))

def set_speed(v):
    return cmd({'command': 'set_lift_speed', 'speed': int(v)})

def move_to(target, tol=4, timeout=15):
    target = max(SAFE_MIN, min(SAFE_MAX, int(target)))
    t0 = time.time(); h = height(); stuck = 0; last = h
    print(f"  lift {h} -> {target} mm", flush=True)
    try:
        while time.time() - t0 < timeout:
            h = height()
            d = target - h
            if abs(d) <= tol:
                break
            # hardware limit / not moving -> stop instead of burning the timeout
            stuck = stuck + 1 if abs(h - last) < 2 else 0
            last = h
            if stuck >= 12:   # ~1s of no progress
                print("  lift not moving (limit reached) - stop", flush=True); break
            set_speed(SPEED if d > 0 else -SPEED)
            time.sleep(0.08)
    finally:
        set_speed(0)
    time.sleep(0.2); h = height()
    print(f"  lift settled at {h} mm", flush=True)
    return h

if __name__ == '__main__':
    a = sys.argv[1] if len(sys.argv) > 1 else 'read'
    if a == 'read':
        print(height())
    elif a == 'to':
        move_to(float(sys.argv[2]))
    elif a == 'by':
        move_to(height() + float(sys.argv[2]))
    else:
        print('usage: lift.py read | to <mm> | by <delta_mm>'); sys.exit(2)
