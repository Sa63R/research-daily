import test from 'node:test';
import assert from 'node:assert/strict';
import { bounds,yesterday,normalize,readHistory,validateReport,renderReport,QQReader,publicResourceUrl } from '../core.mjs';
import { reportIndexEntry } from '../github.mjs';

const c={groups:['123456'],salt:'test-salt-not-production'};
const day='2026-09-15',{start,end}=bounds(day);
function raw(id,time,text='测试消息',extra={}){return {group_id:123456,message_type:'group',post_type:'message',message_id:id,real_seq:String(id),time,user_id:88888,message:[{type:'text',data:{text}}],...extra};}
test('Shanghai natural day boundaries are independent of machine timezone',()=>{assert.equal(new Date(start*1000).toISOString(),'2026-09-14T16:00:00.000Z');assert.equal(yesterday(Date.parse('2026-09-15T16:10:00Z')),'2026-09-15');assert.throws(()=>bounds('2026-02-30'));});
test('private and foreign-group messages cannot enter a packet',()=>{assert.equal(normalize(raw(1,start,'secret',{group_id:999999}),'123456',c),null);assert.equal(normalize(raw(1,start,'secret',{message_type:'private'}),'123456',c),null);const m=normalize(raw(1,start,'邮箱 a@b.com，https://wpa.qq.com/msgrd?v=3&uin=88888'), '123456',c);assert.ok(!m.text.includes('a@b.com'));assert.ok(!m.text.includes('uin='));assert.ok(!JSON.stringify(m).includes('88888'));});
test('history uses returned short ID without decrement and excludes today',async()=>{const calls=[];const pages=[[raw(900,end+1)],[raw(900,end+1),raw(800,start+100,'有效信息')],[raw(800,start+100),raw(700,start-1)]];const reader={call:async(action,args)=>{calls.push(args);return {messages:pages.shift()};}};const result=await readHistory(reader,c,'123456',day,{pause:async()=>{}});assert.equal(calls[0].count,1);assert.equal(calls[1].message_seq,'900');assert.equal(calls[1].reverse_order,true);assert.equal(calls[2].message_seq,'800');assert.equal(result.messages.length,1);assert.equal(result.coverage.boundaryReached,true);assert.equal(result.coverage.complete,false);});
test('stalled pagination is a gap, never silently a complete day',async()=>{const reader={call:async()=>({messages:[raw(900,start+100)]})};const r=await readHistory(reader,c,'123456',day,{pause:async()=>{}});assert.equal(r.coverage.boundaryReached,false);assert.match(r.coverage.reason,/推进/);});
test('real-sequence gaps survive a successful date-boundary crossing',async()=>{const reader={call:async()=>({messages:[raw(99,start+100),raw(95,start+90),raw(90,start-10)]})};const r=await readHistory(reader,c,'123456',day,{pause:async()=>{}});assert.equal(r.coverage.suspectedGaps[0].from,'96');assert.equal(r.coverage.suspectedGaps[0].to,'98');});
test('reject fabricated evidence and executable resource links',()=>{const packet={date:day,messages:[{id:'m_known'}],coverage:[{boundaryReached:true,suspectedGaps:[],unreadMedia:0}]};const r={title:'日报',summary:'摘要',sections:[{name:'科研与学习',items:[{title:'方法',text:'实验建议',nextStep:'',basis:'群友经验',evidenceIds:['m_fake'],links:[]}]}]};assert.throws(()=>validateReport(r,packet));r.sections[0].items[0].evidenceIds=['m_known'];r.sections[0].items[0].links=[{title:'x',url:'javascript:alert(1)'}];assert.throws(()=>validateReport(r,packet));r.sections[0].items[0].links=[];assert.ok(!renderReport(r,packet).includes('m_known'));});
test('QQ connection cannot invoke sending or membership-changing actions',async()=>{const reader=new QQReader({});await assert.rejects(reader.call('send_group_msg',{group_id:123456,message:'x'}));await assert.rejects(reader.call('set_group_leave',{group_id:123456}));});

