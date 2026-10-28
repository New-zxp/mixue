from app import app


def test_local_map_range_and_allowlist(tmp_path, monkeypatch):
    from tea_site import storage
    monkeypatch.setattr(storage, 'ROOT', tmp_path)
    folder = tmp_path / 'data' / 'maps'
    folder.mkdir(parents=True)
    content = b'PMTiles' + bytes(range(256))
    (folder / 'shenyang-streets.pmtiles').write_bytes(content)
    client = app.test_client()
    response = client.get('/maps/shenyang-streets.pmtiles', headers={'Range': 'bytes=0-6'})
    assert response.status_code == 206
    assert response.data == b'PMTiles'
    assert response.headers['Content-Range'] == f'bytes 0-6/{len(content)}'
    assert 'max-age=86400' in response.headers['Cache-Control']
    assert client.get('/maps/config.pmtiles').status_code == 404
    assert client.get('/maps/shenyang-terrain.pmtiles').status_code == 404
    assert client.get('/maps/shenyang-streets.pmtiles', headers={'Range': 'bytes=9999-10000'}).status_code == 416
