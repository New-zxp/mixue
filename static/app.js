const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={school:'学校',residential:'住宅小区',office:'写字楼',mall:'商场',competitor:'竞品茶饮',target:'蜜雪冰城',metro:'地铁站',bus:'公交站',coffee:'咖啡店'};
const colors={target:'#3d608d',competitor:'#d99a52',school:'#4d78ae',residential:'#66864b',office:'#697c92',mall:'#b88b38',metro:'#7165a0',bus:'#688077',coffee:'#9c8070'};
const facilitySymbols={
 school:'<path d="M3 5q5-2 9 1 4-3 9-1v14q-5-2-9 1-4-3-9-1Z"/><path d="M12 6v14"/>',
 residential:'<path d="m2 11 10-9 10 9M5 9v12h14V9M10 21v-7h4v7"/>',
 office:'<path d="M5 22V2h14v20ZM9 6h1m4 0h1M9 10h1m4 0h1M9 14h1m4 0h1M10 22v-4h4v4"/>',
 mall:'<path d="M4 8h16l1 14H3ZM8 9V6a4 4 0 0 1 8 0v3"/>',
 metro:'<path d="m12 1 11 11-11 11L1 12Z"/><path d="M7 16V8l5 5 5-5v8"/>',
 bus:'<rect x="4" y="2" width="16" height="18" rx="3"/><path d="M4 12h16M12 3v9M7 20v2m10-2v2"/><circle cx="8" cy="16" r="1"/><circle cx="16" cy="16" r="1"/>',
 coffee:'<path d="M4 7h13v8a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5ZM17 8h2a3 3 0 0 1 0 6h-2M7 2v2m5-2v2M3 23h16"/>'
};
function facilitySvg(category){return '<svg viewBox="0 0 24 24" aria-hidden="true" fill="white" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+facilitySymbols[category]+'</svg>'}
function evidenceMarker(p){
 if(p.category==='target'||p.category==='competitor')return L.circleMarker([p.lat,p.lon],{radius:7,color:'#fff',weight:2,fillColor:colors[p.category],fillOpacity:1});
 return L.marker([p.lat,p.lon],{title:names[p.category]+' · '+p.name,icon:L.divIcon({className:'facility-marker facility-'+p.category,html:facilitySvg(p.category),iconSize:[26,26],iconAnchor:[13,13],popupAnchor:[0,-13]})});
}
function showFacilityLegend(){const legend=$('#evidence-legend');legend.innerHTML=Object.keys(facilitySymbols).map(cat=>'<span class="legend-item facility-'+cat+'">'+facilitySvg(cat)+'<b>'+names[cat]+'</b></span>').join('')}
let state={data:null,districts:{},area:null,result:null,busy:false,places:[]}, evidenceMarkers={},recMarker;
const map=L.map('map',{preferCanvas:true,zoomControl:false,minZoom:8,maxZoom:19,zoomSnap:1,zoomAnimation:false,markerZoomAnimation:false,fadeAnimation:false,wheelDebounceTime:160}).setView([41.8,123.43],10);
map.createPane('outside');map.getPane('outside').style.zIndex=340;map.getPane('outside').style.pointerEvents='none';
map.createPane('facilities');map.getPane('facilities').style.zIndex=380;
map.createPane('districts');map.getPane('districts').style.zIndex=350;
L.control.zoom({position:'topright'}).addTo(map);L.control.scale({imperial:false}).addTo(map);
const boundaries=L.layerGroup().addTo(map),stores=L.layerGroup().addTo(map),details=L.layerGroup().addTo(map),selection=L.layerGroup().addTo(map);
const basemaps=createBasemaps(map,{
 version:$('meta[name=map-version]').content,
 status:(message,retry=false)=>{$('#basemap-status').hidden=!message;$('#basemap-message').textContent=message;$('#retry-basemap').hidden=!retry},
 changed:()=>{syncZoom()}
});
$('#basemap').onchange=()=>basemaps.setMode($('#basemap').value);
$('#retry-basemap').onclick=()=>basemaps.retry();
const facilityImages={},facilityMarkers=new Map();let facilitiesFrame;
const FacilityCanvas=L.Canvas.extend({_updateFacility(layer){
 if(!this._drawing||layer._empty())return;
 const image=facilityImages[layer.options.category],p=layer._point,r=layer._radius;
 if(image){this._ctx.save();this._ctx.globalAlpha=1;this._ctx.drawImage(image,p.x-r,p.y-r,r*2,r*2);this._ctx.restore()}
}});
const facilityCanvas=new FacilityCanvas({pane:'facilities',padding:.2});
const FacilityPoint=L.CircleMarker.extend({_updatePath(){this._renderer._updateFacility(this)}});
function prepareFacilities(){
 $('#facility-controls').innerHTML=Object.keys(facilitySymbols).map(cat=>'<label class="facility-'+cat+'"><input type="checkbox" id="show-'+cat+'">'+facilitySvg(cat)+'<span>'+names[cat]+'</span><small id="count-'+cat+'">—</small></label>').join('');
 $$('#facility-controls input').forEach(input=>input.onchange=()=>{syncEvidence();queueFacilities()});
 return Promise.all(Object.keys(facilitySymbols).map(cat=>new Promise((resolve,reject)=>{
  const image=new Image();image.onload=()=>{facilityImages[cat]=image;resolve()};image.onerror=reject;
  image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(facilitySvg(cat).replace('<svg ','<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" ').replace('currentColor',colors[cat]));
 })));
}
function queueFacilities(){if(facilitiesFrame)cancelAnimationFrame(facilitiesFrame);facilitiesFrame=requestAnimationFrame(()=>{facilitiesFrame=null;drawFacilities()})}
function drawFacilities(){
 if(!state.data)return;
 const rows=regionPois(),viewport=map.getBounds().pad(.15),keep=new Set(),counts={};
 const radius=map.getZoom()<12?6:map.getZoom()<14?8:11;
 for(const p of rows){
  const categories=p.categories.filter(c=>facilitySymbols[c]);for(const c of categories)counts[c]=(counts[c]||0)+1;
  const category=categories.find(c=>storeVisible(c,p.brand));
  if(!category||!viewport.contains([p.lat,p.lon]))continue;
  const evidence=evidenceMarkers[p.id];if(evidence&&details.hasLayer(evidence))continue;
  keep.add(p.id);let marker=facilityMarkers.get(p.id);
  if(!marker){marker=new FacilityPoint([p.lat,p.lon],{renderer:facilityCanvas,radius,category,weight:0}).bindPopup(()=>'<strong>'+esc(p.name)+'</strong><br>'+esc(names[marker.options.category])+' · '+esc(p.district)+'<br>'+esc(p.address||'暂无详细地址'));marker.addTo(map);facilityMarkers.set(p.id,marker)}
  else if(marker.options.category!==category||marker.getRadius()!==radius){marker.options.category=category;marker.setRadius(radius)}
 }
 for(const [id,marker]of facilityMarkers){if(!keep.has(id)){map.removeLayer(marker);facilityMarkers.delete(id)}}
 for(const cat of Object.keys(facilitySymbols))$('#count-'+cat).textContent=counts[cat]||0;
}
map.on('moveend',queueFacilities);
function notify(message){$('#notice').textContent=message;$('#notice').hidden=!message}
async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Research-Token':$('meta[name=research-token]').content},body:JSON.stringify(body)});let result;try{result=await response.json()}catch{throw Error('服务暂时无法连接，请刷新页面重试')}if(!response.ok)throw Error(result.error||'请求失败');return result}
function panel(open){$('#plan-panel').hidden=!open;$('#toggle-plan').setAttribute('aria-expanded',String(open));$('#map-shell').classList.toggle('planning',open);if(open&&state.result?.status==='recommended')focusResult()}
function boundsOptions(){const open=!$('#plan-panel').hidden;return {animate:false,paddingTopLeft:[45,85],paddingBottomRight:[open&&innerWidth>850?455:open&&innerWidth>580?395:45,65],maxZoom:16}}
function restrictToShenyang(){
 const rings=Object.values(state.data.meta.boundaries).flatMap(b=>b.rings.map(r=>r.map(p=>[p[1],p[0]])));
 const cityBounds=L.latLngBounds(rings.flat());
 // An opaque outside mask retains the true district outlines, rather than a rectangular crop.
 const outer=cityBounds.pad(2);
 L.polygon([[outer.getSouthWest(),outer.getSouthEast(),outer.getNorthEast(),outer.getNorthWest()],...rings],{pane:'outside',stroke:false,fillColor:'#fff',fillOpacity:1,fillRule:'evenodd',interactive:false,smoothFactor:0}).addTo(map);
 map.setMaxBounds(cityBounds.pad(.15));
 const limitZoom=()=>map.setMinZoom(Math.max(8,Math.floor(map.getBoundsZoom(cityBounds,false,L.point(90,150)))));
 limitZoom();map.on('resize',limitZoom);
}
function fitRegion(){if(!state.data)return;map.stop();const code=$('#district').value;const rings=Object.entries(state.data.meta.boundaries||{}).filter(([id])=>!code||id===code).flatMap(([,b])=>b.rings.flatMap(r=>r.map(p=>[p[1],p[0]])));if(rings.length)map.fitBounds(rings,boundsOptions())}
function syncZoom(){const edge=map.getZoom()>=map.getMaxZoom()?'已到最大放大级别，可拖动或缩小':map.getZoom()<=map.getMinZoom()?'已到九区全景，可放大查看街道':'点击地点查看名称与地址';$('#map-hint').textContent=($('#basemap').value==='blank'?'空白底图':'本地街道地图')+' · '+edge;drawBoundaries()}
map.on('zoomend',syncZoom);
let boundaryStyleKey='';
function drawBoundaries(){if(!state.data)return;const styleKey=[$('#district').value,map.getZoom()>=12,$('#basemap').value].join(':');if(styleKey===boundaryStyleKey)return;boundaryStyleKey=styleKey;boundaries.clearLayers();const chosen=$('#district').value;const detailed=map.getZoom()>=12;for(const [code,b] of Object.entries(state.data.meta.boundaries||{})){const selected=chosen===code;for(const ring of b.rings){const polygon=L.polygon(ring.map(p=>[p[1],p[0]]),{pane:'districts',color:selected?'#576577':'#b1b9c3',weight:selected?2:1,fillColor:chosen&&!selected?'#f3f4f6':'#e9edf2',fillOpacity:$('#basemap').value!=='blank'?.025:chosen&&!selected?.18:.45,interactive:!detailed}).addTo(boundaries);polygon.on('click',()=>{if(!state.busy)chooseDistrict(code)});if(!detailed&&ring===b.rings.reduce((a,r)=>r.length>a.length?r:a,[]))polygon.bindTooltip(state.districts[code]||code,{permanent:true,direction:'center',className:'district-name'});}}}
function regionPois(){const code=$('#district').value;return (state.data?.pois||[]).filter(p=>!code||String(p.adcode)===code||p.district===state.districts[code])}
function storeVisible(category,brand){if(category==='target')return $('#show-target').checked;if(category==='competitor')return $('#show-competitor').checked&&(!$('#brand').value||brand===$('#brand').value);return $('#show-'+category)?.checked!==false}
function syncEvidence(){for(const marker of Object.values(evidenceMarkers)){const p=marker.poiData;if(storeVisible(p.category,p.brand)){if(!details.hasLayer(marker))details.addLayer(marker)}else{marker.closePopup();details.removeLayer(marker)}}}
function drawStores(){stores.clearLayers();const pois=regionPois();$('#target-count').textContent=pois.filter(p=>p.categories.includes('target')).length;$('#competitor-count').textContent=pois.filter(p=>p.categories.includes('competitor')).length;const brand=$('#brand').value;for(const p of pois){const cat=p.categories.includes('target')?'target':p.categories.includes('competitor')?'competitor':null;if(!cat||!storeVisible(cat,p.brand))continue;L.circleMarker([p.lat,p.lon],{radius:cat==='target'?5:3.6,color:'#fff',weight:1.2,fillColor:colors[cat],fillOpacity:.95}).bindPopup('<strong>'+esc(p.name)+'</strong><br>'+esc(p.district)+' · '+esc(p.address||'暂无详细地址')+'<br><small>'+names[cat]+'</small>').addTo(stores)}}
function clearResult(){state.result=null;details.clearLayers();selection.clearLayers();evidenceMarkers={};recMarker=null;queueFacilities();$('#result').innerHTML='<div class="initial-result">点击开始选址，查看推荐位置和周边依据。</div>';if(state.area)L.circle([state.area.lat,state.area.lon],{radius:state.area.radius_m,color:'#728aab',weight:1.5,dashArray:'5 5',fillOpacity:.03}).addTo(selection)}
function syncScope(){$('#scope-name').textContent=state.districts[$('#district').value]||'沈阳九区';$('#region-title').textContent=state.districts[$('#district').value]||'沈阳九区';$('#area-controls').hidden=!state.area;$('#selected-place').textContent=state.area?.name||''}
function chooseDistrict(code){if(state.busy)return;$('#district').value=code;state.area=null;$('#place-results').innerHTML='';$('#place-query').value='';clearResult();notify('');syncScope();drawBoundaries();drawStores();drawFacilities();fitRegion()}
$('#district').onchange=()=>chooseDistrict($('#district').value);$('#overview').onclick=()=>{chooseDistrict('');if(!state.busy){panel(false);fitRegion()}};
$('#toggle-plan').onclick=()=>panel($('#plan-panel').hidden);$('#close-plan').onclick=()=>panel(false);
$('#show-target').onchange=$('#show-competitor').onchange=$('#brand').onchange=()=>{drawStores();syncEvidence();queueFacilities()};
function setBusy(b){state.busy=b;for(const e of $$('#district,#overview,#place-query,#search-place,#area-size,#clear-place,#analyze,.place-result'))e.disabled=b;$('#analyze').textContent=b?'正在分析…':'开始选址'}
$('#place-form').onsubmit=async event=>{event.preventDefault();if(state.busy)return;setBusy(true);notify('');try{const r=await api('/api/places',{query:$('#place-query').value});state.places=r.places;$('#place-results').innerHTML=r.places.map((p,i)=>'<button class="place-result" data-place="'+i+'"><strong>'+esc(p.name)+'</strong><small>'+esc(p.district)+' · '+esc(p.address)+'</small></button>').join('')||'<p class="small">'+(r.outside?.length?'该地点不在沈阳九区内，请选择九区内的地点。':'未找到匹配地点，请补充名称后重试。')+'</p>';$$('.place-result').forEach(b=>b.onclick=()=>{if(state.busy)return;state.area={...state.places[Number(b.dataset.place)],radius_m:Number($('#area-size').value)};$('#district').value='';$('#place-results').innerHTML='';clearResult();syncScope();drawStores();drawBoundaries();map.fitBounds(L.latLng(state.area.lat,state.area.lon).toBounds(state.area.radius_m*2),boundsOptions())})}catch(e){notify(e.message)}finally{setBusy(false)}};
$('#area-size').onchange=()=>{if(state.area){state.area.radius_m=Number($('#area-size').value);clearResult();map.fitBounds(L.latLng(state.area.lat,state.area.lon).toBounds(state.area.radius_m*2),boundsOptions())}};
$('#clear-place').onclick=()=>{state.area=null;$('#place-query').value='';clearResult();syncScope();fitRegion()};
function focusPoint(marker){const p=marker.poiData;if(p&&!storeVisible(p.category,p.brand)){notify(facilitySymbols[p.category]?'该地点已隐藏，请先在“周边设施”中勾选'+names[p.category]+'。':'该门店已被地图筛选隐藏，请先勾选对应门店类型，并检查竞品品牌筛选。');return}notify('');const pos=marker.getLatLng();map.setView(pos,16);if(!$('#plan-panel').hidden&&innerWidth>580)map.panBy([innerWidth>850?210:185,0],{animate:false});if(innerWidth<=580)panel(false);marker.openPopup()}
function focusResult(){if(!recMarker)return;const point=state.result.plans[0].selected[0];map.fitBounds(L.latLng(point.lat,point.lon).toBounds(2000),boundsOptions());recMarker.openPopup()}
function evidenceList(cat,rows,title){return '<details class="evidence-list" '+(['school','competitor'].includes(cat)?'open':'')+'><summary>'+esc(title||names[cat])+' · '+rows.length+'处</summary>'+rows.map(p=>'<div class="poi-row"><span>'+Math.round(p.distance_m)+'米</span><button data-poi="'+esc(p.id)+'">'+esc(p.name)+'</button><small>'+esc(p.address||'暂无详细地址')+'</small></div>').join('')+(rows.length?'':'<p class="small">当前样本中未找到相关地点。</p>')+'</details>'}
function showResult(r){state.result=r;details.clearLayers();selection.clearLayers();evidenceMarkers={};recMarker=null;queueFacilities();if(r.status!=='recommended'){$('#result').innerHTML='<div class="result-heading"><h3>'+(r.status==='no_suitable'?'当前范围暂无合适位置':'当前数据不足以判断')+'</h3><p>'+esc(r.reason)+'</p><p>可以更换行政区或调整地点周边的选址范围。</p></div>';return}
const p=r.plans[0].selected[0],e=r.explanation;recMarker=L.marker([p.lat,p.lon],{icon:L.divIcon({className:'recommend-marker',html:'推荐',iconSize:[44,44],iconAnchor:[22,22]})}).bindPopup('<strong>推荐考察位置</strong><br>'+esc(e?.headline||p.anchor_name+'附近')+'<br><small>参考点，不代表有空置商铺</small>').addTo(selection);
L.circle([p.lat,p.lon],{radius:1000,color:'#576f92',weight:1,dashArray:'4 5',fillOpacity:.025}).addTo(selection);
let html='<div class="result-heading"><h3>'+esc(e?.headline||p.anchor_name+'附近')+'</h3><p>建议优先考察周边商业位置，实际铺面需要实地确认。</p></div><button class="focus-result" id="focus-result">定位推荐点</button><div class="result-facts"><div>学校<b>'+p.local_facilities.school+'</b></div><div>住宅小区<b>'+p.local_facilities.residential+'</b></div><div>茶饮竞品<b>'+p.competitors+'</b></div></div>';
if(e){html+='<h3>为什么选这里</h3><p>'+esc(e.selection_reason)+'</p>'+e.reasons.map(x=>'<section class="reason"><h4>'+esc(x.title)+'</h4><p>'+esc(x.text)+'</p></section>').join('');
const pats=e.patterns;if(pats?.stores_total&&pats.school_residential_pct!=null)html+='<h3>已有门店的布局特点</h3><p>在'+pats.stores_total+'家蜜雪冰城样本中，'+Number(pats.school_residential_pct).toFixed(1)+'%的门店周边1公里内同时有学校和住宅。这个现象可供选址参考，不代表经营收益。</p>';
html+='<h3>周边地点</h3><p class="small">点击名称在地图定位。距离为直线距离。</p>'+Object.entries(e.nearby).map(([cat,rows])=>evidenceList(cat,rows)).join('')+evidenceList('target',e.nearest_targets,'最近的蜜雪冰城');
const all=[...Object.entries(e.nearby).flatMap(([cat,rows])=>rows.map(p=>({...p,category:cat}))),...e.nearest_targets.map(p=>({...p,category:'target'}))];
for(const p of all){if(evidenceMarkers[p.id])continue;const m=evidenceMarker(p).bindTooltip(esc(p.name),{direction:'top',className:'evidence-label'}).bindPopup('<strong>'+esc(p.name)+'</strong><br>'+esc(names[p.category])+' · 距推荐点'+Math.round(p.distance_m)+'米<br>'+esc(p.address||''));m.poiData=p;if(storeVisible(p.category,p.brand))m.addTo(details);evidenceMarkers[p.id]=m}}
queueFacilities();$('#result').innerHTML=html;$('#focus-result').onclick=focusResult;$$('[data-poi]').forEach(b=>b.onclick=()=>{const m=evidenceMarkers[b.dataset.poi];if(m)focusPoint(m)});focusResult()}
$('#analyze').onclick=async()=>{if(!state.data||state.busy)return;clearResult();notify('');setBusy(true);try{const started=await api('/api/analyze',{dataset:state.data.id,districts:$('#district').value?[$('#district').value]:[],area:state.area,include_coffee:false});while(true){const job=await api('/api/jobs/'+started.job);if(job.done){if(job.error)throw Error(job.error);showResult(job.result);break}await new Promise(resolve=>setTimeout(resolve,700))}}catch(e){console.error(e.stack);$('#result').innerHTML='<div class="initial-result">'+esc(e.message)+'</div>'}finally{setBusy(false)}};
async function init(){try{const r=await api('/api/status');state.districts=r.districts;$('#district').innerHTML='<option value="">沈阳九区</option>'+Object.entries(r.districts).map(([id,name])=>'<option value="'+id+'">'+esc(name)+'</option>').join('');
// Use the newest completed city-wide nine-district dataset; never silently show a partial run.
const source=r.datasets.find(d=>d.status==='sample_ready'&&!d.meta.archived&&d.meta.classification_version&&!d.meta.area&&d.meta.districts?.length===9&&Object.keys(d.meta.boundaries||{}).length===9);
if(!source)throw Error('暂无可展示的九区门店数据。请联系项目维护人员。');state.data=await api('/api/datasets/'+source.id);const brands=[...new Set(state.data.pois.filter(p=>p.categories.includes('competitor')).map(p=>p.brand).filter(Boolean))].sort();$('#brand').innerHTML='<option value="">全部竞品品牌</option>'+brands.map(b=>'<option>'+esc(b)+'</option>').join('');restrictToShenyang();drawBoundaries();drawStores();drawFacilities();fitRegion();basemaps.setMode('streets');$('#analyze').disabled=false;}catch(e){notify(e.message)}}
showFacilityLegend();
prepareFacilities().then(init).catch(()=>notify('设施图标加载失败，请刷新页面'));



