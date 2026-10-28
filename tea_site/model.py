"""One-store exact enumeration. Public controls are location scope, not model knobs."""
import hashlib
import json
import numpy as np
from scipy.spatial import cKDTree
from .geo import xy,lonlat
from .geometry import boundary_mask
from .scope import DISTRICTS
from .insights import site_evidence

DEMAND=['residential','office','school','mall']
RADIUS=1000
GRID=250

def parameters(raw):
    p={'k':1,'radius':RADIUS,'grid':GRID,'spacing':0,'penalty':.15,'weights':{c:1 for c in DEMAND},'include_coffee':raw.get('include_coffee',False) is True}
    p['districts']=raw.get('districts',[])
    if not isinstance(p['districts'],list) or any(not isinstance(v,str) or v not in DISTRICTS for v in p['districts']):raise ValueError('行政区范围格式错误')
    area=raw.get('area')
    if area is not None:
        if not isinstance(area,dict):raise ValueError('选址范围格式错误')
        try:a={k:float(area[k]) for k in ['lon','lat','radius_m']}
        except (KeyError,ValueError,TypeError):raise ValueError('地点范围缺少有效坐标或距离') from None
        if not all(np.isfinite(v) for v in a.values()) or not(122<a['lon']<125 and 40<a['lat']<44 and 500<=a['radius_m']<=10000):raise ValueError('地点范围参数无效，仅支持沈阳九区')
        p['area']=a|{'name':str(area.get('name','指定地点')),'district':str(area.get('district',''))}
        if 'gcj_lon' in area and 'gcj_lat' in area:
            from .collector import valid_area
            p['area']=valid_area(area)
    else:p['area']=None
    p['exclusions']=raw.get('exclusions',[])
    if not isinstance(p['exclusions'],list) or len(p['exclusions'])>100:raise ValueError('排除区域格式错误')
    for e in p['exclusions']:
        if not isinstance(e,dict):raise ValueError('排除区域格式错误')
        for k in ['lon','lat','radius_m']:
            try:e[k]=float(e[k])
            except (KeyError,ValueError,TypeError):raise ValueError('排除区域坐标或半径错误') from None
        if not all(np.isfinite(e[k]) for k in ['lon','lat','radius_m']) or not(122<e['lon']<125 and 40<e['lat']<44 and 50<=e['radius_m']<=5000):raise ValueError('排除区域坐标或半径超出范围')
    return p

