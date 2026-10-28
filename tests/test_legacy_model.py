import itertools
import numpy as np
import pytest
from tea_site.legacy_model import parameters,prepare,solve,analyze

def sample():
    rows=[]
    for i in range(12):
        rows.append({'id':str(i),'lon':123.4+i%4*.01,'lat':41.8+i//4*.01,'categories':['residential']})
    rows.append({'id':'t','lon':123.4,'lat':41.8,'categories':['target']})
    rows.append({'id':'c','lon':123.425,'lat':41.81,'categories':['competitor']})
    return rows

def test_matches_bruteforce():
    p=parameters({'k':2,'radius':800,'spacing':500});z=prepare(sample(),p);result=solve(z,p)
    scores=[]
    for combo in itertools.combinations(range(len(z['candidate'])),2):
        if any(a in combo and b in combo for a,b in z['conflict']):continue
        new=z['coverage'][:,combo].any(axis=1)&~z['existing']
        scores.append(float(z['weights'][new].sum())-p['penalty']*100*z['compnorm'][list(combo)].mean())
    assert result['objective']==pytest.approx(max(scores),abs=1e-5)
    assert len(result['selected'])==2

def test_metrics_and_baselines():
    r=analyze(sample(),{'k':2})
    assert len(r['plans'])==3
    for plan in r['plans']:
        assert 0<=plan['new_coverage']<=100.00001
        assert plan['total_coverage']==pytest.approx(r['existing_coverage']+plan['new_coverage'])
    assert r['plans'][0]['objective']+1e-4>=max(p['objective'] for p in r['plans'][1:])

def test_no_target_competitor():
    r=analyze(sample()[:12],{'k':2});assert len(r['plans'])==2
    assert r['existing_coverage']==0
    assert r['plans'][0]['competition_index']==0

def test_empty_and_infeasible():
    with pytest.raises(ValueError):analyze([], {})
    with pytest.raises(ValueError):analyze(sample()[:1],{'k':3})

@pytest.mark.parametrize('params',[{'k':1.5},{'radius':float('nan')},{'grid':0},{'weights':{'school':-1}},{'k':11}])
def test_bad_parameters(params):
    with pytest.raises(ValueError):parameters(params)

def test_deterministic_and_weight_sum():
    a=analyze(sample(),{'k':2});b=analyze(list(reversed(sample())),{'k':2})
    assert a['input_sha256']==b['input_sha256']
    assert a['plans']==b['plans']
    assert sum(c['weight'] for c in a['cells'])==pytest.approx(100)

def test_all_covered():
    rows=sample()
    rows.extend([dict(r,id='target'+r['id'],categories=['target']) for r in rows[:12]])
    r=analyze(rows,{'k':2,'spacing':0})
    assert r['existing_coverage']==pytest.approx(100)
    assert r['plans'][0]['new_coverage']==pytest.approx(0)

def test_pairwise_infeasible():
    rows=sample()[:3]
    with pytest.raises(ValueError,match='不可行'):
        analyze(rows,{'k':3,'spacing':3000})
