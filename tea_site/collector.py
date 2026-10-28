import json
import time
import uuid
import re
from datetime import datetime
import requests
import yaml
import numpy as np
from . import storage
from .geo import gcj_to_wgs,xy
from .classify import clean_record,VERSION

from .scope import DISTRICTS
from .geometry import boundary_mask
LABELS={'target':'目标品牌','competitor':'确认茶饮','coffee':'咖啡','review':'待核验','residential':'住宅','office':'办公','school':'学校','mall':'商场','metro':'地铁','bus':'公交'}
QUERIES=[('target',None),('competitor','奶茶'),('competitor','茶饮'),('residential','住宅小区'),('office','写字楼'),('school','学校'),('mall','购物中心'),('metro','地铁站'),('bus','公交站')]
def now():return datetime.now().astimezone().isoformat(timespec='seconds')
def integer(v,lo,hi,label):
    if isinstance(v,bool):raise ValueError(label+'必须为整数')
    try:f=float(v)
    except (TypeError,ValueError):raise ValueError(label+'必须为整数') from None
    if not np.isfinite(f) or not f.is_integer() or not lo<=f<=hi:raise ValueError(f'{label}须为{lo}—{hi}的整数')
    return int(f)
def read_key():
    cfg=yaml.safe_load((storage.ROOT/'config.yaml').read_text(encoding='utf-8-sig'))
    key=cfg.get('amap_key') if isinstance(cfg,dict) else None
    if not isinstance(key,str) or not key.strip():raise ValueError('config.yaml缺少有效amap_key')
    return key.strip()
def api_get(key,endpoint,params):
    try:
        r=requests.get('https://restapi.amap.com/v3/'+endpoint,params={'key':key,**params},timeout=(8,25))
        r.raise_for_status();result=r.json()
    except (requests.RequestException,ValueError):raise ValueError('网络或响应格式异常，已保留进度；URL已隐藏') from None
    if not isinstance(result,dict) or str(result.get('status'))!='1':
        code=str(result.get('infocode','unknown')) if isinstance(result,dict) else 'invalid_response'
        raise ValueError(f'高德接口错误码 {code}；已停止，不自动重试或购买额度')
    return result
def in_district(p,district):
    code=p.get('adcode')
    if isinstance(code,(str,int)) and str(code).strip():return str(code)==district
    return p.get('cityname')=='沈阳市' and p.get('adname')==DISTRICTS[district]
def valid_area(area):
    if not isinstance(area,dict):raise ValueError('地点范围格式错误')
    try:result={k:float(area[k]) for k in ['lon','lat','gcj_lon','gcj_lat']}
    except (KeyError,ValueError,TypeError):raise ValueError('地点缺少有效坐标，请重新搜索选择') from None
    if any(not np.isfinite(v) for v in result.values()) or not (122<result['lon']<125 and 40<result['lat']<44):raise ValueError('仅支持沈阳九区内地点')
    converted=gcj_to_wgs(result['gcj_lon'],result['gcj_lat'])
    if max(abs(converted[i]-result[k]) for i,k in enumerate(['lon','lat']))>1e-5:raise ValueError('地点坐标不一致，请重新搜索选择')
    result['radius_m']=integer(area.get('radius_m',3000),500,10000,'选址范围半径')
    result['name']=str(area.get('name','指定地点'))[:100];result['district']=str(area.get('district',''))[:100]
    return result
def search_places(text):
    if not isinstance(text,str) or not text.strip() or len(text)>100:raise ValueError('请输入1—100字的地点')
    word=re.sub(r'^(我想|请|想|我要)?在','',text.strip());word=re.sub(r'(附近|周边).*$', '',word);word=re.sub(r'(选址|开店)$','',word).strip()
    if not word:raise ValueError('请输入具体学校、商场或街道名称')
    r=api_get(read_key(),'place/text',{'keywords':word,'city':'沈阳','citylimit':'false','offset':10,'page':1})
    found=[];outside=[]
    for p in r.get('pois',[]):
        try:
            a,b=map(float,p['location'].split(','));lon,lat=gcj_to_wgs(a,b)
            if not (122<lon<125 and 40<lat<44):continue
            if not any(in_district(p,d) for d in DISTRICTS):
                outside.append({'name':p.get('name',''),'district':str(p.get('cityname',''))+str(p.get('adname',''))});continue
            found.append({'id':p['id'],'name':p['name'],'address':p.get('address') or '', 'district':str(p.get('cityname',''))+str(p.get('adname','')),'lon':lon,'lat':lat,'gcj_lon':a,'gcj_lat':b})
        except (KeyError,TypeError,ValueError):continue
    return {'places':found,'outside':outside,'query':word,'requests':1,'note':'仅支持沈阳九区；九区之外的地点不能用于选址。'}
