import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const html=await readFile(new URL('../pages/index.html',import.meta.url),'utf8');
const app=await readFile(new URL('../pages/app.js',import.meta.url),'utf8');
const config=await readFile(new URL('../pages/config.js',import.meta.url),'utf8');
for(const id of ['reader-view','report-content','date-switcher-current','search-input','theme-toggle']) assert.ok(html.includes(`id="${id}"`),`Missing reader control ${id}`);
assert.ok(!html.includes('已停止每日更新'));
assert.ok(!config.includes('data.csbaoyan.icelon.top'),'Must not read another community’s reports');
const context=vm.createContext({window:{CSBAOYAN_CONFIG:{dataBaseUrl:'.'}}});
vm.runInContext(app.slice(0,app.indexOf('const elements =')),context);
const actual=vm.runInContext(`normalizeManifest([{date:'2026-09-15',md_path:'reports/2026-09-15.md'},{date:'2026-09-15',md_path:'reports/2026-09-15.md'},{date:'2026-09-16',md_path:'https://malicious.example/report.md'},{date:'../../secret',md_path:'reports/../../secret.md'}])`,context);
assert.equal(actual.length,1,'Reject duplicates and paths outside the report directory');
assert.equal(vm.runInContext("dataUrl('reports.json')",context),'./reports.json');
console.log('Reader and manifest checks passed');
