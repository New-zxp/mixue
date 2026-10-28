const assert=require('node:assert/strict');
const {createBasemaps}=require('../static/basemaps.js');
const layers=[];
class Layer{
 constructor(options){this.options=options;this.events={};this.container={style:{}};layers.push(this)}
 on(name,fn){this.events[name]=fn;return this}
 fire(name,event={}){this.events[name]?.(event)}
 getContainer(){return this.container}
 addTo(map){map.add(this);this.fire('loading');return this}
}
global.L={latLngBounds:()=>({}),GridLayer:{extend:()=>Layer}};
global.protomapsL={leafletLayer:options=>new Layer(options)};
global.pmtiles={PMTiles:class{constructor(url){assert.ok(url.startsWith('/maps/'))}}};
const shown=new Set(),map={add:l=>shown.add(l),removeLayer:l=>shown.delete(l)};
let message='',retry=false;
const control=createBasemaps(map,{status:(m,r=false)=>{message=m;retry=r},changed(){}});
control.setMode('streets');const street=layers[0],a={},b={};
street.fire('tileloadstart',{tile:a});street.fire('tileloadstart',{tile:b});
street.fire('tileerror',{tile:a});street.fire('tileload',{tile:b});street.fire('load');
assert.equal(street.container.style.visibility,'hidden');assert.equal(retry,true);
street.fire('tileloadstart',{tile:a});street.fire('tileload',{tile:a});street.fire('load');
assert.equal(street.container.style.visibility,'visible');assert.equal(message,'');
control.setMode('blank');assert.equal(shown.size,0);assert.equal(message,'');
street.fire('load');assert.equal(message,'');
control.retry();assert.equal(shown.size,0);
control.setMode('terrain');assert.equal(shown.size,0);
control.setMode('streets');assert.equal(shown.size,1);
control.setMode('blank');
console.log('Offline maps: street/blank switching, rejected terrain, mixed failure, recovery and stale events passed.');
