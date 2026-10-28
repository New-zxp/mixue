from tea_site.collector import in_district
import pytest
from tea_site import collector,storage

def test_district_code_and_name_fallback():
    assert in_district({'adcode':'210102'},'210102')
    assert in_district({'cityname':'沈阳市','adname':'和平区'},'210102')
    assert in_district({'adcode':[],'cityname':'沈阳市','adname':'和平区'},'210102')
    assert not in_district({'cityname':'天津市','adname':'和平区'},'210102')
    assert not in_district({'cityname':'沈阳市','adname':'浑南区'},'210102')
    assert not in_district({'adcode':'210112','cityname':'沈阳市','adname':'和平区'},'210102')
    assert not in_district({},'210102')

@pytest.mark.parametrize('budget,expected,calls',[(1,'budget_stopped',1),(9,'sample_ready',9)])
def test_budget_boundaries(tmp_path,monkeypatch,budget,expected,calls):
    monkeypatch.setattr(storage,'ROOT',tmp_path)
    monkeypatch.setattr(storage,'DB',tmp_path/'db.sqlite3')
    (tmp_path/'config.yaml').write_text('amap_key: test-only',encoding='utf-8')
    counter=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'status':'1','count':'1','pois':[{'id':'test','name':'蜜雪冰城','location':'123.4,41.8','cityname':'沈阳市','adname':'和平区'}]}
    def get(*args,**kwargs):counter.append(1);return Response()
    monkeypatch.setattr(collector.requests,'get',get)
    did=collector.collect({'pages':1,'budget':budget,'districts':['210102'],'boundaries':False})
    data=storage.get_dataset(did)
    assert data['status']==expected
    assert len(counter)==calls==data['meta']['requests']
    assert len(data['queries'])==calls
    assert 'test-only' not in str(data)