def initial_plan(districts,brand,area=None):
    return [{'district':d,'category':cat,'keyword':word or brand,'next_page':1,'seen':[],'reported_total':0,'status':'pending'} for cat,word in QUERIES for d in (['nearby'] if area else districts)]
def coverage(meta):
    plans=meta.get('plan',[])
    return {'queries':len(plans),'retrieval_ended':sum(p['status']=='ended' for p in plans),'capped':sum(p['status']=='capped' for p in plans),'pending':sum(p['status'] in ['pending','active'] for p in plans),'unknown_completeness':True}
def collect(options,progress=lambda x:None,cancel=lambda:False):
    budget=integer(options.get('budget',180),1,1000,'本次请求上限');pages=integer(options.get('pages',4),1,8,'查询页数')
    parent=storage.get_dataset(str(options['resume'])) if options.get('resume') else None
    if parent and parent['status']=='running':raise ValueError('快照正在采集，不能同时续采')
    brand=parent['meta']['brand'] if parent else options.get('brand','蜜雪冰城')
    if not isinstance(brand,str) or not brand.strip() or len(brand)>30:raise ValueError('品牌名须为1—30个字符')
    brand=brand.strip();area=valid_area(parent['meta']['area'] if parent else options['area']) if (parent and parent['meta'].get('area')) or (not parent and options.get('area')) else None
    districts=parent['meta']['districts'] if parent else options.get('districts',list(DISTRICTS))
    if not isinstance(districts,list) or (not area and not districts) or any(not isinstance(d,str) or d not in DISTRICTS for d in districts):raise ValueError('请选择有效行政区')
    districts=list(DISTRICTS) if area else list(dict.fromkeys(districts));key=read_key();did=uuid.uuid4().hex[:12]
    merged={p['id']:clean_record(p,brand) for p in parent['pois']} if parent else {}
    plan=json.loads(json.dumps(parent['meta']['plan'])) if parent and parent['meta'].get('plan') else initial_plan(districts,brand,area)
    if area and parent and parent['meta'].get('target_buffer_m',1000)<2000:
        plan=[initial_plan(districts,brand,area)[0] if item['category']=='target' else item for item in plan]
    for item in plan:
        if item['status']=='capped' and item['next_page']<=pages:item['status']='active'
    meta={'target_buffer_m':2000,'brand':brand,'districts':districts,'area':area,'pages':pages,'budget':budget,'requests':parent['meta'].get('requests',0) if parent else 0,'session_requests':0,'rejected':0,'duplicates':0,'sample':True,'classification_version':VERSION,'plan':plan,'boundaries':parent['meta'].get('boundaries',{}) if parent else {},'parent':parent['id'] if parent else None,'note':'按返回类别和名称分类；检索结束不等于在营门店普查。'}
    with storage.connect() as c:
        c.execute('INSERT INTO datasets VALUES(?,?,?,?)',(did,now(),json.dumps(meta,ensure_ascii=False),'running'))
        for p in merged.values():c.execute('INSERT INTO pois VALUES(?,?,?)',(did,p['id'],json.dumps(p,ensure_ascii=False)))
        if parent:
            for e in storage.list_exclusions(parent['id']):c.execute('INSERT INTO exclusions VALUES(?,?,?)',(did,e['id'],json.dumps(e,ensure_ascii=False)))
            for q in parent['queries']:c.execute('INSERT INTO queries VALUES(?,?)',(did,json.dumps(q,ensure_ascii=False)))
    count=0;status='sample_ready';error=None
    def commit():
        meta.update(session_requests=count,unique_records=len(merged),coverage=coverage(meta),error=error)
        storage.save_dataset(did,'running',meta)
    def tick(message):
        nonlocal count
        count+=1;meta['requests']+=1
        progress({'dataset':did,'requests':count,'budget':budget,'message':message});commit()
    try:
        if options.get('boundaries',True):
            for d in districts:
                if d in meta['boundaries']:continue
                if cancel():status='cancelled';break
                if count>=budget:status='budget_stopped';break
                tick(DISTRICTS[d]+' · 获取行政边界');log={'time':now(),'district':d,'category':'boundary','keyword':'行政边界','page':0}
                try:
                    result=api_get(key,'config/district',{'keywords':d,'subdistrict':0,'extensions':'all'})
                    match=next((x for x in result.get('districts',[]) if str(x.get('adcode'))==d),None)
                    if not match or not match.get('polyline'):raise ValueError('接口未返回可用行政边界')
                    rings=[[gcj_to_wgs(*map(float,point.split(','))) for point in ring.split(';') if point] for ring in match['polyline'].split('|')]
                    if not all(len(ring)>=3 for ring in rings):raise ValueError('行政边界坐标无效')
                    meta['boundaries'][d]={'name':DISTRICTS[d],'rings':rings,'source':'AMap district API','time':now()};log['returned']=len(rings)
                except ValueError as exc:log['error']=str(exc)
                with storage.connect() as c:c.execute('INSERT INTO queries VALUES(?,?)',(did,json.dumps(log,ensure_ascii=False)))
                commit()
                if log.get('error'):raise ValueError(log['error'])
        if area and status=='sample_ready':
            if any(d not in meta['boundaries'] for d in DISTRICTS):raise ValueError('缺少九区完整边界，无法验证地点；请补采边界后重试')
            if not boundary_mask(xy([[area['lon'],area['lat']]]),meta['boundaries'])[0]:raise ValueError('该地点在沈阳九区之外，不允许采集或选址')
        while status=='sample_ready':
            pending=[p for p in plan if p['status'] in ['pending','active']]
            if not pending:break
            item=min(pending,key=lambda p:p['next_page'])
            if item['next_page']>pages:item['status']='capped';continue
            if cancel():status='cancelled';break
            if count>=budget:status='budget_stopped';break
            d=item['district'];page=item['next_page'];tick(f"{area['name'] if area else DISTRICTS[d]} · {item['keyword']} · 第{page}页")
            log={'time':now(),'district':d,'category':item['category'],'keyword':item['keyword'],'page':page}
            try:
                params={'keywords':item['keyword'],'offset':25,'page':page,'extensions':'base','output':'JSON'}
                if area:params.update(location=f"{area['gcj_lon']},{area['gcj_lat']}",radius=area['radius_m']+(2000 if item['category']=='target' else 1000),sortrule='distance');endpoint='place/around'
                else:params.update(city=d,citylimit='true');endpoint='place/text'
                result=api_get(key,endpoint,params);pois=result.get('pois',[])
                if not isinstance(pois,list):raise ValueError('接口POI格式异常')
                reported=int(result.get('count',0));item['reported_total']=max(item['reported_total'],reported)
                oldseen=set(item['seen']);seen=set(oldseen)
                oldraw=set(item.get('raw_seen',item['seen']));rawseen=oldraw|{str(r['id']) for r in pois if isinstance(r,dict) and r.get('id')}
                for raw in pois:
                    try:
                        lon,lat=map(float,raw.get('location','').split(','))
                        allowed=any(in_district(raw,z) for z in DISTRICTS) if area else in_district(raw,d)
                        if not allowed or not (122<lon<125 and 40<lat<44) or not raw.get('id'):raise ValueError()
                    except (ValueError,TypeError,AttributeError):meta['rejected']+=1;continue
                    pid=raw['id'];seen.add(pid);wlon,wlat=gcj_to_wgs(lon,lat)
                    hit=f"{d}:{item['category']}:{item['keyword']}";hits=list(merged.get(pid,{}).get('query_hits',[]))
                    if hit not in hits:hits.append(hit)
                    if pid in merged:meta['duplicates']+=1
                    record={'id':pid,'name':raw.get('name',''),'address':raw.get('address') or '', 'district':str(raw.get('adname') or (DISTRICTS.get(d,''))),'adcode':str(raw.get('adcode') or (d if not area else '')),'type':raw.get('type',''),'typecode':raw.get('typecode',''),'gcj_lon':lon,'gcj_lat':lat,'lon':wlon,'lat':wlat,'query_hits':hits}
                    merged[pid]=clean_record(record,brand)
                item['seen']=sorted(seen);item['raw_seen']=sorted(rawseen);item['next_page']=page+1
                item['status']='ended' if not pois or not(rawseen-oldraw) else ('capped' if page>=pages else 'active')
                item['end_reason']='empty_page' if not pois else 'no_new_ids' if not(rawseen-oldraw) else 'page_cap' if page>=pages else ''
                log.update(reported_total=reported,returned=len(pois),unique_in_query=len(seen),possibly_truncated=item['status']=='capped' or len(seen)<item['reported_total'])
                with storage.connect() as c:
                    c.execute('INSERT INTO queries VALUES(?,?)',(did,json.dumps(log,ensure_ascii=False)))
                    for p in merged.values():c.execute('INSERT OR REPLACE INTO pois VALUES(?,?,?)',(did,p['id'],json.dumps(p,ensure_ascii=False)))
                commit();time.sleep(.2)
            except (ValueError,TypeError) as exc:
                log['error']=str(exc)
                with storage.connect() as c:c.execute('INSERT INTO queries VALUES(?,?)',(did,json.dumps(log,ensure_ascii=False)))
                raise ValueError(str(exc)) from None
    except Exception as exc:status='failed';error=str(exc) if isinstance(exc,ValueError) else '采集中断，进度已保存'
    if cancel() and status=='sample_ready':status='cancelled'
    meta.update(session_requests=count,unique_records=len(merged),coverage=coverage(meta),error=error)
    storage.save_dataset(did,status,meta)
    progress({'dataset':did,'requests':count,'budget':budget,'message':error or f'{status}：{len(merged)}条记录'})
    return did

