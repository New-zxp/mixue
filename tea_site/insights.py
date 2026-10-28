"""Auditable spatial associations and plain-language site evidence, not sales predictions."""
from collections import Counter
import json
import numpy as np
from scipy.spatial import cKDTree
from .geo import xy

LABELS={'school':'学校','residential':'住宅小区','office':'写字楼','mall':'商场','competitor':'其他茶饮店','coffee':'咖啡店','target':'本品牌门店','metro':'地铁站','bus':'公交站'}
ORDER=list(LABELS)

def clean(pois):
    return sorted((p for p in pois if 'review' not in p['categories']),key=lambda p:p['id'])

def coords(rows):return xy([[p['lon'],p['lat']] for p in rows])

def network_patterns(pois):
    rows=clean(pois);targets=[p for p in rows if 'target' in p['categories']]
    centres=coords(targets);n=len(targets);features=[];vectors={}
    for cat in ORDER:
        if cat=='target':continue
        subset=[p for p in rows if cat in p['categories']]
        counts=cKDTree(coords(subset)).query_ball_point(centres,1000,return_length=True) if subset and n else np.zeros(n,dtype=int)
        vectors[cat]=counts
        features.append({'category':cat,'label':LABELS[cat],'stores_with':int(np.sum(counts>0)),'stores_total':n,'share_pct':float(np.mean(counts>0)*100) if n else None,'median_count':float(np.median(counts)) if n else None})
    mixed=int(np.sum((vectors['school']>0)&(vectors['residential']>0))) if n else 0
    nearest=cKDTree(centres).query(centres,k=2)[0][:,1] if n>1 else []
    return {'radius_m':1000,'stores_total':n,'features':features,'school_residential_stores':mixed,'school_residential_pct':mixed/n*100 if n else None,'median_same_brand_distance_m':float(np.median(nearest)) if len(nearest) else None,'districts':[{'district':d,'stores':count} for d,count in Counter(p.get('district','未标注') for p in targets).most_common()], 'note':'统计当前快照中本品牌每家门店周边1公里的已采集设施；比例分母为本品牌门店数。同一设施可位于多家门店周边。这是分布关联，不证明因果或盈利。'}

def dataset_insights(data):
    pois=data['pois'];review=sum('review' in p['categories'] for p in pois)
    unique_logs={json.dumps({k:v for k,v in q.items() if k!='source_dataset'},sort_keys=True,ensure_ascii=False):q for q in data.get('queries',[])}
    logs=[q for q in unique_logs.values() if q.get('category')!='boundary']
    raw_count=sum(q.get('returned',0) for q in logs)
    return {'dataset':data['id'],'brand':data['meta']['brand'],'created':data['created'],'quality':{'returned_items':raw_count,'unique_pois':len(pois),'review':review,'usable':len(pois)-review,'districts':len({p.get('district','未标注') for p in pois}),'requests':len(unique_logs),'new_requests':data['meta'].get('session_requests',0),'capped':sum(q['status']=='capped' for q in data['meta'].get('plan',[])),'pending':sum(q['status'] in ['pending','active'] for q in data['meta'].get('plan',[]))},'patterns':network_patterns(pois),'scale_note':'展示大数据分析流程：批量采集→按POI ID去重→类别校验→空间索引关联→门店分布统计→位置比较。当前是城市级POI样本，不是海量客流或交易大数据。'}

