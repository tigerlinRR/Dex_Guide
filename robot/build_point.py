import sys, json
sys.path.insert(0,'/home/rr/teleop/bin')
import numpy as np, motion_recorder as M
HZ=50.0
def apex_pose(name):  # end pose of a *_out gesture = its pointing apex
    d=json.load(open(M.recording_path(name))); tr=M.Recording(d).joint_tracks()
    return {a:q[-1] for a,(t,q) in tr.items()}
def save_bridge(name, pa, pb, dur, arms):
    n=int(dur*HZ); s=(1-np.cos(np.linspace(0,np.pi,n)))/2
    fr={a:np.array([pa[a]*(1-x)+pb[a]*x for x in s]) for a in pa}
    events=[]
    for i in range(n):
        t=round(i/HZ,4)
        for a in fr: events.append({'t':t,'k':'joints','arm':a,'joints':[round(float(v),4) for v in fr[a][i]]})
    events.sort(key=lambda e:e['t'])
    d={'format':1,'name':name,'created':'point','duration':round(n/HZ,3),'arms':arms,'counts':{},'events':events}
    d['max_deg_per_tick_1x']=M.compute_max_deg_per_tick_1x(M.Recording(d).joint_tracks(), d['duration'])
    json.dump(d,open(M.recording_path(name),'w'))
    import shutil; shutil.copy(M.recording_path(name),'/home/rr/dex_guide/gestures_built/%s.json'%name)
    print('%s: dur=%.1fs mdt=%.2f gap=%.0f deg'%(name, n/HZ, d['max_deg_per_tick_1x'], max(float(np.abs(pa[a]-pb[a]).max()) for a in pa)))

tp=json.load(open('/home/rr/dex_guide/gestures/travel.json'))
travel={a:np.array(tp[a]) for a in tp}
arms={'left':'192.168.12.132','right':'192.168.12.133'}
left_apex=apex_pose('Guide2_out')
right_apex=apex_pose('Guide3_out')
save_bridge('Guide2_point', travel, left_apex, 2.0, arms)   # travel -> point LEFT
save_bridge('Guide3_point', travel, right_apex, 2.0, arms)  # travel -> point RIGHT
