"""Manual offline-map preparation; never called by the web application.

Download licensed regional archives, validate them, then atomically publish.
The OSM public raster tile service is deliberately not used.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT / 'data' / 'maps'
TOOL = ROOT / 'scripts' / 'bin' / 'pmtiles.exe'
CITY = '122.2,41.1,124.2,43.2'
OVERVIEW = '120,39,127,45'
SOURCES = {
    'streets': ('https://data.source.coop/protomaps/openstreetmap/v4.pmtiles', 15),
    'terrain': ('https://data.source.coop/mapterhorn/mapterhorn/planet.pmtiles', 12),
}


def run(*args):
    env = {k: v for k, v in os.environ.items() if k.lower() not in {'http_proxy', 'https_proxy', 'all_proxy'}}
    subprocess.run([str(TOOL), *map(str, args)], check=True, env=env, timeout=1800)


def prepare(kind):
    url, maxzoom = SOURCES[kind]
    stage = ROOT / 'work' / 'offline-map-build'
    stage.mkdir(parents=True, exist_ok=True)
    overview, detail, merged = [stage / f'{kind}-{suffix}.pmtiles' for suffix in ('overview', 'detail', 'merged')]
    # Disjoint zoom ranges: a broad low-resolution surround, full detail for Shenyang.
    run('extract', url, overview, f'--bbox={OVERVIEW}', '--maxzoom=10', '--download-threads=4')
    run('extract', url, detail, f'--bbox={CITY}', '--minzoom=11', f'--maxzoom={maxzoom}', '--download-threads=4')
    run('merge', overview, detail, merged)
    run('verify', merged)
    destination = MAPS / f'shenyang-{kind}.pmtiles'
    os.replace(merged, destination)
    return {'file': destination.name, 'source': url, 'max_data_zoom': maxzoom,
            'bytes': destination.stat().st_size, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


if __name__ == '__main__':
    if not TOOL.is_file():
        raise SystemExit('Missing scripts/bin/pmtiles.exe; see docs/offline-maps.md for the official download.')
    MAPS.mkdir(parents=True, exist_ok=True)
    # Sequential to avoid flooding a public download service.
    records = {kind: prepare(kind) for kind in SOURCES}
    (MAPS / 'manifest.json').write_text(json.dumps({
        'downloaded_at': datetime.now(timezone.utc).isoformat(),
        'detail_bounds': list(map(float, CITY.split(','))),
        'overview_bounds': list(map(float, OVERVIEW.split(','))),
        'maps': records,
    }, ensure_ascii=False, indent=2), encoding='utf8')
