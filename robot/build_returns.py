import sys, json
sys.path.insert(0,'/home/rr/teleop/bin')
import numpy as np, motion_recorder as M
HZ=50.0
def apex(name):
    tr=M.Recording(json.load(open(M.recording_path(name)))).joint_tracks()
    return {a:q[-1] for a,(t,q) in tr.items()}
def save(name,pa,pb,dur,arms):
    n=int(dur*HZ); s=(1-np.cos(np.linspace(0,np.pi,n)))/2
    fr={a:np.array([pa[a]*(1-x)+pb[a]*x for x in s]) for a in pa}
    ev=[]
    for i in range(n):
        t=round(i/HZ,4)
        for a in fr: ev.append({'t':t,'k':'joints','arm':a,'joints':[round(float(v),4) for v in fr[a][i]]})
    ev.sort(key=lambda e:e['t'])
    d={'format':1,'name':name,'created':'ret','duration':round(n/HZ,3),'arms':arms,'counts':{},'events':ev}
    d['max_deg_per_tick_1x']=M.compute_max_deg_per_tick_1x(M.Recording(d).joint_tracks(),d['duration'])
    json.dump(d,open(M.recording_path(name),'w'))
    import shutil; shutil.copy(M.recording_path(name),'/home/rr/dex_guide/gestures_built/%s.json'%name)
    print('%s dur=%.1fs mdt=%.2f'%(name,n/HZ,d['max_deg_per_tick_1x']))
tp=json.load(open('/home/rr/dex_guide/gestures/travel.json')); travel={a:np.array(tp[a]) for a in tp}
arms={'left':'192.168.12.132','right':'192.168.12.133'}
save('Ret_from_left', apex('Guide2_out'), travel, 2.2, arms)   # left apex -> travel
save('Ret_from_right', apex('Guide3_out'), travel, 2.2, arms)  # right apex -> travel
