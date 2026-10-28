import numpy as np
import pytest
from tea_site.insights import network_patterns,site_evidence,dataset_insights
from tea_site.geo import xy
from tests.test_model import sample,run

def test_network_percentages_use_store_denominator():
    rows=[{'id':'t1','name':'A','categories':['target'],'lon':123.4,'lat':41.8},
          {'id':'t2','name':'B','categories':['target'],'lon':123.5,'lat':41.8},
          {'id':'s','name':'school','categories':['school'],'lon':123.401,'lat':41.8},
          {'id':'r','name':'home','categories':['residential'],'lon':123.401,'lat':41.8},
          {'id':'x','name':'unknown','categories':['review','school'],'lon':123.501,'lat':41.8}]
    p=network_patterns(rows)
    s=next(x for x in p['features'] if x['category']=='school')
    assert s['stores_with']==1 and s['stores_total']==2
    assert s['share_pct']==50 and s['median_count']==.5
    assert p['school_residential_stores']==1 and p['school_residential_pct']==50

def test_evidence_names_distances_and_counts_trace_to_source():
    rows=sample();r=run(rows);point=r['plans'][0]['selected'][0];e=r['explanation']
    ids={p['id']:p for p in rows};center=xy([[point['lon'],point['lat']]])[0]
    for cat,items in e['nearby'].items():
        for item in items:
            source=ids[item['id']]
            assert item['name']==source['name']
            distance=float(np.linalg.norm(xy([[source['lon'],source['lat']]])[0]-center))
            assert distance<=1000 and item['distance_m']==pytest.approx(distance)
        if cat in point['local_facilities']:assert len(items)==point['local_facilities'][cat]
    assert sum(p.get('new_to_brand',False) for items in e['nearby'].values() for p in items)==point['new_facilities']
    assert len(e['nearby']['competitor'])==point['competitors']
    assert e['patterns']['stores_total']==1

def test_no_targets_does_not_invent_network_pattern():
    p=network_patterns([])
    assert p['stores_total']==0 and p['school_residential_pct'] is None
    assert all(x['share_pct'] is None for x in p['features'])

def test_no_recommendation_has_no_invented_evidence():
    r=run([])
    assert r['status']=='insufficient_data' and 'explanation' not in r

def test_pipeline_counts_raw_and_review_separately():
    data={'id':'test','created':'2026-10-26','pois':sample()+[{'id':'unknown','categories':['review']}],
          'meta':{'brand':'test','districts':['210102'],'requests':3},
          'queries':[{'category':'boundary','returned':1},{'category':'school','returned':25},{'category':'mall','returned':25}]}
    r=dataset_insights(data)
    assert r['quality']['returned_items']==50
    assert r['quality']['unique_pois']==15 and r['quality']['usable']==14

def test_known_store_outside_scope_still_prevents_false_opportunity():
    from tea_site.geo import lonlat
    def row(pid,x,cat):
        lon,lat=lonlat([x,125])
        return {'id':pid,'name':pid,'lon':float(lon),'lat':float(lat),'categories':[cat]}
    rows=[row('shop',2000,'target'),row('anchor',375,'competitor'),
          row('school',1100,'school'),row('home1',1200,'residential'),row('home2',1250,'residential')]
    r=run(rows,area={'lon':123.4,'lat':41.8,'radius_m':500})
    assert r['counts']['target']==1
    assert r['existing_coverage']==pytest.approx(100)
    assert r['status']=='no_suitable'
    assert all(x['new_facilities']==0 for x in r['candidate_preview'])

def test_merged_query_logs_do_not_inflate_data_pipeline():
    q={'time':'2026-10-26','category':'school','district':'210102','page':1,'returned':25}
    data={'id':'d','created':'2026-10-26','pois':sample(),'meta':{'brand':'test','districts':['210102'],'requests':0},'queries':[q,q|{'source_dataset':'parent'}]}
    r=dataset_insights(data)
    assert r['quality']['returned_items']==25 and r['quality']['requests']==1
    assert r['quality']['new_requests']==0
