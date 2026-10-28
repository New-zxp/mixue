const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
const controls={'#count-school':{},'#count-office':{}};
let school=true,office=true,created=0;
const rows=[{id:'a',lat:41,lon:123,categories:['school']},{id:'b',lat:40,lon:120,categories:['school']},{id:'c',lat:41,lon:123,categories:['office','school']}];
const markers=new Map(),displayed=new Set();
class Point{constructor(pos,opt){created++;this.options=opt;this.radius=opt.radius}bindPopup(){return this}addTo(){displayed.add(this);return this}getRadius(){return this.radius}setRadius(r){this.radius=r}}
const evidence={};let zoom=11;
const context=vm.createContext({state:{data:{}},regionPois:()=>rows,facilitySymbols:{school:1,office:1},facilityMarkers:markers,evidenceMarkers:evidence,
 details:{hasLayer:()=>true},facilityCanvas:{},FacilityPoint:Point,$:s=>controls[s],storeVisible:c=>c==='school'?school:office,
 map:{getBounds:()=>({pad:()=>({contains:p=>p[1]===123})}),getZoom:()=>zoom,removeLayer:m=>displayed.delete(m)}});
vm.runInContext(source.slice(source.indexOf('function drawFacilities(){'),source.indexOf("map.on('moveend',queueFacilities)")),context);
const draw=()=>vm.runInContext('drawFacilities()',context);
draw();assert.equal(markers.size,2);assert.equal(created,2);assert.equal(controls['#count-school'].textContent,3);
draw();assert.equal(created,2); // Panning/refresh reuses paths rather than creating DOM icons.
school=false;draw();assert.equal(markers.size,1);assert.ok(markers.has('c'));
office=false;draw();assert.equal(displayed.size,0);
school=true;office=true;evidence.a={};zoom=19;draw();assert.equal(markers.size,1);assert.equal(markers.get('c').radius,11);
console.log('Facility regression: viewport culling, category counts, cached paths, hide-all and evidence deduplication passed.');
