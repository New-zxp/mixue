import csv
import io
import json
import secrets
import threading
import uuid
from datetime import datetime
from urllib.parse import urlsplit
from flask import Flask, jsonify, request, render_template, Response, send_file, abort
from werkzeug.exceptions import HTTPException
from tea_site import storage
from tea_site.collector import collect,DISTRICTS,LABELS,derive,search_places,now
from tea_site.classify import VERSION
from tea_site.model import analyze,parameters
from tea_site.density import kde
from tea_site.insights import dataset_insights

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
    files=[storage.ROOT/'data'/'maps'/f'shenyang-{kind}.pmtiles' for kind in ('streets','terrain')]
    version='-'.join(str(p.stat().st_mtime_ns) if p.is_file() else 'missing' for p in files)
    return render_template('index.html',token=TOKEN,map_version=version)

@app.get('/maps/<name>.pmtiles')
def offline_map(name):
    # A fixed allowlist keeps local data/config files out of this public route.
    if name not in {'shenyang-streets','shenyang-terrain'}:abort(404)
    path=storage.ROOT/'data'/'maps'/f'{name}.pmtiles'
    if not path.is_file():abort(404)
    return send_file(path,mimetype='application/octet-stream',conditional=True,max_age=86400)

@app.get('/api/status')
def status():
    return jsonify(datasets=storage.datasets(),districts=DISTRICTS,labels=LABELS,key_configured=(storage.ROOT/'config.yaml').exists())

@app.get('/api/datasets/<dataset>')
def dataset(dataset):return jsonify(storage.get_dataset(dataset))

@app.get('/api/insights/<dataset>')
def insights(dataset):
    data=storage.get_dataset(dataset)
    if data['status']=='running':raise ValueError('数据正在采集，请等待完成后查看规律')
    if data['meta'].get('classification_version')!=VERSION:raise ValueError('请先清洗旧版快照再统计规律')
    return jsonify(dataset_insights(data))

@app.get('/api/density/<dataset>')
def density(dataset):return jsonify(kde(storage.get_dataset(dataset)['pois']))

def persist_job(jid,info):
    jobs[jid].update(info)
    with storage.connect() as c:c.execute('INSERT OR REPLACE INTO tasks VALUES(?,?)',(jid,json.dumps(jobs[jid],ensure_ascii=False,allow_nan=False)))

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

@app.post('/api/collect')
def collect_route():
    options=request.get_json()
    if not isinstance(options,dict):raise ValueError('请求参数格式错误')
    return start_job('collect',lambda progress,cancel:collect(options,progress,cancel))

@app.get('/api/jobs')
def all_jobs():
    with storage.connect() as c:rows=[json.loads(r[0]) for r in c.execute('SELECT payload FROM tasks')]
    rows.sort(key=lambda r:r.get('created',''),reverse=True)
    return jsonify([{k:v for k,v in r.items() if k!='result'} for r in rows[:20]])

@app.post('/api/jobs/<jid>/cancel')
def cancel_job(jid):
    if jid not in cancellations or jobs[jid]['done']:raise ValueError('任务已结束或不在本进程运行')
    cancellations[jid].set();persist_job(jid,{'message':'正在取消，将在当前请求返回后保存进度'})
    return jsonify(ok=True)

@app.get('/api/jobs/<jid>')
def job(jid):
    if jid in jobs:return jsonify(jobs[jid])
    with storage.connect() as c:r=c.execute('SELECT payload FROM tasks WHERE id=?',(jid,)).fetchone()
    if not r:raise ValueError('任务不存在')
    return jsonify(json.loads(r[0]))

@app.post('/api/places')
def places():
    raw=request.get_json()
    if not isinstance(raw,dict):raise ValueError('参数错误')
    return jsonify(search_places(raw.get('query')))

@app.post('/api/derive')
def derive_route():return jsonify(dataset=derive(request.get_json().get('datasets')))

@app.post('/api/datasets/<dataset>/archive')
def archive_dataset(dataset):
    d=storage.get_dataset(dataset)
    if d['status']=='running':raise ValueError('请先停止采集')
    d['meta']['archived']=request.get_json().get('archived',True) is True
    storage.save_dataset(dataset,d['status'],d['meta']);return jsonify(ok=True)

@app.get('/api/exclusions/<dataset>')
def exclusions(dataset):
    storage.get_dataset(dataset);return jsonify(storage.list_exclusions(dataset))

@app.post('/api/exclusions/<dataset>')
def add_exclusion(dataset):
    from tea_site.model import parameters
    storage.get_dataset(dataset);row=request.get_json();parameters({'exclusions':[row]})
    row['id']=uuid.uuid4().hex[:12];row['name']=str(row.get('name','人工排除区域'))[:100]
    with storage.connect() as c:c.execute('INSERT INTO exclusions VALUES(?,?,?)',(dataset,row['id'],json.dumps(row,ensure_ascii=False)))
    return jsonify(row)

@app.post('/api/exclusions/<dataset>/<eid>/remove')
def remove_exclusion(dataset,eid):
    with storage.connect() as c:c.execute('DELETE FROM exclusions WHERE dataset=? AND id=?',(dataset,eid))
    return jsonify(ok=True)