def derive(ids):
    if not isinstance(ids,list) or not 1<=len(ids)<=20:raise ValueError('请选择1—20个快照')
    sources=[storage.get_dataset(str(i)) for i in dict.fromkeys(ids)]
    if any(d['status']=='running' for d in sources):raise ValueError('不能合并正在采集的数据')
    brand=sources[0]['meta']['brand']
    if any(d['meta']['brand']!=brand for d in sources):raise ValueError('只能合并相同目标品牌')
    areas=[s['meta'].get('area') for s in sources]
    if any(a!=areas[0] for a in areas):raise ValueError('地点范围不同，不能直接合并；请选择相同范围')
    sources.sort(key=lambda d:d['created']);rows={};boundaries={};districts=set()
    for source in sources:
        boundaries.update(source['meta'].get('boundaries',{}));districts.update(source['meta']['districts'])
        for p in source['pois']:rows[p['id']]=clean_record(p,brand)
    plans={}
    exclusions={}
    for source in sources:
        for item in source['meta'].get('plan',[]):
            key=(item['district'],item['category'],item['keyword'])
            if key not in plans or item['next_page']>plans[key]['next_page']:plans[key]=item
        for e in storage.list_exclusions(source['id']):exclusions[(e['lon'],e['lat'],e['radius_m'])]=e
    did=uuid.uuid4().hex[:12];meta={'target_buffer_m':min(s['meta'].get('target_buffer_m',1000) for s in sources),'plan':list(plans.values()),'source_plan_missing':any(not s['meta'].get('plan') or s['meta'].get('source_plan_missing') for s in sources),'brand':brand,'districts':sorted(districts),'area':areas[0],'parents':[s['id'] for s in sources],'boundaries':boundaries,'classification_version':VERSION,'unique_records':len(rows),'sample':True,'requests':0,'session_requests':0,'note':'本地清洗合并派生快照；原数据保留，合并不等于普查。'}
    with storage.connect() as c:
        c.execute('INSERT INTO datasets VALUES(?,?,?,?)',(did,now(),json.dumps(meta,ensure_ascii=False),'derived'))
        for e in exclusions.values():c.execute('INSERT OR IGNORE INTO exclusions VALUES(?,?,?)',(did,e['id'],json.dumps(e,ensure_ascii=False)))
        for p in rows.values():c.execute('INSERT INTO pois VALUES(?,?,?)',(did,p['id'],json.dumps(p,ensure_ascii=False)))
        for source in sources:
            for q in source['queries']:c.execute('INSERT INTO queries VALUES(?,?)',(did,json.dumps(q|{'source_dataset':source['id']},ensure_ascii=False)))
    return did
