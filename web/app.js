import {aggregate, compact, connectionCommand, csvCell, shiftDay, yesterday} from './logic.js';

const $=id=>document.getElementById(id);
let realData={repo:'OWAngel/token-arena',participants:[],reports:[]}, data=realData, demo=false, expanded=null;
let view={day:yesterday(),days:1,model:'',search:'',metric:'total_tokens'};
const el=(tag,cls,value)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=value;return n;};
const exact=n=>n.toLocaleString('en-US');
const rate=(c,i)=>i ? `${(100*c/i).toFixed(1)}%` : '—';

function sampleData() {
  const names=['北极星','小林的实验室','阿树','橘子汽水','向晚','白噪声','山海','云边'];
  const models=['DeepSeek-V4.1-Flash','Qwen3.5-397B','GLM-5','MiniMax-M2.5'];
  const base=yesterday(), participants=names.map((name,i)=>({id:String(i),github:`demo-spark-${i+1}`,wechat_name:name,issue:i+1}));
  const reports=[];
  for(let d=0;d<7;d++)for(let i=0;i<names.length;i++){
    const input=Math.round(28000000/(i+1)*(1+Math.sin(d+i)*.4));
    const output=Math.round(input*(.06+(i%3)*.03));
    reports.push({...participants[i],date:shiftDay(base,-d),coverage:'recorded-window',models:[{model:models[i%4],input_tokens:input,output_tokens:output,cached_input_tokens:Math.round(input*.73),total_tokens:input+output}]});
  }
  return {repo:'OWAngel/token-arena',participants,reports};
}

function render() {
  const result=aggregate(data,view);
  $('total').textContent=compact(result.totals.total_tokens);$('output').textContent=compact(result.totals.output_tokens);
  $('people').textContent=result.ranking.length;$('models').textContent=result.models.length;
  $('scope').textContent=`${view.days===1?view.day:`${shiftDay(view.day,1-view.days)} → ${view.day}`} · 北京时间`;
  $('enrolled').textContent=`共 ${data.participants.length} 位自愿参加者`;$('row-count').textContent=`${result.ranking.length} 人`;
  $('ranking').replaceChildren();$('empty').hidden=result.ranking.length>0;
  $('empty-copy').textContent=(view.search||view.model)?'当前筛选没有匹配的记录。试试其他昵称、模型或日期。':'还没有这个日期的公开上报。连接自己的 sparkDash，让昨天的用量出现在这里。';
  result.ranking.forEach((u,index)=>{
    const row=el('tr','data-row');const rank=el('td');rank.append(el('span',`rank-number${index<3?' top':''}`,String(index+1).padStart(2,'0')));row.append(rank);
    const cell=el('td'),person=el('div','person'),label=el('div');person.append(el('span','avatar',[...u.wechat_name].slice(0,1).join('')));
    label.append(el('strong','',u.wechat_name),el('small','',`@${u.github}`));person.append(label);cell.append(person);row.append(cell);
    const sorted=[...u.models.values()].sort((a,b)=>b.total_tokens-a.total_tokens),modelCell=el('td');
    const pill=el('span','model-pill',sorted[0]?.model||'—');pill.title=sorted.map(m=>m.model).join(', ');modelCell.append(pill);row.append(modelCell);
    const amount=el('td','numeric amount',compact(u.total_tokens));amount.title=exact(u.total_tokens);row.append(amount);
    row.append(el('td','numeric optional',compact(u.output_tokens)),el('td','numeric optional',rate(u.cached_input_tokens,u.input_tokens)));
    const action=el('td'),button=el('button','expand',expanded===u.id?'−':'+');button.setAttribute('aria-label',`展开 ${u.wechat_name} 的模型明细`);button.setAttribute('aria-expanded',String(expanded===u.id));
    button.addEventListener('click',()=>{expanded=expanded===u.id?null:u.id;render();const active=[...document.querySelectorAll('.expand')].find(b=>b.getAttribute('aria-label')===`展开 ${u.wechat_name} 的模型明细`);active?.focus({preventScroll:true});});action.append(button);row.append(action);$('ranking').append(row);
    if(expanded===u.id){
      const detail=el('tr'),td=el('td','detail-cell');td.colSpan=7;const content=el('div','detail-content');
      content.append(el('p','',`已报 ${u.dates.size} / ${view.days} 天 · ${u.partial?'含覆盖不足的日期 · ':''}sparkDash 实例记录用量（包含缓存输入）`));
      for(const m of sorted){const line=el('div','detail-model');line.append(el('span','',m.model),el('span','',`输入 ${exact(m.input_tokens)} · 输出 ${exact(m.output_tokens)} · 缓存 ${exact(m.cached_input_tokens)}`));content.append(line);}
      if(!demo)for(const issue of u.issueNumbers){const link=el('a','text-button',`查看公开报告 #${issue} ↗`);link.href=`https://github.com/${data.repo}/issues/${issue}`;link.target='_blank';link.rel='noopener noreferrer';content.append(link);}
      td.append(content);detail.append(td);$('ranking').append(detail);
    }
  });
  $('model-list').replaceChildren();$('model-empty').hidden=result.models.length>0;
  const modelMax=result.models[0]?.total_tokens||1;
  for(const m of result.models.slice(0,5)){const li=el('li'),name=el('div','model-name');const text=el('span','',m.model);text.title=m.model;name.append(text,el('span','mono',compact(m.total_tokens)));const track=el('div','model-track'),bar=el('i');bar.style.width=`${100*m.total_tokens/modelMax}%`;track.append(bar);li.append(name,track);$('model-list').append(li);}
  $('trend').replaceChildren();const trend=[];
  for(let i=6;i>=0;i--){const day=shiftDay(view.day,-i);const t=aggregate(data,{...view,day,days:1,search:'',model:''}).totals.total_tokens;trend.push({day,total:t});}
  const max=Math.max(1,...trend.map(t=>t.total));
  for(const t of trend){const column=el('div','trend-column'),space=el('div','bar-space'),bar=el('div','bar');bar.style.height=`${Math.max(2,94*t.total/max)}px`;column.title=`${t.day}: ${exact(t.total)} Token`;space.append(bar);column.append(space,el('small','',t.day.slice(5)));$('trend').append(column);}
  $('export').disabled=!result.ranking.length;
}

