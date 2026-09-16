import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const html=await readFile(new URL('../pages/index.html',import.meta.url),'utf8');
const app=await readFile(new URL('../pages/app.js',import.meta.url),'utf8');
const config=await readFile(new URL('../pages/config.js',import.meta.url),'utf8');
const styles=await readFile(new URL('../pages/styles.css',import.meta.url),'utf8');
const markedSource=await readFile(new URL('../pages/vendor/marked.min.js',import.meta.url),'utf8');
for(const id of ['reader-view','report-content','date-switcher-current','search-input','theme-toggle']) assert.ok(html.includes(`id="${id}"`),`Missing reader control ${id}`);
assert.ok(!html.includes('已停止每日更新'));
assert.ok(!config.includes('data.csbaoyan.icelon.top'),'Must not read another community’s reports');
const context=vm.createContext({window:{CSBAOYAN_CONFIG:{dataBaseUrl:'.'}}});
vm.runInContext(app.slice(0,app.indexOf('const elements =')),context);
const actual=vm.runInContext(`normalizeManifest([{date:'2026-09-15',md_path:'reports/2026-09-15.md'},{date:'2026-09-15',md_path:'reports/2026-09-15.md'},{date:'2026-09-16',md_path:'https://malicious.example/report.md'},{date:'../../secret',md_path:'reports/../../secret.md'}])`,context);
assert.equal(actual.length,1,'Reject duplicates and paths outside the report directory');
assert.equal(vm.runInContext("dataUrl('reports.json')",context),'./reports.json');

const newReport = `# 2026-09-15 保研与科研日报

## 今日值得关注

### 院校与项目

**北航软件名单发布**：先核对[学院通知](https://example.edu/notice)。

### 申请与考核

**安排考核行程**：分别记录报到和面试时间。

### 经验与选择

**候补尚未确定**：先核对已有选择。

### 科研与学习

**控制变量实验**：固定画面，只改变声音。

## 今日讨论脉络

### 08:00–09:00｜北航报名与审核

讨论区分报名名单和录取结果。

- 先查看系统状态。
- 再核对个人通知。

**讨论状态：** 有通知依据，具体批次仍需核对。

## 传闻与待核实

### 机试日期的不同说法

**不确定性：** 群内日期说法不一致。

**建议核实：** 查看本人通知。
`;
const searchResults={innerHTML:''};
const sanitizationCalls=[];
const readerContext=vm.createContext({
  window:{CSBAOYAN_CONFIG:{dataBaseUrl:'.'},addEventListener(){}},
  document:{querySelector:selector=>selector==='#search-results'?searchResults:null},
});
vm.runInContext(markedSource,readerContext);
readerContext.window.marked=readerContext.marked;
readerContext.window.DOMPurify={sanitize(raw,options){sanitizationCalls.push({raw,options});return 'sanitized output';}};
vm.runInContext(app.slice(0,app.lastIndexOf('\ninitTheme();')),readerContext);
readerContext.newReport=newReport;
assert.equal(vm.runInContext('renderMarkdown(newReport)',readerContext),'sanitized output','Always return the sanitizer output');
const rendered=sanitizationCalls.at(-1);
for(const heading of ['今日值得关注','今日讨论脉络','传闻与待核实'])assert.ok(rendered.raw.includes(`<h2>${heading}</h2>`));
for(const heading of ['院校与项目','申请与考核','经验与选择','科研与学习','08:00–09:00｜北航报名与审核'])assert.ok(rendered.raw.includes(`<h3>${heading}</h3>`));
assert.ok(rendered.raw.includes('<strong>北航软件名单发布</strong>'));
assert.ok(rendered.raw.includes('<li>先查看系统状态。</li>'));
assert.ok(rendered.raw.includes('<strong>讨论状态：</strong>'));
for(const tag of ['h2','h3','strong','ul','li','a'])assert.ok(rendered.options.ALLOWED_TAGS.includes(tag),`${tag} is needed by the report format`);
for(const tag of ['script','style','img','svg','iframe','form','input'])assert.ok(!rendered.options.ALLOWED_TAGS.includes(tag),`${tag} must not enter a report`);
for(const attr of ['style','onclick','onerror','src','id','name'])assert.ok(!rendered.options.ALLOWED_ATTR.includes(attr));
assert.equal(rendered.options.ALLOW_DATA_ATTR,false);
assert.equal(rendered.options.ALLOW_ARIA_ATTR,false);
assert.match(styles,/\.report-content h3\s*\{/);
assert.match(styles,/\.report-content li \+ li\s*\{/);
assert.ok(!app.includes('report-toc'),'Preserve the original reader without adding a table of contents');

// Check section selection separately from browser DOM text extraction.
vm.runInContext('markdownPlainText = text => text',readerContext);
assert.equal(vm.runInContext('extractOverview(newReport)',readerContext),'**北航软件名单发布**：先核对[学院通知](https://example.edu/notice)。');
assert.equal(vm.runInContext('extractOverview(newReport.replaceAll("\\n", "\\r\\n"))',readerContext),'**北航软件名单发布**：先核对[学院通知](https://example.edu/notice)。');
assert.match(vm.runInContext('extractOverview("# 空日报")',readerContext),/概览暂不可用/);

vm.runInContext(`state.manifest=[{date:'2026-09-15',md_path:'reports/2026-09-15.md'}]; state.reportsCache['2026-09-15']=newReport; performSearch('08:00–09:00 北航');`,readerContext);
assert.ok(searchResults.innerHTML.includes('href="#2026-09-15"'),'Search keeps date navigation');
assert.ok(searchResults.innerHTML.includes('<mark>08:00–09:00</mark>'),'Timeline text remains searchable');
vm.runInContext("performSearch('控制变量 实验')",readerContext);
assert.ok(searchResults.innerHTML.includes('search-result-item'),'New research category remains searchable');
vm.runInContext("performSearch('讨论状态')",readerContext);
assert.ok(searchResults.innerHTML.includes('<mark>讨论状态</mark>'),'Bold status labels remain searchable');
readerContext.unsafeText='搜索样例 <img src=x onerror="alert(1)">';
vm.runInContext("state.reportsCache['2026-09-15']=unsafeText; performSearch('搜索样例')",readerContext);
assert.ok(!searchResults.innerHTML.includes('<img'),'Search snippets escape report HTML');
assert.ok(searchResults.innerHTML.includes('&lt;img'));
console.log('Reader, manifest, new report structure, search and sanitizer boundary checks passed');
