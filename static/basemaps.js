function createBasemaps(map,ui){
 const extent=L.latLngBounds([39,120],[45,127]);
 const version=encodeURIComponent(ui.version||'1');
 const attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · <a href="https://protomaps.com">Protomaps</a>';
 const streets=protomapsL.leafletLayer({url:(document.querySelector('meta[name=app-base]')?.content||'')+'/maps/shenyang-streets.pmtiles?v='+version,flavor:'white',lang:'zh-Hans',maxDataZoom:15,maxNativeZoom:16,maxZoom:19,updateWhenZooming:false,updateWhenIdle:true,keepBuffer:1,bounds:extent,noWrap:true,attribution});
 const layers={streets};let mode='blank',active=null,timer;
 const states=new Map(Object.values(layers).map(layer=>[layer,{pending:new Set(),errors:new Set()}]));
 function hide(layer){const c=layer.getContainer();if(c)c.style.visibility='hidden'}
 function finish(layer){
  if(active!==layer)return;const s=states.get(layer);if(s.pending.size)return;
  clearTimeout(timer);
  if(s.errors.size){hide(layer);ui.status('本地底图读取失败，请重新加载。',true)}
  else{const c=layer.getContainer();if(c)c.style.visibility='visible';ui.status('')}
 }
 for(const layer of Object.values(layers)){
  const s=states.get(layer);
  layer.on('loading',()=>{if(active!==layer)return;hide(layer);ui.status('正在读取本地底图…');clearTimeout(timer);timer=setTimeout(()=>{if(active===layer&&s.pending.size){hide(layer);ui.status('本地底图读取较慢，可重新加载。',true)}},12000)});
  layer.on('tileloadstart',e=>{s.pending.add(e.tile);s.errors.delete(e.tile)});
  layer.on('tileload',e=>{s.pending.delete(e.tile);s.errors.delete(e.tile);finish(layer)});
  layer.on('tileerror',e=>{s.pending.delete(e.tile);s.errors.add(e.tile);if(active===layer){hide(layer);ui.status('本地底图读取失败，请检查地图文件是否完整。',true)}});
  layer.on('tileunload',e=>{s.pending.delete(e.tile);s.errors.delete(e.tile)});
  layer.on('load',()=>finish(layer));
 }
 function setMode(next){
  if(!['blank','streets'].includes(next))return;
  clearTimeout(timer);const old=active;active=null;
  if(old){map.removeLayer(old);states.get(old).pending.clear();states.get(old).errors.clear()}
  mode=next;active=layers[next]||null;ui.status('');
  if(active)active.addTo(map);ui.changed(mode);
 }
 return {setMode,retry(){const current=mode;setMode('blank');setMode(current)}};
}
if(typeof module!=='undefined')module.exports={createBasemaps};