def analyze(pois,raw,cancel=lambda:False):
    p=parameters(raw);radius=p['radius'];rows=sorted([r for r in pois if 'review' not in r['categories']],key=lambda r:r['id'])
    known_targets=[r for r in rows if 'target' in r['categories']]
    area=p['area']
    if area:
        center=xy([[area['lon'],area['lat']]])[0]
        rows=[r for r in rows if np.linalg.norm(xy([[r['lon'],r['lat']]])[0]-center)<=area['radius_m']+radius]
    # Keep nearby POIs outside district in the demand buffer, but constrain candidate centres later.
    cats={c:[r for r in rows if c in r['categories']] for c in ['target','competitor','coffee','metro','bus']}
    cats['target']=known_targets  # A known shop outside the requested circle can still serve a nearby facility.
    for cat in DEMAND:cats[cat]=[r for r in rows if next((c for c in DEMAND if c in r['categories']),None)==cat]
    result={'model_version':2,'parameters':p,'plans':[],'cells':[],'counts':{c:len(v) for c,v in cats.items()},'candidate_count':0,'existing_coverage':0,'warnings':['固定1公里是直线评估假设，不是奶茶店实际客流覆盖。','结果只基于当前检索样本；无可用商铺、租金或利润数据。','推荐点是商圈考察参考点，不代表空置商铺；仍需现场确认。'],'status':'no_suitable','reason':'当前范围没有满足规则的候选区域。','input_sha256':hashlib.sha256(json.dumps(sorted(pois,key=lambda r:r['id']),ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'coordinate_note':'源坐标GCJ-02，地图近似WGS84。','qualification_rules':{'min_new_facilities':3,'min_facility_types':2,'near_commercial_m':250,'minimum_score':0}}
    boundaries={k:v for k,v in raw.get('boundaries',{}).items() if k in DISTRICTS}
    result['boundary_sha256']=hashlib.sha256(json.dumps(boundaries,sort_keys=True).encode()).hexdigest()
    if p['districts']:boundaries={k:v for k,v in boundaries.items() if k in p['districts']}
    if not boundaries:
        result.update(status='insufficient_data',reason='缺少所选行政区边界，无法可靠限制选址位置。请先采集边界。');return result
    if p['districts'] and any(d not in boundaries for d in p['districts']):
        result.update(status='insufficient_data',reason='所选范围部分行政区缺少边界，请补采后再评估。');return result
    if area and not boundary_mask(np.array([center]),boundaries)[0]:
        result.update(status='outside_scope',reason='该地点不在支持的沈阳九区范围内，不能用于选址。');return result
    meta=raw.get('collection_meta')
    if meta is not None:
        if meta.get('area') and meta.get('target_buffer_m',1000)<2000:
            result.update(status='insufficient_data',reason='这份附近样本缺少外围本品牌门店证据，请续采补齐后再判断。')
            return result
        relevant=[q for q in meta.get('plan',[]) if q['district']=='nearby' or not p['districts'] or q['district'] in p['districts']]
        pending=[q for q in relevant if q['status'] not in ['ended','capped']]
        required={'target','competitor','residential','office','school','mall','metro','bus'}
        regions=['nearby'] if meta.get('area') else (p['districts'] or list(boundaries))
        missing=[d for d in regions if not required.issubset({q['category'] for q in relevant if q['district']==d})]
        if not relevant or pending or missing or meta.get('source_plan_missing'):
            result.update(status='insufficient_data',reason=f'当前范围的采集计划尚未完成或缺少记录（待续采查询{len(pending)}项、缺少类别的区域{len(missing)}个），请续采后再评估。')
            return result
    demand=[];weights=[];dcats=[]
    for cat in DEMAND:
        for r in cats[cat]:demand.append(r);weights.append(1/len(cats[cat]));dcats.append(cat)
    if len(demand)<3 or len(set(dcats))<2:
        result.update(status='insufficient_data',reason='可用需求设施不足3个或不足2类，无法判断是否适合开店。');return result
    w=np.array(weights);w=w/w.sum()*100;dxy=xy([[r['lon'],r['lat']] for r in demand]);dtree=cKDTree(dxy)
    target=xy([[r['lon'],r['lat']] for r in cats['target']]);existing=cKDTree(target).query(dxy)[0]<=radius if len(target) else np.zeros(len(demand),dtype=bool)
    result['existing_coverage']=float(w[existing].sum())
    commerce=[r for r in rows if any(c in r['categories'] for c in ['competitor','coffee','mall']) and 'target' not in r['categories']]
    if not commerce:result.update(status='insufficient_data',reason='未找到可确认的商业设施作为候选区域依据，请补充周边采集。');return result
    # Each candidate is a 250m commercial grid, not a school/residential centroid.
    cxy=xy([[r['lon'],r['lat']] for r in commerce]);ij=np.unique(np.floor(cxy/GRID).astype(int),axis=0);candidate=(ij+.5)*GRID
    eligible=np.ones(len(candidate),dtype=bool)
    if area:eligible&=np.linalg.norm(candidate-center,axis=1)<=area['radius_m']
    eligible&=boundary_mask(candidate,boundaries)
    for e in p['exclusions']:eligible&=np.linalg.norm(candidate-xy([[e['lon'],e['lat']]])[0],axis=1)>e['radius_m']
    candidate=candidate[eligible];ij=ij[eligible]
    result['candidate_count']=len(candidate)
    if not len(candidate):result['reason']='当前范围没有找到可用的商业设施附近位置。可扩大选址范围或补采数据。';return result
    competition=cats['competitor']+(cats['coffee'] if p['include_coffee'] else [])
    compxy=xy([[r['lon'],r['lat']] for r in competition]);comptree=cKDTree(compxy) if len(compxy) else None
    commercial_tree=cKDTree(cxy);target_tree=cKDTree(target) if len(target) else None
    transport=cats['metro']+cats['bus'];txy=xy([[r['lon'],r['lat']] for r in transport]);ttree=cKDTree(txy) if len(txy) else None
    records=[]
    for j,point in enumerate(candidate):
        if cancel():raise ValueError('计算已取消')
        ids=np.array(dtree.query_ball_point(point,radius),dtype=int);new=ids[~existing[ids]];comps=len(comptree.query_ball_point(point,radius)) if comptree else 0
        nearest,anchor=commercial_tree.query(point)
        counts={c:sum(dcats[i]==c for i in ids) for c in DEMAND};gain=float(w[new].sum())
        lon,lat=lonlat(point)
        records.append({'grid_id':f'{ij[j,0]}:{ij[j,1]}','lon':float(lon),'lat':float(lat),'competitors':comps,'nearest_target_m':float(target_tree.query(point)[0]) if target_tree else None,'local_facilities':counts,'new_facilities':len(new),'facility_types':sum(n>0 for n in counts.values()),'standalone_new_coverage':gain,'local_coverage':float(w[ids].sum()),'overlap':float(w[ids[existing[ids]]].sum()),'nearest_transport_m':float(ttree.query(point)[0]) if ttree else None,'anchor_name':commerce[int(anchor)]['name'],'anchor_district':commerce[int(anchor)].get('district',''),'anchor_distance_m':float(nearest)})
    maxcomp=max(1,max(r['competitors'] for r in records))
    # Scale competition against the maximum incremental benefit in this scope, not whole-city weight units.
    maxgain=max(r['standalone_new_coverage'] for r in records)
    for r in records:
        r['competition_index']=r['competitors']/maxcomp;r['score']=r['standalone_new_coverage']-.15*maxgain*r['competition_index']
        r['qualified']=r['new_facilities']>=3 and r['facility_types']>=2 and r['anchor_distance_m']<=250 and r['score']>1e-9
    qualified=[r for r in records if r['qualified']]
    result['qualified_count']=len(qualified)
    result['candidate_preview']=records
    # Display demand grid weights without a dense candidate x demand matrix.
    grids={}
    for i,point in enumerate(dxy):
        cell=tuple(np.floor(point/GRID).astype(int));g=grids.setdefault(cell,{'weight':0.,'covered_weight':0.,'counts':{c:0 for c in DEMAND}})
        g['weight']+=float(w[i]);g['covered_weight']+=float(w[i]) if existing[i] else 0;g['counts'][dcats[i]]+=1
    for key,g in sorted(grids.items()):
        lon,lat=lonlat((np.array(key)+.5)*GRID);result['cells'].append({'id':f'{key[0]}:{key[1]}','lon':float(lon),'lat':float(lat),'weight':g['weight'],'existing_covered':g['covered_weight']>=g['weight']-1e-8,'counts':g['counts']})
    if not qualified:
        result['reason']='当前样本中，没有找到能兼顾生活配套、补充本品牌现有布局和竞争压力的位置。需要附近至少有3处距本品牌现有店超过1公里的配套、至少2类生活或工作配套，并靠近现有商业设施。不会强行推荐。';return result
    best=max(qualified,key=lambda r:(r['score'],r['standalone_new_coverage'],r['grid_id']))
    chosen=[('optimized',best),('density',max(records,key=lambda r:(r['local_coverage'],r['grid_id'])))]
    if len(target):chosen.append(('distance',max(records,key=lambda r:(r['nearest_target_m'],r['grid_id']))))
    for method,s in chosen:
        result['plans'].append({'method':method,'selected':[s],'qualified':s['qualified'],'new_coverage':s['standalone_new_coverage'],'total_coverage':result['existing_coverage']+s['standalone_new_coverage'],'overlap':s['overlap'],'competition_index':s['competition_index'],'objective':s['score'],'solver_status':0,'optimal':True,'mip_gap':0.0})
    result['explanation']=site_evidence(pois,best,p,raw.get('collection_meta') or {},records)
    result.update(status='recommended',reason='已根据周边配套、本品牌现有布局和竞争情况，选出一个优先考察位置。')
    result['warnings'].append('筛选阈值为软件规则，不是经营业额验证的商业成功标准；样本截断可能改变结论。')
    return result
