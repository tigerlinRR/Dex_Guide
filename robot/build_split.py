import sys, json
sys.path.insert(0,'/home/rr/teleop/bin')
import numpy as np, motion_recorder as M
HZ=50.0
def smooth_cols(q,win=9):
    if len(q)<win: return q
    k=np.ones(win)/win; pad=win//2; out=np.empty_like(q)
    for j in range(q.shape[1]):
        col=np.pad(q[:,j],pad,mode='edge'); out[:,j]=np.convolve(col,k,mode='same')[pad:-pad]
    return out

d=json.load(open(M.recording_path('Left'))); rec=M.Recording(d); tr=rec.joint_tracks(); dur=rec.duration
ticks=np.arange(0,dur,1/HZ)
F={a: np.column_stack([np.interp(ticks,t,q[:,j]) for j in range(q.shape[1])]) for a,(t,q) in tr.items()}
start={a:F[a][0] for a in F}
dist=np.zeros(len(ticks))
for a in F: dist+=np.abs(F[a]-start[a]).sum(axis=1)
apex=int(np.argmax(dist)); apex_t=apex/HZ
arms=d['arms']

def save_seg(name, i0, i1, trim_head, trim_tail):
    # motion-threshold trim within [i0,i1]
    seg={a:F[a][i0:i1] for a in F}
    spd=np.zeros(i1-i0)
    for a in seg: spd[1:]+=np.abs(np.diff(seg[a],axis=0)).sum(axis=1)
    spd*=HZ; thr=max(70, spd.max()*0.12)
    act=np.where(spd>thr)[0]
    lo=act[0] if (trim_head and len(act)) else 0
    hi=act[-1]+1 if (trim_tail and len(act)) else (i1-i0)
    events=[]
    for k in range(lo,hi):
        t=round((k-lo)/HZ,4)
        for a in seg:
            events.append({'t':t,'k':'joints','arm':a,'joints':[round(float(v),4) for v in smooth_cols(seg[a])[k]]})
    events.sort(key=lambda e:e['t'])
    n=hi-lo
    out={'format':1,'name':name,'created':'split','duration':round(n/HZ,3),'arms':arms,'counts':{},'events':events}
    out['max_deg_per_tick_1x']=M.compute_max_deg_per_tick_1x(M.Recording(out).joint_tracks(), out['duration'])
    json.dump(out, open(M.recording_path(name),'w'))
    print(f"{name}: dur={n/HZ:.1f}s  max_deg/tick1x={out['max_deg_per_tick_1x']:.2f}")
    return {a:smooth_cols(seg[a])[lo] for a in seg}, {a:smooth_cols(seg[a])[hi-1] for a in seg}

print(f"Left apex at {apex_t:.2f}s")
out_s,out_e = save_seg('Guide2_out', 0, apex+1, trim_head=True, trim_tail=False)   # start..apex, keep apex
ret_s,ret_e = save_seg('Guide2_ret', apex, len(ticks), trim_head=False, trim_tail=True) # apex..end
# seam check: out end vs ret start (should be ~0, both = apex)
gap=max(float(np.abs(out_e[a]-ret_s[a]).max()) for a in F)
print(f"apex seam gap (out-end vs ret-start): {gap:.1f} deg  (should be ~0)")