function publicationFixture(){
  const id='m_0123456789abcdef01234567',author='成员a1b2c3',group='123456789';
  const packet={date:day,messages:[{id,author}],coverage:[{group,boundaryReached:true,suspectedGaps:[],unreadMedia:0}]};
  const privateText=`${group} ${id} ${author} 联系 researcher@example.com 13812345678`;
  const report={title:privateText,summary:privateText,sections:[{name:'科研与学习',items:[{title:privateText,text:privateText,nextStep:privateText,basis:privateText,evidenceIds:[id],links:[{title:privateText,url:'https://arxiv.org/abs/2501.12345'}]}]}]};
  return {packet,report,privateValues:[group,id,author,'researcher@example.com','13812345678']};
}
test('published Markdown and homepage index remove identities from every visible field',()=>{
  const {packet,report,privateValues}=publicationFixture();
  const markdown=renderReport(report,packet),index=reportIndexEntry(day,report.summary);
  for(const secret of privateValues){assert.ok(!markdown.includes(secret),`Markdown contains ${secret}`);assert.ok(!JSON.stringify(index).includes(secret),`index contains ${secret}`);}
  assert.equal(index.md_path,`reports/${day}.md`);
  assert.ok(markdown.includes('https://arxiv.org/abs/2501.12345'));
  assert.ok(markdown.includes('\\[已匿名\\]'));
  assert.equal(renderReport(report,packet),markdown,'repeated rendering must remain stable');
});
test('resource URLs reject contact addresses, encoded identities and signed private URLs',()=>{
  const {packet,report}=publicationFixture(),item=report.sections[0].items[0];
  const blocked=[
    'https://wpa.qq.com.cn/msgrd?uin=88888',
    'https://example.com/resource?UIN=88888',
    'https://example.com/resource?%75in=88888',
    'https://example.com/%31%32%33%34%35%36%37%38%39',
    'https://example.com/member/%E6%88%90%E5%91%98a1b2c3',
    'https://example.com/resource?access_token=secret',
    'https://example.com/resource#access_token=secret',
    'https://example.com/#/resource?token=secret',
    'https://example.com/resource?X-Amz-Signature=secret',
    'https://example.com/researcher%40example.com',
    'https://example.com/13812345678',
    'https://account:password@example.com/resource',
    'http://2130706433/resource',
    'http://[::1]/resource',
    'http://computer.local/resource',
  ];
  for(const url of blocked){item.links=[{title:'资源',url}];assert.throws(()=>validateReport(report,packet),undefined,url);}
  for(const url of ['https://arxiv.org/abs/2501.12345','https://stanford-cs336.github.io/spring2025/','https://github.com/example/project?tab=readme-ov-file#readme'])assert.equal(publicResourceUrl(url),url);
});
test('inline prose cannot bypass link checks with Markdown, images or HTML',()=>{
  const {packet,report}=publicationFixture();
  report.summary='[联系](https://wpa.qq.com.cn/msgrd?uin=88888)';
  report.sections[0].items[0].text='![图片](https://example.com/pixel.png) <img src="https://example.com/image.png"> [私有资源](https://example.com/?token=secret)';
  const markdown=renderReport(report,packet);
  assert.ok(!markdown.includes('uin='));assert.ok(!markdown.includes('token=secret'));
  assert.ok(!markdown.includes('![图片]'));assert.ok(!markdown.includes('<img'));
  assert.ok(markdown.includes('!\\[图片\\]'));
  const directIndex=reportIndexEntry(day,'成员abcdef m_0123456789abcdef01234567 邮箱 x@example.com 群号123456789 https://example.com/?token=secret');
  for(const value of ['成员abcdef','m_0123456789abcdef01234567','x@example.com','123456789','token=secret'])assert.ok(!directIndex.summary.includes(value));
});
