import numpy as np
import pytest
from tea_site.model import analyze,parameters
from tea_site.geometry import boundary_mask
from tea_site.geo import xy

BOUNDARIES={'210102':{'rings':[[[123.39,41.79],[123.47,41.79],[123.47,41.85],[123.39,41.85]]]}}

def sample():
    rows=[]
    for i in range(12):
        rows.append({'id':str(i),'name':'fixture','lon':123.415+i%4*.005,'lat':41.805+i//4*.005,'categories':['residential' if i%2 else 'school']})
    rows.append({'id':'t','name':'target','lon':123.4,'lat':41.8,'categories':['target']})
    rows.append({'id':'c','name':'commercial','lon':123.425,'lat':41.81,'categories':['competitor']})
    return rows

def run(rows=None,**kwargs):
    return analyze(sample() if rows is None else rows,{'boundaries':BOUNDARIES,'districts':['210102'],**kwargs})

def test_fixed_single_store_and_exact_maximum():
    r=run(k=20,radius=300,spacing=800)
    assert r['status']=='recommended'
    assert r['parameters']['k']==1 and r['parameters']['radius']==1000
    assert len(r['plans'][0]['selected'])==1
    assert r['plans'][0]['objective']==pytest.approx(max(x['score'] for x in r['candidate_preview'] if x['qualified']))
    assert sum(x['weight'] for x in r['cells'])==pytest.approx(100)
    for x in r['candidate_preview']:
        assert boundary_mask(xy([[x['lon'],x['lat']]]),BOUNDARIES)[0]

def test_truthful_empty_and_covered():
    assert run([])['status']=='insufficient_data'
    assert analyze(sample(),{})['status']=='insufficient_data'
    rows=sample();rows += [dict(r,id='target'+r['id'],categories=['target']) for r in rows[:12]]
    r=run(rows)
    assert r['existing_coverage']==pytest.approx(100)
    assert r['status']=='no_suitable' and r['plans']==[]

def test_place_outside_and_exclusion():
    r=run(area={'lon':123.6,'lat':41.8,'radius_m':3000})
    assert r['status']=='outside_scope' and not r['plans']
    r=run(exclusions=[{'lon':123.425,'lat':41.81,'radius_m':2000}])
    assert r['status']=='no_suitable' and not r['plans']

def test_nine_district_allowlist_cannot_be_overridden():
    with pytest.raises(ValueError):parameters({'districts':['210411']})
    r=analyze(sample(),{'boundaries':{'210411':BOUNDARIES['210102']}})
    assert r['status']=='insufficient_data' and not r['plans']
    r=analyze(sample(),{'boundaries':BOUNDARIES,'districts':['210102','210103']})
    assert r['status']=='insufficient_data'

def test_circle_and_boundary_intersection():
    r=run(area={'lon':123.425,'lat':41.81,'radius_m':500})
    assert r['status']=='recommended'
    center=xy([[123.425,41.81]])[0]
    for p in r['candidate_preview']:
        assert np.linalg.norm(xy([[p['lon'],p['lat']]])[0]-center)<=500
        assert boundary_mask(xy([[p['lon'],p['lat']]]),BOUNDARIES)[0]

def test_deterministic():
    a=run();b=run(list(reversed(sample())))
    assert a['input_sha256']==b['input_sha256'] and a['plans']==b['plans']

@pytest.mark.parametrize('raw',[{'area':[]},{'area':{'lon':float('nan'),'lat':41.8,'radius_m':1000}},{'districts':'210102'}])
def test_invalid_scope(raw):
    with pytest.raises(ValueError):parameters(raw)


def test_incomplete_collection_is_not_no_suitable():
    from tea_site.collector import initial_plan
    plan=initial_plan(['210102'],'test')
    r=run(collection_meta={'plan':plan})
    assert r['status']=='insufficient_data' and not r['plans']
    for q in plan:q['status']='capped'
    assert run(collection_meta={'plan':plan})['status']=='recommended'
    assert run(collection_meta={'plan':plan[:1]})['status']=='insufficient_data'
