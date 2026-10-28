import hashlib
import json
import numpy as np
from scipy.spatial.distance import cdist
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import csr_matrix, hstack, vstack, eye
from .geo import xy,lonlat

DEMAND=['residential','office','school','mall']

def parameters(raw):
    p={k:float(raw.get(k,d)) for k,d in {'grid':500,'radius':800,'spacing':400,'penalty':.15,'k':3}.items()}
    bounds={'grid':(250,2000),'radius':(200,3000),'spacing':(0,3000),'penalty':(0,1),'k':(1,10)}
    for key,(lo,hi) in bounds.items():
        if not np.isfinite(p[key]) or not lo<=p[key]<=hi:raise ValueError(f'{key} 超出范围 {lo}—{hi}')
    if p['k']!=int(p['k']):raise ValueError('新增门店数必须为整数')
    p['k']=int(p['k'])
    p['weights']={cat:float(raw.get('weights',{}).get(cat,1)) for cat in DEMAND}
    if any(not np.isfinite(v) or v<0 or v>10 for v in p['weights'].values()) or sum(p['weights'].values())<=0:raise ValueError('需求权重须为0—10，且至少一个大于0')
    return p

def prepare(pois,p):
    rows=sorted(pois,key=lambda r:r['id'])
    cats={c:[r for r in rows if c in r['categories']] for c in ['target','competitor','metro','bus']}
    for cat in DEMAND:cats[cat]=[r for r in rows if next((c for c in DEMAND if c in r['categories']),None)==cat]
    grid={}
    for cat in DEMAND:
        entries=cats[cat]
        for r,point in zip(entries,xy([[r['lon'],r['lat']] for r in entries])):
            if p['weights'][cat]==0:continue
            ij=tuple(np.floor(point/p['grid']).astype(int))
            cell=grid.setdefault(ij,{'weight':0.,'counts':{c:0 for c in DEMAND}})
            cell['weight']+=p['weights'][cat]/len(entries);cell['counts'][cat]+=1
    if not grid:raise ValueError('缺少有效需求设施数据，请先采集住宅、办公、学校或商场')
    if len(grid)>600:raise ValueError('需求网格超过600，请增大网格或缩小采集范围')
    keys=sorted(grid);coords=np.array([(np.array(ij)+.5)*p['grid'] for ij in keys])
    weights=np.array([grid[ij]['weight'] for ij in keys]);weights=100*weights/weights.sum()
    target=xy([[r['lon'],r['lat']] for r in cats['target']])
    competitors=xy([[r['lon'],r['lat']] for r in cats['competitor'] if 'target' not in r['categories']])
    near=cdist(coords,target).min(axis=1) if len(target) else np.full(len(coords),np.inf)
    existing=near<=p['radius']
    candidate_indices=np.where(near>=p['spacing'])[0]
    if len(candidate_indices)<p['k']:raise ValueError('满足现有门店间距的候选区域不足，请减小新增数量或间距')
    candidate=coords[candidate_indices]
    coverage=cdist(coords,candidate)<=p['radius']
    comp=(cdist(candidate,competitors)<=p['radius']).sum(axis=1) if len(competitors) else np.zeros(len(candidate),dtype=int)
    compnorm=comp/max(1,int(comp.max()))
    conflict=np.argwhere(np.triu(cdist(candidate,candidate)<p['spacing'],1))
    return dict(coords=coords,weights=weights,existing=existing,candidate=candidate,indices=candidate_indices,coverage=coverage,comp=comp,compnorm=compnorm,conflict=conflict,near=near,keys=keys,grid=grid,counts={k:len(v) for k,v in cats.items()},has_target=bool(len(target)))