def site_evidence(pois,selected,parameters,meta,records):
    rows=clean(pois);point=xy([[selected['lon'],selected['lat']]])[0]
    distances=np.linalg.norm(coords(rows)-point,axis=1)
    targets=[p for p in rows if 'target' in p['categories']]
    target_tree=cKDTree(coords(targets)) if targets else None
    nearby={cat:[] for cat in ORDER}
    def describe(p,d):
        cats=p['categories'];item={k:p.get(k,'') for k in ['id','name','address','district','brand','lon','lat','gcj_lon','gcj_lat']}
        item['distance_m']=float(d)
        item['category']=next((c for c in ORDER if c in cats),'review')
        if any(c in cats for c in ['school','residential','office','mall']):
            item['new_to_brand']=target_tree is None or float(target_tree.query(coords([p])[0])[0])>1000
        return item
    for p,d in sorted(zip(rows,distances),key=lambda pair:(pair[1],pair[0]['id'])):
        if d>1000:continue
        # Same category priority as demand allocation in the model (one demand category per POI).
        cat=next((c for c in ['residential','office','school','mall'] if c in p['categories']),None)
        if cat is None:cat=next((c for c in ORDER if c in p['categories']),None)
        if cat:
            item=describe(p,d);item['category']=cat;nearby[cat].append(item)
    nearest_targets=sorted([describe(p,float(np.linalg.norm(coords([p])[0]-point))) for p in targets],key=lambda p:(p['distance_m'],p['id']))[:3]
    patterns=network_patterns(pois)
    comparison=[]
    for feature in patterns['features']:
        cat=feature['category'];comparison.append(feature|{'site_count':len(nearby[cat])})
    def names(cat):return '、'.join(f"{p['name']}（约{p['distance_m']:.0f}米）" for p in nearby[cat][:3])
    reasons=[]
    for cat,title,hint in [('school','周边学校','可供核查学生及教职工消费场景；POI数量不等于学生人数'),('residential','周边住宅','可供核查居民日常消费场景；没有住户数量数据'),('office','办公与工作日消费','可供核查工作日消费场景；没有入驻率数据'),('mall','现有商业配套','说明附近已存在商业设施；不代表存在可租店面')]:
        count=len(nearby[cat])
        reasons.append({'title':title,'text':f"1公里内采到{count}处{LABELS[cat]}。"+(f"包括{names(cat)}。" if count else '当前样本中未找到，不能据此断定现实中没有。')+hint+'。'})
    comp=len(nearby['competitor']);coffee=len(nearby['coffee'])
    reasons.append({'title':'竞争情况与风险','text':f"附近有{comp}家其他茶饮店"+(f"：{names('competitor')}" if comp else '')+f"；另有{coffee}家咖啡店（{'已计入' if parameters['include_coffee'] else '未计入'}竞争评分）。这些店既提示商业活动，也可能争夺顾客，不能简单认为越多越好。"})
    nearest=nearest_targets[0] if nearest_targets else None
    reasons.append({'title':'与本品牌现有门店的关系','text':(f"最近的同品牌门店是{nearest['name']}，直线约{nearest['distance_m']:.0f}米。" if nearest else '样本中没有找到本品牌门店，现有布局证据不足。')+f"本位置附近有{selected['new_facilities']}处学校、住宅、办公或商场，距离样本中所有现有同品牌店均超过1公里，因此可作为补充服务的考察对象；不等于这些地方没有消费者被服务。"})
    transport=sorted(nearby['bus']+nearby['metro'],key=lambda p:p['distance_m'])
    reasons.append({'title':'交通与实地核查','text':(f"最近的交通站点为{transport[0]['name']}，直线约{transport[0]['distance_m']:.0f}米。" if transport else '1公里样本中未找到公交或地铁站。')+'所有距离为直线距离，过街、围墙、出入口和步行时间须现场确认。'})
    comp_counts=[r['competitors'] for r in records]
    comparison_note=f"本次比较{len(records)}个商业设施附近的位置，有{sum(r['qualified'] for r in records)}个满足条件。先要求附近至少有3处距本品牌现有店较远的配套，且周边有至少2类生活或工作配套；再优先考虑补充服务的机会，并扣减竞争较多的位置。这个位置在该规则下排第一。"
    if comp_counts:comparison_note+=f"本位置计入的竞店为{selected['competitors']}家，所有候选位置的中位数为{float(np.median(comp_counts)):g}家。"
    return {'version':1,'headline':f"建议优先考察{selected.get('anchor_district','')}{selected['anchor_name']}附近的商业区域",'selection_reason':comparison_note,'reasons':reasons,'nearby':nearby,'nearest_targets':nearest_targets,'comparisons':comparison,'patterns':patterns,'brand':meta.get('brand','目标品牌'),'source_records':len(pois),'scope_note':'门店规律基于整份当前快照；本位置配套按推荐点1公里统计。范围外数据未采齐和查询截断均可能影响结果。','rules_note':'既有门店统计用于解释与对照，尚未用销量验证或训练盈利模型；本次排名仍来自明确的选址规则。'}
