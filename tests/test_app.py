import json
import pytest
import app as web
from tea_site import storage
from tests.test_model import sample,BOUNDARIES
from tea_site.classify import VERSION

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'test.sqlite3')
    rows=[dict(r,name='test',address='test',district='test',gcj_lon=r['lon'],gcj_lat=r['lat']) for r in sample()]
    with storage.connect() as c:
        c.execute('INSERT INTO datasets VALUES(?,?,?,?)',('test','2026-10-25',json.dumps({'brand':'test','districts':['210102'],'boundaries':BOUNDARIES,'classification_version':VERSION}),'sample_ready'))
        for r in rows:c.execute('INSERT INTO pois VALUES(?,?,?)',('test',r['id'],json.dumps(r)))
    return web.app.test_client()

def test_read_and_exports(client):
    assert client.get('/').status_code==200
    assert client.get('/config.yaml').status_code==404
    assert client.get('/api/status').json['datasets'][0]['id']=='test'
    assert len(client.get('/api/datasets/test').json['pois'])==14
    res=client.get('/api/export/dataset/test')
    assert res.status_code==200 and res.data.startswith(b'\xef\xbb\xbf')
    assert client.get('/api/datasets/unknown').status_code==400

def test_csrf_and_host(client):
    assert client.post('/api/analyze',json={}).status_code==403
    assert client.post('/api/analyze',json={},headers={'X-Research-Token':web.TOKEN,'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/status',headers={'Host':'evil.example'}).status_code==403

def test_saved_result_export(client):
    data=storage.get_dataset('test');r=web.save_run('test',web.analyze(data['pois'],{'boundaries':BOUNDARIES}))
    saved=client.get('/api/runs/'+r['run_id']).json
    assert saved['input_sha256']==r['input_sha256']
    assert client.get('/api/export/run/'+r['run_id']).status_code==200
    assert client.get('/api/export/run/'+r['run_id']+'?format=json').json['parameters']['k']==1

def test_formula_injection(client):
    with web.app.app_context():
        r=web.csv_response([{'name':'=HYPERLINK("https://example.com")'}],'a.csv')
        assert "'=HYPERLINK" in r.get_data(as_text=True)

def test_kde(client):
    r=client.get('/api/density/test').json
    assert r['max']>0 and r['bandwidth_m']==800
    assert len(r['cells'])>10


@pytest.mark.parametrize('body',[{'area':[]},{'districts':['210411']},{'districts':'210102'}])
def test_invalid_scope_rejected_before_job(client,body):
    response=client.post('/api/analyze',json={'dataset':'test',**body},headers={'X-Research-Token':web.TOKEN})
    assert response.status_code==400


def test_non_object_post_rejected(client):
    assert client.post('/api/places',json=[],headers={'X-Research-Token':web.TOKEN}).status_code==400
