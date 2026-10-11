import importlib.util, itertools, math, random, time
sp=importlib.util.spec_from_file_location('m','modul3_calc_prototype.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
p=dict(m.PARAMS); p['c_rate']=1.0
def brute(cb,fi,imp,exp,cap,p):
    q=p['step'];n=int(cap/q);eta=math.sqrt(p['eta_rt']);pmax=p['c_rate']*cap
    kc=max(1,int(pmax*eta/q));kd=max(1,int(pmax/(eta*q)));H=len(cb);best=0.0
    for ks in itertools.product(range(-kd,kc+1),repeat=H):
        e=0;c=0;ok=True
        for h,k in enumerate(ks):
            e+=k
            if e<0 or e>n: ok=False;break
            if k>0:
                bus=k*q/eta;ab=min(exp[h],bus);c+=(bus-ab)*cb[h]+ab*fi[h]
            elif k<0:
                d=-k*q*eta;use=min(d,imp[h]);c+=-use*cb[h]-(d-use)*fi[h]
        if ok and c<best: best=c
    return best
random.seed(1)
for t in range(30):
    H=4;cap=random.choice([2.0,3.0])
    cb=[random.uniform(0.05,0.5) for _ in range(H)];fi=[random.choice([0,0.06]) for _ in range(H)]
    imp=[random.uniform(0,2) for _ in range(H)];exp=[random.choice([0,random.uniform(0,2)]) for _ in range(H)]
    a=m.dp_day(cb,fi,imp,exp,cap,p);b=brute(cb,fi,imp,exp,cap,p)
    assert abs(a-b)<1e-9,(a,b,t)
print("DP == Brute force OK")
