"""Recompute an existing local snapshot; never calls external APIs."""
import argparse
import json
import sys
import platform
import importlib.metadata
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tea_site import storage
from tea_site.model import analyze

parser=argparse.ArgumentParser()
parser.add_argument('--dataset')
args=parser.parse_args()
datasets=storage.datasets()
dataset=args.dataset or next((d['id'] for d in datasets if d['meta'].get('unique_records',0)>0 and d['meta'].get('classification_version')),None)
if not dataset:raise SystemExit('Bundled dataset missing. Restore data/research.sqlite3 from the project package.')
data=storage.get_dataset(dataset);result=analyze(data['pois'],{'collection_meta':data['meta'],'boundaries':data['meta'].get('boundaries',{}),'districts':data['meta']['districts'],'area':data['meta'].get('area'),'exclusions':storage.list_exclusions(dataset)})
out=storage.ROOT/'results';out.mkdir(exist_ok=True)
(out/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
manifest={'dataset':dataset,'input_sha256':result['input_sha256'],'parameters':result['parameters'],'seed':None,'algorithm':'deterministic exact single-site enumeration','python':platform.python_version(),'dependencies':{n:importlib.metadata.version(n) for n in ['numpy','scipy','Flask']},'command':f'python scripts/reproduce.py --dataset {dataset}', 'data_status':'keyword_sample_not_full_census'}
(out/'reproduction.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'dataset':dataset,'records':len(data['pois']),'candidates':result['candidate_count'],'plans':[{k:v for k,v in p.items() if k!='selected'} for p in result['plans']]},ensure_ascii=True,indent=2))
