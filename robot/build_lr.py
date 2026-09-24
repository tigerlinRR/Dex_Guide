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
def frames(name):
    d=json.load(open(M.recording_path(name))); rec=M.Recording(d); tr=rec.joint_tracks(); dur=rec.duration
    ticks=np.arange(0,dur,1/HZ)
    F={a: smooth_cols(np.column_stack([np.interp(ticks,t,q[:,j]) for j in range(q.shape[1])])) for a,(t,q) in tr.items()}
    return F, dur, d['arms']
def save(name, frdict, arms, dur):
    n=frdict['left'].shape[0]; events=[]
    for i in range(n):
        t=round(i/HZ,4)
        for a in frdict: events.append({'t':t,'k':'joints','arm':a,'joints':[round(float(v),4) for v in frdict[a][i]]})
    events.sort(key=lambda e:e['t'])
    out={'format':1,'name':name,'created':'lr','duration':round(n/HZ,3),'arms':arms,'counts':{},'events':events}
    out['max_deg_per_tick_1x']=M.compute_max_deg_per_tick_1x(M.Recording(out).joint_tracks(), out['duration'])
    json.dump(out, open(M.recording_path(name),'w'))
    print(f"{name}: dur={n/HZ:.1f}s  max_deg/tick1x={out['max_deg_per_tick_1x']:.2f}")

# Right split at apex
RF,Rdur,arms = frames('Right')
start={a:RF[a][0] for a in RF}
dist=np.zeros(RF['left'].shape[0])
for a in RF: dist+=np.abs(RF[a]-start[a]).sum(axis=1)
rapex=int(np.argmax(dist)); print('Right apex at %.2fs'%(rapex/HZ))
# right return: apex..end, trim trailing settle
seg={a:RF[a][rapex:] for a in RF}
spd=np.zeros(seg['left'].shape[0])
for a in seg: spd[1:]+=np.abs(np.diff(seg[a],axis=0)).sum(axis=1)
spd*=HZ; act=np.where(spd>max(70,spd.max()*0.12))[0]; hi=(act[-1]+1) if len(act) else seg['left'].shape[0]
save('Guide2R_ret', {a:seg[a][:hi] for a in seg}, arms, None)
right_apex={a:RF[a][rapex] for a in RF}

# left apex = Guide2_out end pose
Ld=json.load(open(M.recording_path('Guide2_out'))); Lrec=M.Recording(Ld); Ltr=Lrec.joint_tracks()
left_apex={a:q[-1] for a,(t,q) in Ltr.items()}

# swing: left_apex -> right_apex, cosine, 1.8s
n=int(1.8*HZ); s=(1-np.cos(np.linspace(0,np.pi,n)))/2
swing={a:np.array([left_apex[a]*(1-x)+right_apex[a]*x for x in s]) for a in RF}
save('Guide2_swing', swing, arms, None)
gap=max(float(np.abs(left_apex[a]-right_apex[a]).max()) for a in RF)
print(f"swing spans left_apex->right_apex, max joint move = {gap:.0f} deg over 1.8s")