def save_run(dataset,result):
    rid=uuid.uuid4().hex[:12];result['run_id']=rid;result['dataset']=dataset
    result['created']=datetime.now().astimezone().isoformat(timespec='seconds')
    result['dataset_meta']=storage.get_dataset(dataset)['meta']
    with storage.connect() as c:c.execute('INSERT INTO runs VALUES(?,?,?,?)',(rid,dataset,result['created'],json.dumps(result,ensure_ascii=False,allow_nan=False)))
    return result

@app.post('/api/analyze')
def analyze_route():
    raw=request.get_json()
    if not isinstance(raw,dict):raise ValueError('请求参数格式错误')
    dataset_id=str(raw.get('dataset',''));data=storage.get_dataset(dataset_id)
    if data['status']=='running':raise ValueError('请等待采集完成后再分析')
    if data['meta'].get('classification_version')!=VERSION:raise ValueError('旧版数据尚未校验类别，请先点击“清洗当前快照”')
    # Nearby snapshots cannot be reused as evidence for a larger or different area.
    parameters(raw)  # Validate before inspecting nested values or starting a job.
    source_area=data['meta'].get('area');requested=raw.get('area')
    if source_area:
        if not requested:raw['area']=source_area
        elif abs(float(requested.get('lon',0))-source_area['lon'])>1e-5 or abs(float(requested.get('lat',0))-source_area['lat'])>1e-5 or float(requested.get('radius_m',0))>source_area['radius_m']:
            raise ValueError('当前数据只覆盖原地点附近，请为新范围采集数据')
    raw['collection_meta']=data['meta']
    raw['boundaries']=data['meta'].get('boundaries',{})
    raw['exclusions']=storage.list_exclusions(dataset_id)
    if not raw.get('districts'):raw['districts']=data['meta'].get('districts',[])
    if any(d not in data['meta'].get('districts',[]) for d in raw['districts']):raise ValueError('所选行政区不在当前采集范围内')
    def task(progress,cancel):
        progress({'message':'固定1公里评估，逐一比较范围内候选点…'})
        return save_run(dataset_id,analyze(data['pois'],raw,cancel))
    return start_job('analysis',task)

@app.post('/api/sensitivity')
def sensitivity_route():
    return jsonify(error='已按需求固定为1公里；不再提供半径调整功能'),410

@app.get('/api/runs')
def runs():
    with storage.connect() as c:
        return jsonify([{'id':r['id'],'dataset':r['dataset'],'created':r['created'],'version':json.loads(r['payload']).get('model_version',1),'status':json.loads(r['payload']).get('status','legacy')} for r in c.execute('SELECT * FROM runs ORDER BY created DESC LIMIT 100')])

@app.get('/api/runs/<rid>')
def run_detail(rid):
    return jsonify(read_run(rid))

def read_run(rid):
    with storage.connect() as c:r=c.execute('SELECT payload FROM runs WHERE id=?',(rid,)).fetchone()
    if not r:raise ValueError('方案不存在')
    return json.loads(r[0])

def csv_response(rows,filename):
    out=io.StringIO(newline='')
    if rows:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader()
        for row in rows:
            safe=dict(row)
            for k,v in safe.items():
                if isinstance(v,(dict,list)):safe[k]=json.dumps(v,ensure_ascii=False)
                if isinstance(safe[k],str) and safe[k].lstrip().startswith(('=','+','-','@','\t','\r')):safe[k]="'"+safe[k]
            w.writerow(safe)
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="{filename}"'})

@app.get('/api/export/dataset/<dataset>')
def export_dataset(dataset):
    data=storage.get_dataset(dataset)
    return csv_response(data['pois'],f'pois_{dataset}.csv')

@app.get('/api/export/run/<rid>')
def export_run(rid):
    r=read_run(rid)
    if request.args.get('format')=='json':
        return Response(json.dumps(r,ensure_ascii=False,indent=2),mimetype='application/json',headers={'Content-Disposition':f'attachment; filename="analysis_{rid}.json"'})
    rows=[]
    for p in r['plans']:
        for s in p['selected']:rows.append({'method':p['method'],**s,'plan_new_coverage':p['new_coverage'],'plan_total_coverage':p['total_coverage'],'objective':p['objective'],'solver_status':p['solver_status'],'input_sha256':r['input_sha256']})
    if not rows:rows=[{'status':r.get('status'),'reason':r.get('reason'),'input_sha256':r['input_sha256']}]
    return csv_response(rows,f'locations_{rid}.csv')

if __name__=='__main__':
    storage.connect().close()
    with storage.connect() as con:
        for row in con.execute('SELECT id,payload FROM tasks').fetchall():
            task=json.loads(row['payload'])
            if not task.get('done'):
                task.update(done=True,error='服务已重启，采集进度已保存，可选择原快照续采')
                con.execute('UPDATE tasks SET payload=? WHERE id=?',(json.dumps(task,ensure_ascii=False),row['id']))
        for row in con.execute("SELECT id,meta FROM datasets WHERE status='running'").fetchall():
            meta=json.loads(row['meta']);meta['error']='上次服务中断，保留已采集的部分数据'
            con.execute('UPDATE datasets SET status=?,meta=? WHERE id=?',('interrupted',json.dumps(meta,ensure_ascii=False),row['id']))
    app.run(host='127.0.0.1',port=8765,debug=False,threaded=True)
