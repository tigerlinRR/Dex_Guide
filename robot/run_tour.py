import subprocess, time, sys
HERE='/home/rr/dex_guide'
order = sys.argv[1:] or ['Guide1','Guide2','Guide3','Guide4']
for st in order:
    print(f"\n===== {st} =====", flush=True)
    subprocess.call(['python', f'{HERE}/run_stop.py', st])
    print(f"----- {st} done (arms at travel pose) -----", flush=True)
    time.sleep(2)   # in the live tour the operator presses Next here
print("\n===== tour complete =====")
