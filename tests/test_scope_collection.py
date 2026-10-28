import pytest
from tea_site import collector,storage
from tea_site.geo import gcj_to_wgs

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'test.sqlite3')
    monkeypatch.setattr(collector,'read_key',lambda:'test-secret')
    monkeypatch.setattr(collector.time,'sleep',lambda _:None)

def test_search_excludes_other_cities_and_liaozhong(isolated,monkeypatch):
    monkeypatch.setattr(collector,'api_get',lambda *args:{'pois':[
        {'id':str(i),'name':'同名学校','location':'123.4,41.8','adcode':code}
        for i,code in enumerate(['210102','210113','210111','210115','210411'])]})
    r=collector.search_places('在同名学校附近选址')
    assert [x['id'] for x in r['places']]==['0','1','2']
    assert len(r['outside'])==2

def test_area_outside_boundary_never_calls_poi(isolated,monkeypatch):
    calls=[]
    def fake(key,endpoint,params):
        calls.append(endpoint)
        assert endpoint=='config/district'
        return {'districts':[{'adcode':params['keywords'],'polyline':'123.4,41.8;123.5,41.8;123.5,41.9;123.4,41.9'}]}
    monkeypatch.setattr(collector,'api_get',fake)
    lon,lat=gcj_to_wgs(123.8,41.8)
    did=collector.collect({'area':{'lon':lon,'lat':lat,'gcj_lon':123.8,'gcj_lat':41.8},'budget':50})
    d=storage.get_dataset(did)
    assert d['status']=='failed' and '九区之外' in d['meta']['error']
    assert len(calls)==9 and d['pois']==[]

def test_resume_keeps_parent_immutable(isolated,monkeypatch):
    def fake(key,endpoint,params):
        return {'count':'2','pois':[{'id':params['keywords']+str(params['page']),'name':'学校','type':'科教文化服务;学校;学校','adcode':'210102','location':'123.4,41.8'}]}
    monkeypatch.setattr(collector,'api_get',fake)
    first=collector.collect({'districts':['210102'],'pages':2,'budget':1,'boundaries':False})
    before=storage.get_dataset(first)
    second=collector.collect({'resume':first,'pages':2,'budget':30,'boundaries':False})
    assert storage.get_dataset(first)==before
    after=storage.get_dataset(second)
    assert second!=first and after['meta']['parent']==first
    assert after['status']=='sample_ready' and after['meta']['session_requests']==17
    assert len(after['pois'])>len(before['pois'])

def test_boundary_error_stops_without_extra_requests(isolated,monkeypatch):
    calls=[]
    def fake(*args):
        calls.append(1)
        raise ValueError('quota test')
    monkeypatch.setattr(collector,'api_get',fake)
    d=storage.get_dataset(collector.collect({'budget':100}))
    assert len(calls)==1 and d['status']=='failed'

def test_cancel_keeps_snapshot(isolated):
    d=storage.get_dataset(collector.collect({},cancel=lambda:True))
    assert d['status']=='cancelled' and d['meta']['requests']==0

def test_nearby_target_collection_includes_outer_evidence(isolated,monkeypatch):
    calls=[]
    def fake(key,endpoint,params):
        if endpoint=='config/district':
            return {'districts':[{'adcode':params['keywords'],'polyline':'123.3,41.7;123.5,41.7;123.5,41.9;123.3,41.9'}]}
        calls.append(params)
        return {'count':'0','pois':[]}
    monkeypatch.setattr(collector,'api_get',fake)
    lon,lat=gcj_to_wgs(123.4,41.8)
    d=storage.get_dataset(collector.collect({'area':{'lon':lon,'lat':lat,'gcj_lon':123.4,'gcj_lat':41.8,'radius_m':1000},'budget':50}))
    assert d['status']=='sample_ready' and d['meta']['target_buffer_m']==2000
    assert next(p for p in calls if p['keywords']=='蜜雪冰城')['radius']==3000
    assert next(p for p in calls if p['keywords']=='学校')['radius']==2000


def test_filtered_page_does_not_end_query(isolated,monkeypatch):
    def fake(key,endpoint,params):
        return {'count':'2','pois':[{'id':params['keywords']+str(params['page']),'name':'学校','type':'科教文化服务;学校;学校','adcode':'210411' if params['page']==1 else '210102','location':'123.4,41.8'}]}
    monkeypatch.setattr(collector,'api_get',fake)
    first=collector.collect({'districts':['210102'],'pages':2,'budget':9,'boundaries':False})
    d=storage.get_dataset(first)
    assert d['pois']==[] and all(p['status']=='active' for p in d['meta']['plan'])
    second=collector.collect({'resume':first,'pages':2,'budget':9,'boundaries':False})
    assert len(storage.get_dataset(second)['pois'])==9


def test_clean_and_merge_preserve_exclusions_and_plan(isolated,monkeypatch):
    import json
    monkeypatch.setattr(collector,'api_get',lambda *args:{'count':'0','pois':[]})
    first=collector.collect({'districts':['210102'],'pages':1,'budget':1,'boundaries':False})
    with storage.connect() as c:
        c.execute('INSERT INTO exclusions VALUES(?,?,?)',(first,'excluded',json.dumps({'id':'excluded','lon':123.4,'lat':41.8,'radius_m':300})))
    second=collector.derive([first])
    assert storage.list_exclusions(second)==storage.list_exclusions(first)
    assert storage.get_dataset(second)['meta']['plan']==storage.get_dataset(first)['meta']['plan']
