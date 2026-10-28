import json
import socket
import pytest
import app as web
from tea_site import storage
from tea_site.scope import DISTRICTS
from tea_site.classify import VERSION
from tea_site.place_search import search_saved_places

@pytest.fixture
def saved(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'data.sqlite3')
    def forbidden(*args,**kwargs):
        raise AssertionError('Unexpected network connection')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    meta={'districts':list(DISTRICTS),'boundaries':dict.fromkeys(DISTRICTS,{}),'classification_version':VERSION}
    row={'id':'school','name':'东北大学','address':'文化路','adcode':'210102','lon':123.4,'lat':41.8,'gcj_lon':123.406,'gcj_lat':41.802}
    with storage.connect() as c:
        c.execute('INSERT INTO datasets VALUES(?,?,?,?)',('saved','2026-10-26',json.dumps(meta),'sample_ready'))
        c.execute('INSERT INTO pois VALUES(?,?,?)',('saved',row['id'],json.dumps(row)))
    return web.app.test_client()

def test_local_name_address_and_natural_query(saved):
    for query in ['东北大学','文化路','在东北大学附近选址']:
        result=search_saved_places(query)
        assert result['source']=='local' and result['requests']==0
        assert result['places'][0]['id']=='school'
    assert search_saved_places('不存在的学校')['places']==[]

@pytest.mark.parametrize('query',[None,[], '', '附近', '字'*101])
def test_invalid_search(saved,query):
    with pytest.raises(ValueError):search_saved_places(query)

def test_offline_endpoints(saved):
    headers={'X-Research-Token':web.TOKEN}
    response=saved.post('/api/places',json={'query':'东北大学','dataset':'saved'},headers=headers)
    assert response.status_code==200 and len(response.json['places'])==1
    assert 'key_configured' not in saved.get('/api/status').json
    assert saved.post('/api/collect',json={},headers=headers).status_code==404
    assert saved.post('/api/derive',json={},headers=headers).status_code==404
