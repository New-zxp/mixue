import secrets
import threading
import uuid
from datetime import datetime
from urllib.parse import urlsplit
from flask import Flask, jsonify, request, render_template, send_file, abort
from werkzeug.exceptions import HTTPException
from tea_site import storage
from tea_site.scope import DISTRICTS,LABELS

def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")
from tea_site.classify import VERSION
from tea_site.model import analyze,parameters
from tea_site.place_search import search_saved_places

app=Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD']=True
app.config['MAX_CONTENT_LENGTH']=64*1024
TOKEN=secrets.token_urlsafe(32)
job_lock=threading.Lock(); jobs={}; cancellations={}

@app.before_request
def local_guard():
    if request.host.split(':')[0] not in {'localhost','127.0.0.1','[::1]'}:
        return jsonify(error='仅允许本机访问'),403
    if request.method=='POST':
        if request.headers.get('X-Research-Token')!=TOKEN:return jsonify(error='请刷新页面后重试'),403
        origin=request.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=request.host:return jsonify(error='不允许跨站请求'),403
        if not isinstance(request.get_json(silent=True),dict):return jsonify(error='请提交JSON对象参数'),400

@app.after_request
def headers(resp):
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['X-Frame-Options']='DENY'
    resp.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    if request.path.startswith('/api/'):resp.headers['Cache-Control']='no-store'
    return resp

@app.errorhandler(ValueError)
def invalid(exc):return jsonify(error=str(exc)),400

@app.errorhandler(TypeError)
def bad_type(exc):return jsonify(error='参数类型不正确，请检查输入'),400

@app.errorhandler(HTTPException)
def http_error(exc):return jsonify(error='请求格式或资源访问错误',status=exc.code),exc.code

@app.errorhandler(404)
def missing(exc):return jsonify(error='资源不存在'),404

@app.route('/')
def index():
    files=[storage.ROOT/'data'/'maps'/f'shenyang-{kind}.pmtiles' for kind in ('streets',)]
    version='-'.join(str(p.stat().st_mtime_ns) if p.is_file() else 'missing' for p in files)
    return render_template('index.html',token=TOKEN,map_version=version)

@app.get('/maps/<name>.pmtiles')
def offline_map(name):
    # A fixed allowlist keeps local data/config files out of this public route.
    if name not in {'shenyang-streets'}:abort(404)
    path=storage.ROOT/'data'/'maps'/f'{name}.pmtiles'
    if not path.is_file():abort(404)
    return send_file(path,mimetype='application/octet-stream',conditional=True,max_age=86400)

@app.get('/api/status')
def status():
    return jsonify(datasets=storage.datasets(),districts=DISTRICTS,labels=LABELS)

@app.get('/api/datasets/<dataset>')
def dataset(dataset):return jsonify(storage.get_dataset(dataset))

def persist_job(jid,info):
    jobs[jid].update(info)

def start_job(kind,fn):
    if not job_lock.acquire(blocking=False):return jsonify(error='已有任务运行，请等待完成'),409
    jid=uuid.uuid4().hex[:12];jobs[jid]={'id':jid,'kind':kind,'done':False,'message':'准备中','created':now()};cancellations[jid]=threading.Event();persist_job(jid,{})
    def run():
        try:
            result=fn(lambda info:persist_job(jid,info),cancellations[jid].is_set)
            persist_job(jid,{'result':result,'done':True})
        except Exception as exc:
            persist_job(jid,{'done':True,'error':str(exc) if isinstance(exc,(ValueError,FileNotFoundError)) else '任务失败，请检查输入数据；敏感信息未输出'})
        finally:job_lock.release()
    threading.Thread(target=run,daemon=True).start()
    return jsonify(job=jid),202

@app.get('/api/jobs/<jid>')
def job(jid):
    if jid in jobs:return jsonify(jobs[jid])
    raise ValueError('任务不存在，请重新开始选址')

@app.post('/api/places')
def places():
    raw=request.get_json()
    if not isinstance(raw,dict):raise ValueError('参数错误')
    return jsonify(search_saved_places(raw.get('query'), raw.get('dataset')))

@app.post('/api/analyze')
def analyze_route():
    raw=request.get_json()
    if not isinstance(raw,dict):raise ValueError('请求参数格式错误')
    dataset_id=str(raw.get('dataset',''));data=storage.get_dataset(dataset_id)
    if data['status']=='running':raise ValueError('当前数据不可用于分析')
    if data['meta'].get('classification_version')!=VERSION:raise ValueError('当前数据版本不支持分析')
    # Nearby snapshots cannot be reused as evidence for a larger or different area.
    parameters(raw)  # Validate before inspecting nested values or starting a job.
    source_area=data['meta'].get('area');requested=raw.get('area')
    if source_area:
        if not requested:raw['area']=source_area
        elif abs(float(requested.get('lon',0))-source_area['lon'])>1e-5 or abs(float(requested.get('lat',0))-source_area['lat'])>1e-5 or float(requested.get('radius_m',0))>source_area['radius_m']:
            raise ValueError('当前数据只覆盖原地点附近，请缩小选址范围')
    raw['collection_meta']=data['meta']
    raw['boundaries']=data['meta'].get('boundaries',{})
    raw['exclusions']=storage.list_exclusions(dataset_id)
    if not raw.get('districts'):raw['districts']=data['meta'].get('districts',[])
    if any(d not in data['meta'].get('districts',[]) for d in raw['districts']):raise ValueError('所选行政区不在当前采集范围内')
    def task(progress,cancel):
        progress({'message':'固定1公里评估，逐一比较范围内候选点…'})
        return analyze(data['pois'],raw,cancel)
    return start_job('analysis',task)

if __name__=='__main__':
    storage.connect().close()
    app.run(host='127.0.0.1',port=8765,debug=False,threaded=True)
