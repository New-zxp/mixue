// Regression: ordinary shops and recommendation evidence share the same filters.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const controls = {'#show-target': {checked:true}, '#show-competitor': {checked:true}, '#brand': {value:''}};
const layers = new Set();
const markers = Object.fromEntries(['target','competitor','school','residential'].map(category => [category, {
  poiData:{category,brand:category==='competitor'?'茶百道':'蜜雪冰城'}, closePopup(){this.closed=true;}
}]));
const context = vm.createContext({$:id=>controls[id], evidenceMarkers:markers,
  details:{hasLayer:m=>layers.has(m),addLayer:m=>layers.add(m),removeLayer:m=>layers.delete(m)}});
for (const name of ['storeVisible','syncEvidence']) {
  const line=source.split('\n').find(line=>line.startsWith(`function ${name}(`));
  assert.ok(line, name);vm.runInContext(line,context);
}
const sync=()=>vm.runInContext('syncEvidence()',context);
sync();assert.equal(layers.size,4);
controls['#show-target'].checked=false;controls['#show-competitor'].checked=false;
sync();assert.deepEqual([...layers].map(m=>m.poiData.category),['school','residential']);
assert.ok(markers.target.closed && markers.competitor.closed);
controls['#show-competitor'].checked=true;controls['#brand'].value='霸王茶姬';
sync();assert.equal(layers.has(markers.competitor),false);
controls['#brand'].value='茶百道';sync();assert.equal(layers.has(markers.competitor),true);
controls['#show-target'].checked=true;sync();assert.equal(layers.size,4);
assert.ok(source.includes('if(!cat||!storeVisible(cat,p.brand))continue;'));
assert.ok(source.includes('if(storeVisible(p.category,p.brand))m.addTo(details)'));
console.log('Map filter regression passed: hide, restore, brand filter, facilities retained.');