def solve(problem,p,method='optimized'):
    z=problem;n=len(z['candidate']); active=np.where(~z['existing'])[0];m=len(active)
    c=np.zeros(n+m)
    if method=='optimized':c[:n]=p['penalty']*100/p['k']*z['compnorm'];c[n:]=-z['weights'][active]
    elif method=='density':c[:n]=-(z['coverage']*z['weights'][:,None]).sum(axis=0)
    elif method=='distance':
        if not z['has_target']:return None
        c[:n]=-z['near'][z['indices']]/1000
    constraints=[csr_matrix(([1.]*n,([0]*n,list(range(n)))),shape=(1,n+m))]
    low=[p['k']];high=[p['k']]
    if m:
        constraints.append(hstack([-csr_matrix(z['coverage'][active].astype(float)),eye(m)],format='csr'));low.extend([-np.inf]*m);high.extend([0]*m)
    if len(z['conflict']):
        rows=np.repeat(np.arange(len(z['conflict'])),2);cols=z['conflict'].ravel()
        constraints.append(csr_matrix((np.ones(len(cols)),(rows,cols)),shape=(len(z['conflict']),n+m)))
        low.extend([-np.inf]*len(z['conflict']));high.extend([1]*len(z['conflict']))
    res=milp(c,integrality=np.ones(n+m),bounds=Bounds(0,1),constraints=LinearConstraint(vstack(constraints,format='csr'),low,high),options={'time_limit':15,'mip_rel_gap':.001})
    if res.x is None:raise ValueError('当前数量和间距下无可用方案（不可行或求解超时），请调整参数')
    selection=np.flatnonzero(res.x[:n]>.5)
    if len(selection)!=p['k'] or any(a in selection and b in selection for a,b in z['conflict']):raise ValueError('求解结果未通过约束检查')
    covers=z['coverage'][:,selection];union=covers.any(axis=1);new=union&~z['existing']
    gain=float(z['weights'][new].sum());total=float(z['weights'][union|z['existing']].sum())
    overlap=float(z['weights'][(covers.sum(axis=1)+z['existing'].astype(int))>=2].sum())
    compmean=float(z['compnorm'][selection].mean())
    selected=[]
    for j in selection:
        i=z['indices'][j];lon,lat=lonlat(z['candidate'][j]);ij=z['keys'][i]
        selected.append({'grid_id':f'{ij[0]}:{ij[1]}','lon':float(lon),'lat':float(lat),'competitors':int(z['comp'][j]),'nearest_target_m':float(z['near'][i]) if z['has_target'] else None,'standalone_new_coverage':float(z['weights'][z['coverage'][:,j]&~z['existing']].sum()),'local_facilities':z['grid'][ij]['counts']})
    return {'method':method,'selected':selected,'new_coverage':gain,'total_coverage':total,'overlap':overlap,'competition_index':compmean,'objective':gain-p['penalty']*100*compmean,'solver_status':int(res.status),'optimal':res.status==0,'mip_gap':float(res.mip_gap) if getattr(res,'mip_gap',None) is not None else None}

def analyze(pois,raw):
    p=parameters(raw);z=prepare(pois,p)
    plans=[solve(z,p,method) for method in ['optimized','density','distance']];plans=[s for s in plans if s is not None]
    cells=[]
    for i,(lon,lat) in enumerate(lonlat(z['coords'])):
        ij=z['keys'][i]
        cells.append({'id':f'{ij[0]}:{ij[1]}','lon':float(lon),'lat':float(lat),'weight':float(z['weights'][i]),'existing_covered':bool(z['existing'][i]),'counts':z['grid'][ij]['counts']})
    warnings=['仅依据当前采集样本；关键词遗漏、分页截断和门店状态未核验。','网格中心只是考察区域；土地用途、可租商铺、租金及实际客流未核验。','直线服务半径不是步行可达范围；需求代理权重不是人口或销售额。']
    if not z['has_target']:warnings.append('当前样本没有目标品牌门店，未运行距离基准；现有覆盖视为0。')
    for c in DEMAND:
        if not z['counts'][c]:warnings.append(f'需求类别 {c} 无数据；需求指标只基于其余类别。')
    digest=hashlib.sha256(json.dumps(sorted(pois,key=lambda r:r['id']),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'parameters':p,'plans':plans,'cells':cells,'counts':z['counts'],'candidate_count':len(z['candidate']),'existing_coverage':float(z['weights'][z['existing']].sum()),'warnings':warnings,'input_sha256':digest,'coordinate_note':'源数据GCJ-02；地图为近似WGS84，距离为沈阳局部米制近似。'}
