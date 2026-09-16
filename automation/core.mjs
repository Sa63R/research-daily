import { createHmac, randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, existsSync, renameSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import WebSocket from 'ws';
import { isIP } from 'node:net';

export const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
export const PRIVATE=process.env.RESEARCH_DAILY_PRIVATE || resolve(ROOT,'.private');
export const sections=['保研信息','科研与学习','值得收藏','待核实'];
export function saveJson(file,data) {mkdirSync(dirname(file),{recursive:true});const tmp=file+'.tmp';writeFileSync(tmp,JSON.stringify(data,null,2),{mode:0o600});renameSync(tmp,file);}
export function loadJson(file,fallback=null) {try{return JSON.parse(readFileSync(file,'utf8').replace(/^\uFEFF/,''));}catch(error){if(error.code==='ENOENT')return fallback;throw error;}}
export function config() {
  mkdirSync(PRIVATE,{recursive:true});const file=resolve(PRIVATE,'config.json');
  if(!existsSync(file))saveJson(file,{groups:[],websocket:'ws://127.0.0.1:3001',token:randomBytes(32).toString('hex'),salt:randomBytes(32).toString('hex'),repository:'',napcatDir:'',qqAccount:'',enabled:false});
  const c=loadJson(file);if(!Array.isArray(c.groups)||!c.groups.length||!c.groups.every(g=>/^\d+$/.test(g)))throw Error('请先配置目标 QQ 群');
  const url=new URL(c.websocket);if(!['ws:','wss:'].includes(url.protocol)||!['127.0.0.1','localhost','[::1]'].includes(url.hostname))throw Error('QQ 接口只允许本机地址');
  if(!/^[\w.-]+\/[\w.-]+$/.test(c.repository))throw Error('GitHub 仓库配置无效');
  if(typeof c.token!=='string'||c.token.length<24||typeof c.salt!=='string'||c.salt.length<24)throw Error('本机密钥配置无效');return c;
}
export function chinaDay(ms=Date.now()) {return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(ms));}
export function yesterday(ms=Date.now()) {return chinaDay(ms-86400000);}
export function bounds(day) {if(!/^\d{4}-\d{2}-\d{2}$/.test(day))throw Error('日期无效');const start=Date.parse(`${day}T00:00:00+08:00`)/1000;if(!Number.isFinite(start)||chinaDay(start*1000)!==day)throw Error('日期无效');return {start,end:start+86400};}
export function redact(text) {
  return String(text).replace(/\[CQ:at,[^\]]*\]/g,'@群成员').replace(/\[CQ:[^\]]*\]/g,'[非文本内容未解析]')
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,'[邮箱]')
    .replace(/(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)/g,'[手机号]')
    .replace(/(?:QQ|qq|微信|微信号|VX|vx|wx|联系方式)\s*[:：号]?\s*[a-zA-Z0-9_-]{5,}/g,'[联系方式]')
    .replace(/https?:\/\/(?:qm\.qq\.com|jq\.qq\.com|wpa\.qq\.com|wpa\.qq\.com\.cn|u\.wechat\.com)\/[^\s]+/gi,'[联系链接]');
}
function decoded(value) {
  let result=String(value);
  for(let i=0;i<3;i++){try{const next=decodeURIComponent(result);if(next===result)break;result=next;}catch{break;}}
  return result;
}
function containsPrivateMarker(value,markers=[]) {
  const text=decoded(value);
  return /成员[a-f\d]{6}\b|\bm_[a-f\d]{24}\b/i.test(text)||markers.some(marker=>marker&&text.includes(String(marker)));
}
export function publicResourceUrl(value,markers=[]) {
  const url=new URL(value),host=url.hostname.toLowerCase().replace(/\.$/,'');
  if(!['https:','http:'].includes(url.protocol)||url.username||url.password)throw Error('资源链接协议或凭据无效');
  // Published resources must not point to a local service, a contact profile, or a signed private URL.
  if(isIP(host)||host.startsWith('[')||!host.includes('.')||/(^|\.)(localhost|local|internal|lan)$/.test(host))throw Error('不得公开本机或内部地址');
  if(/(^|\.)(?:wpa|qm|jq)\.qq\.com(?:\.cn)?$|(^|\.)user\.qzone\.qq\.com$|(^|\.)u\.wechat\.com$/.test(host))throw Error('不得公开联系链接');
  const privateKey=/^(?:uin|qq|qq_number|group_id|group_code|user_id|openid|unionid|wechat|wx|phone|mobile|telephone|email|access_token|refresh_token|token|auth|authorization|password|passwd|secret|api_key|apikey|signature|sig|x-amz-.+)$/i;
  const decodedUrl=decoded(url.href);
  const keys=[...url.searchParams.keys(),...new URLSearchParams(url.hash.slice(1)).keys(),...Array.from(decodedUrl.matchAll(/[?&#]([^?&#=]+)=/g),m=>m[1])];
  if(keys.some(key=>privateKey.test(decoded(key))))throw Error('不得公开身份或凭据参数');
  if(containsPrivateMarker(url.href,markers)||/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i.test(decodedUrl)||/(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)/.test(decodedUrl))throw Error('资源链接包含私人标识');
  return url.href;
}
export function publicText(value,markers=[]) {
  let text=String(value).replace(/https?:\/\/[^\s<>"`\[\]\\]+/gi,raw=>{
    const suffix=raw.match(/[),.;，。！？；、]+$/)?.[0]||'';
    const candidate=suffix?raw.slice(0,-suffix.length):raw;
    try{publicResourceUrl(candidate,markers);return raw;}catch{return '[私人链接已移除]'+suffix;}
  });
  text=redact(text).replace(/成员[a-f\d]{6}\b|\bm_[a-f\d]{24}\b/gi,'[已匿名]')
    .replace(/(?:群号|QQ群号|QQ号)\s*[:：]?\s*\d{5,12}/gi,'[已匿名]');
  for(const marker of markers)if(marker)text=text.split(String(marker)).join('[已匿名]');
  return text;
}
export function normalize(message,group,c) {
  if(String(message.group_id)!==group||message.message_type&&message.message_type!=='group'||message.post_type&&!['message','message_sent'].includes(message.post_type))return null;
  const time=Number(message.time);if(!Number.isSafeInteger(time)||time<946684800||time>Date.now()/1000+300)return null;
  if(message.message_id==null||message.user_id==null)return null;
  let text='';let hasUnread=false;
  if(Array.isArray(message.message)){text=message.message.map(s=>{if(s.type==='text')return String(s.data?.text||'');if(s.type==='at')return '@群成员';if(s.type==='face')return '[表情]';if(s.type==='reply')return '[引用]';hasUnread=true;return `[${({image:'图片未识别',record:'语音未转录',video:'视频未识别',file:'群文件未读取',forward:'转发未展开'})[s.type]||'非文本内容未解析'}]`;}).join('');}
  else text=typeof message.message==='string'?message.message:typeof message.raw_message==='string'?message.raw_message:'';
  if(!text.trim())return null;
  const hash=value=>createHmac('sha256',c.salt).update(value).digest('hex');
  const seq=/^\d+$/.test(String(message.real_seq||''))?String(message.real_seq):null;
  return {id:'m_'+hash(`${group}:${seq||`${time}:${message.user_id}:${text}`}`).slice(0,24),time,author:'成员'+hash(`${group}:${message.user_id}`).slice(0,6),text:redact(text).slice(0,20000),realSeq:seq,hasUnread};
}
export class QQReader {
  constructor(c){this.c=c;this.pending=new Map();this.sequence=0;}
  async open(){await new Promise((resolve,reject)=>{this.ws=new WebSocket(this.c.websocket,{headers:{Authorization:`Bearer ${this.c.token}`},handshakeTimeout:12000,maxPayload:12*1024*1024});this.ws.once('open',resolve);this.ws.once('error',reject);this.ws.on('message',bytes=>{let data;try{data=JSON.parse(bytes.toString());}catch{return;}const task=this.pending.get(data.echo);if(!task)return;clearTimeout(task.timer);this.pending.delete(data.echo);if(data.status==='ok'||data.retcode===0)task.resolve(data.data);else task.reject(Error('QQ 历史读取失败：'+String(data.message||data.wording||data.retcode).slice(0,250)));});this.ws.on('close',()=>{for(const p of this.pending.values()){clearTimeout(p.timer);p.reject(Error('QQ 接口已断开'));}this.pending.clear();});});}
  call(action,params={}){if(!['get_login_info','get_status','get_group_msg_history'].includes(action))return Promise.reject(Error('仅允许读取登录状态和群历史'));return new Promise((resolve,reject)=>{const echo=`read-${++this.sequence}`;const timer=setTimeout(()=>{this.pending.delete(echo);reject(Error('QQ 历史读取超时'));},action==='get_group_msg_history'?180000:30000);this.pending.set(echo,{resolve,reject,timer});try{this.ws.send(JSON.stringify({action,params,echo}));}catch(e){clearTimeout(timer);this.pending.delete(echo);reject(e);}});}
  close(){this.ws?.close();}
}
function rawSequence(m){try{return BigInt(m.real_seq);}catch{return 0n;}}
function earlier(a,b){const at=Number(a.time),bt=Number(b.time);return at<bt || at===bt&&rawSequence(a)<rawSequence(b);}
function earliest(messages){return messages.reduce((best,m)=>!best||earlier(m,best)?m:best,null);}
export async function readHistory(reader,c,group,day,{maxPages=500,pause=()=>new Promise(r=>setTimeout(r,350)),onProgress=()=>{}}={}) {
  const {start,end}=bounds(day);const collected=new Map();const seenCursors=new Set();let cursor,oldest,direction=true,probed=false,pages=0,boundary=false,reason='达到分页上限';let newestTime=null,oldestTime=null;
  while(pages<maxPages){
    let data;
    // A one-message initial view avoids QQ builds that stall on a large initial
    // load. Subsequent pages use the returned message ID and walk backwards.
    try{data=await reader.call('get_group_msg_history',{group_id:group,count:cursor==null?1:100,...(cursor!=null?{message_seq:String(cursor)}:{}),reverse_order:direction,disable_get_url:true,parse_mult_msg:false,quick_reply:true});}catch(error){reason=error.message;break;}
    pages++;
    const all=Array.isArray(data?.messages)?data.messages:[];
    const page=all.filter(m=>String(m.group_id)===group&&(!m.message_type||m.message_type==='group')&&Number.isSafeInteger(Number(m.time))&&Number(m.time)>946684800&&Number(m.time)<=Date.now()/1000+300);
    if(!page.length){reason='历史接口未返回可用消息';break;}
    const first=earliest(page);
    for(const m of page){oldestTime=oldestTime==null?Number(m.time):Math.min(oldestTime,Number(m.time));newestTime=newestTime==null?Number(m.time):Math.max(newestTime,Number(m.time));if(Number(m.time)>=start&&Number(m.time)<end){const normalized=normalize(m,group,c);if(normalized)collected.set(normalized.id,normalized);}}
    onProgress({pages,messageCount:collected.size,oldestTime,newestTime});
    if(Number(first.time)<start){boundary=true;reason='已读取到目标日期之前';break;}
    if(oldest&&!earlier(first,oldest)){
      if(!probed){direction=!direction;probed=true;await pause();continue;}
      reason='分页没有继续向更早消息推进';break;
    }
    oldest=first;const next=first.message_id??first.message_seq;
    if(next==null||seenCursors.has(String(next))){reason='历史游标缺失或重复';break;}
    seenCursors.add(String(next));cursor=next;await pause();
  }
  const messages=[...collected.values()].sort((a,b)=>a.time-b.time||a.id.localeCompare(b.id));
  const seqs=[...new Set(messages.filter(m=>m.realSeq).map(m=>m.realSeq))].map(BigInt).sort((a,b)=>a<b?-1:a>b?1:0);
  const gaps=[];for(let i=1;i<seqs.length;i++)if(seqs[i]-seqs[i-1]>1n)gaps.push({from:(seqs[i-1]+1n).toString(),to:(seqs[i]-1n).toString()});
  return {messages,coverage:{group:group,day,pages,firstReturnedAt:oldestTime,lastReturnedAt:newestTime,boundaryReached:boundary,reason,suspectedGaps:gaps,unreadMedia:messages.filter(m=>m.hasUnread).length,complete:false}};
}
export function validateReport(report,packet){
  if(!report||typeof report.title!=='string'||!report.title.trim()||typeof report.summary!=='string'||!Array.isArray(report.sections))throw Error('日报结构无效');
  const known=new Set(packet.messages.map(m=>m.id));const seen=new Set();
  for(const section of report.sections){if(!sections.includes(section.name)||seen.has(section.name)||!Array.isArray(section.items))throw Error('日报分类无效');seen.add(section.name);for(const item of section.items){if(typeof item.title!=='string'||typeof item.text!=='string'||!Array.isArray(item.evidenceIds)||!item.evidenceIds.length||!item.evidenceIds.every(id=>known.has(id)))throw Error('日报条目缺少有效消息依据');if(!Array.isArray(item.links))throw Error('资源链接无效');for(const link of item.links){const u=new URL(link.url);if(!['https:','http:'].includes(u.protocol)||u.username||u.password)throw Error('资源链接协议无效');if(typeof link.title!=='string')throw Error('资源链接名称无效');}}}
  // Apply the same public boundary to every visible field, including resource labels and the index summary.
  const privateMarkers=[...known,...new Set(packet.messages.map(m=>m.author).filter(Boolean)),...packet.coverage.map(c=>c.group).filter(Boolean)];
  for(const section of report.sections)for(const item of section.items){
    for(const link of item.links){link.url=publicResourceUrl(link.url,privateMarkers);link.title=publicText(link.title,privateMarkers);}
    for(const key of ['title','text','nextStep','basis'])if(typeof item[key]==='string')item[key]=publicText(item[key],privateMarkers);
  }
  for(const key of ['title','summary'])report[key]=publicText(report[key],privateMarkers);
  return report;
}
function mdText(text){return publicText(text).replace(/\\/g,'\\\\').replace(/[\[\]]/g,'\\$&').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
export function renderReport(report,packet){
  validateReport(report,packet);
  const lines=[`# ${packet.date} 保研与科研日报`,'',mdText(report.summary),''];
  for(const section of report.sections){if(!section.items.length)continue;lines.push(`## ${section.name}`,'');for(const item of section.items){lines.push(`### ${mdText(item.title)}`,'',mdText(item.text),'');if(item.nextStep)lines.push(`**怎么开始：** ${mdText(item.nextStep)}`,'');for(const link of item.links){const url=new URL(link.url).href.replace(/\(/g,'%28').replace(/\)/g,'%29');lines.push(`- [${mdText(link.title)}](${url})`);}if(item.links.length)lines.push('');if(item.basis)lines.push(`*${mdText(item.basis)}*`,'');}}
  if(!report.sections.some(s=>s.items.length))lines.push('今天已读取的消息中，没有筛选到符合主题的新信息。','');
  const warnings=packet.coverage.filter(c=>!c.boundaryReached||c.suspectedGaps.length);
  lines.push('---',`本期根据 ${packet.messages.length} 条已返回消息整理。QQ 离线历史可能存在缺失。${warnings.length?'本次检测到读取范围不足或疑似序号缺口。':''}${packet.coverage.some(c=>c.unreadMedia)?'图片、语音及未展开转发未纳入内容判断。':''}`,'');
  return lines.join('\n');
}
