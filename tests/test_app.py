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

def test_read(client):
    assert client.get('/').status_code==200
    assert client.get('/config.yaml').status_code==404
    assert client.get('/api/status').json['datasets'][0]['id']=='test'
    assert len(client.get('/api/datasets/test').json['pois'])==14
    assert client.get('/api/datasets/unknown').status_code==400

def test_csrf_and_host(client):
    assert client.post('/api/analyze',json={}).status_code==403
    assert client.post('/api/analyze',json={},headers={'X-Research-Token':web.TOKEN,'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/status',headers={'Host':'evil.example'}).status_code==403

@pytest.mark.parametrize('body',[{'area':[]},{'districts':['210411']},{'districts':'210102'}])
def test_invalid_scope_rejected_before_job(client,body):
    response=client.post('/api/analyze',json={'dataset':'test',**body},headers={'X-Research-Token':web.TOKEN})
    assert response.status_code==400


def test_non_object_post_rejected(client):
    assert client.post('/api/places',json=[],headers={'X-Research-Token':web.TOKEN}).status_code==400