function updateOptions(){
  const options=[...new Set(data.reports.flatMap(r=>r.models.map(m=>m.model)))].sort();
  $('model-filter').replaceChildren(new Option('全部模型',''),...options.map(m=>new Option(m,m)));
  view.model='';$('model-filter').value='';
}
function toggleDemo(force){
  demo=typeof force==='boolean'?force:!demo;data=demo?sampleData():realData;
  $('demo-note').hidden=!demo;$('demo-toggle').textContent=demo?'返回真实榜单 ↗':'看看演示数据 ↗';
  expanded=null;updateOptions();render();
}
function joinCommand(){
  const name=$('join-name').value.trim(),url=$('join-url').value.trim();let valid=false;
  try{const p=new URL(url);valid=!!name&&name.length<=40&&!/[\x00-\x1f\x7f-\x9f]/.test(name+url)&&['http:','https:'].includes(p.protocol)&&!p.username&&!p.password&&!p.search&&!p.hash&&$('consent').checked;}catch{/* Incomplete local form; no request is made. */}
  $('copy-command').disabled=!valid;
  $('join-command').textContent=valid?connectionCommand(name,url,data.repo):'填写有效的昵称、http(s) 地址并勾选同意后生成命令。';$('copy-status').textContent='';
}
$('date').value=view.day;$('date').max=yesterday();$('date').min='2026-01-01';
document.querySelectorAll('[data-days]').forEach(button=>button.addEventListener('click',()=>{view.days=Number(button.dataset.days);document.querySelectorAll('[data-days]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));render();}));
$('search').addEventListener('input',e=>{view.search=e.target.value;render();});
$('model-filter').addEventListener('change',e=>{view.model=e.target.value;render();});
$('metric').addEventListener('change',e=>{view.metric=e.target.value;render();});
$('date').addEventListener('change',e=>{if(e.target.validity.valid&&e.target.value){view.day=e.target.value;render();}});
$('demo-toggle').addEventListener('click',()=>toggleDemo());$('exit-demo').addEventListener('click',()=>toggleDemo(false));
document.querySelectorAll('.join-trigger').forEach(button=>button.addEventListener('click',()=>$('join-dialog').showModal()));
document.querySelector('.close-dialog').addEventListener('click',()=>$('join-dialog').close());
for(const id of ['join-name','join-url','consent'])$(id).addEventListener('input',joinCommand);
$('copy-command').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('join-command').textContent);$('copy-status').textContent='已复制到剪贴板';}catch{$('copy-status').textContent='请选中命令并手动复制';}});
$('export').addEventListener('click',()=>{
  const rows=[['mode','end_date','days','wechat_name','github','model','input_tokens','output_tokens','cached_input_tokens','total_tokens','reported_days']];
  for(const u of aggregate(data,view).ranking)for(const m of u.models.values())rows.push([demo?'DEMO':'self-reported',view.day,view.days,u.wechat_name,u.github,m.model,m.input_tokens,m.output_tokens,m.cached_input_tokens,m.total_tokens,u.dates.size]);
  const blob=new Blob(['\ufeff'+rows.map(r=>r.map(csvCell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=`spark-arena-${demo?'demo-':''}${view.day}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
render();
try{
  const response=await fetch('data.json',{cache:'no-store'});if(!response.ok)throw new Error('load');
  realData=await response.json();if(!Array.isArray(realData.reports)||!Array.isArray(realData.participants))throw new Error('format');
  data=demo?sampleData():realData;updateOptions();render();
  const stamp=new Date(realData.generated_at);const age=Date.now()-stamp.getTime();
  $('data-status').textContent=`${age>6*3600e3?'榜单快照较旧 · ':''}更新于 ${stamp.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})} · 北京时间 · 自愿公开`;
}catch{
  $('data-status').textContent='榜单数据暂时无法读取，请稍后刷新。演示仍可查看。';
  $('empty-copy').textContent='当前数据读取失败，暂时无法确认真实榜单。';
}
