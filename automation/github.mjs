import { spawn } from 'node:child_process';
import { publicText } from './core.mjs';

export function command(executable,args,{input='',cwd,timeout=120000}={}){
  return new Promise((resolve,reject)=>{const child=spawn(executable,args,{cwd,windowsHide:true,stdio:['pipe','pipe','pipe']});let stdout='',stderr='';const timer=setTimeout(()=>{child.kill();reject(Error('外部命令执行超时'));},timeout);child.stdout.on('data',d=>stdout+=d.toString());child.stderr.on('data',d=>stderr+=d.toString());child.on('error',e=>{clearTimeout(timer);reject(e);});child.on('close',code=>{clearTimeout(timer);code===0?resolve(stdout):reject(Error(`${executable} 执行失败 (${code})：${stderr.slice(-1000)}`));});child.stdin.on('error',()=>{});child.stdin.end(input);});
}
async function api(path,body){const args=['api',path];if(body!==undefined)args.push('--method','POST','--input','-');const output=await command('gh',args,{input:body===undefined?'':JSON.stringify(body)});return output.trim()?JSON.parse(output):null;}
export function reportIndexEntry(date,summary){return {date,md_path:`reports/${date}.md`,summary:publicText(summary)};}
export async function publish(repo,date,markdown,summary){
  if(!/^[\w.-]+\/[\w.-]+$/.test(repo)||!/^\d{4}-\d{2}-\d{2}$/.test(date))throw Error('发布目标无效');
  markdown=publicText(markdown);
  for(let attempt=0;attempt<3;attempt++){
    const ref=await api(`repos/${repo}/git/ref/heads/main`);
    const commit=await api(`repos/${repo}/git/commits/${ref.object.sha}`);
    const file=await api(`repos/${repo}/contents/pages/reports.json?ref=${ref.object.sha}`);
    const manifest=JSON.parse(Buffer.from(file.content,'base64').toString('utf8'));
    if(!Array.isArray(manifest))throw Error('线上日报索引无效');
    const next=[...manifest.filter(r=>r.date!==date),reportIndexEntry(date,summary)].sort((a,b)=>b.date.localeCompare(a.date));
    const tree=await api(`repos/${repo}/git/trees`,{base_tree:commit.tree.sha,tree:[{path:`pages/reports/${date}.md`,mode:'100644',type:'blob',content:markdown},{path:'pages/reports.json',mode:'100644',type:'blob',content:JSON.stringify(next,null,2)+'\n'}]});
    const created=await api(`repos/${repo}/git/commits`,{message:`Publish daily report ${date}`,tree:tree.sha,parents:[ref.object.sha]});
    try{await command('gh',['api',`repos/${repo}/git/refs/heads/main`,'--method','PATCH','--input','-'],{input:JSON.stringify({sha:created.sha,force:false})});return created.sha;}catch(error){if(attempt===2)throw error;}
  }
}
