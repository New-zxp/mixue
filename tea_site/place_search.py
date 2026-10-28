"""Search the saved nine-district snapshot without an API key or network."""
import re
from . import storage
from .scope import DISTRICTS


def search_saved_places(text, dataset=None):
    if not isinstance(text, str) or not text.strip() or len(text) > 100:
        raise ValueError('请输入1—100字的地点')
    word = re.sub(r'^(我想|请|想|我要)?在', '', text.strip())
    word = re.sub(r'(附近|周边).*$', '', word)
    word = re.sub(r'(选址|开店)$', '', word).strip()
    if not word:
        raise ValueError('请输入具体学校、商场或街道名称')
    sources = [d for d in storage.datasets()
               if d['status'] == 'sample_ready' and not d['meta'].get('archived')
               and not d['meta'].get('area') and d['meta'].get('classification_version')
               and set(d['meta'].get('districts', [])) == set(DISTRICTS)
               and set(d['meta'].get('boundaries', {})) == set(DISTRICTS)]
    source = next((d for d in sources if d['id'] == dataset), None) if dataset else next(iter(sources), None)
    if source is None:
        raise ValueError('暂无可搜索的完整九区数据')
    needle = re.sub(r'\s+', '', word).casefold()
    matches = []
    for p in storage.get_dataset(source['id'])['pois']:
        if str(p.get('adcode', '')) not in DISTRICTS:
            continue
        name = str(p.get('name', ''))
        address = str(p.get('address') or '')
        normalized = re.sub(r'\s+', '', name).casefold()
        if needle not in normalized and needle not in re.sub(r'\s+', '', address).casefold():
            continue
        if not all(isinstance(p.get(k), (int, float)) for k in ('lon', 'lat', 'gcj_lon', 'gcj_lat')):
            continue
        match = {k: p[k] for k in ('id', 'lon', 'lat', 'gcj_lon', 'gcj_lat')}
        match.update(name=name, address=address, district='沈阳市' + DISTRICTS[str(p['adcode'])])
        rank = 0 if normalized == needle else 1 if normalized.startswith(needle) else 2 if needle in normalized else 3
        matches.append((rank, name, str(p['id']), match))
    matches.sort(key=lambda item: item[:3])
    return {'places': [item[3] for item in matches[:20]], 'outside': [],
            'query': word, 'requests': 0, 'source': 'local', 'dataset': source['id'],
            'note': '仅搜索已采集的沈阳九区地点；没有结果表示本地数据未收录匹配地点。'}
