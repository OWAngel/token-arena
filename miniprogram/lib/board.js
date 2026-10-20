function shiftDay(day, offset) {const d=new Date(day+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+offset);return d.toISOString().slice(0,10);}
function yesterday(now) {return new Date((now===undefined?Date.now():now)+8*3600e3-86400e3).toISOString().slice(0,10);}
function compact(n) {const unit=n>=1e9?[1e9,'B']:n>=1e6?[1e6,'M']:n>=1e3?[1e3,'K']:[1,''];return (n/unit[0]).toFixed(unit[1]?2:0).replace(/\.00$/,'')+unit[1];}
function aggregate(data,day,days,model) {
  const users=new Map(), models=new Set(),start=shiftDay(day,1-days);
  for(const r of data.reports||[]) {
    if(r.date<start||r.date>day)continue;
    for(const m of r.models||[]) {
      if(model&&m.model!==model)continue;
      models.add(m.model);
      if(!users.has(r.id))users.set(r.id,{id:r.id,name:r.wechat_name,identity:r.identity==='wechat-login'?'微信登录账号':'网页账号',total:0,output:0,input:0,cached:0,models:new Map(),days:new Set(),partial:false});
      const u=users.get(r.id);u.days.add(r.date);u.partial=u.partial||r.coverage==='partial';u.total+=m.total_tokens;u.output+=m.output_tokens;u.input+=m.input_tokens;u.cached+=m.cached_input_tokens;
      const modelRow=u.models.get(m.model)||{model:m.model,total:0,input:0,output:0};modelRow.total+=m.total_tokens;modelRow.input+=m.input_tokens;modelRow.output+=m.output_tokens;u.models.set(m.model,modelRow);
    }
  }
  const ranked=[...users.values()].sort((a,b)=>b.total-a.total||a.id.localeCompare(b.id));
  let total=0,output=0;
  const rows=ranked.map((u,i)=>{total+=u.total;output+=u.output;const detail=[...u.models.values()].sort((a,b)=>b.total-a.total).map(m=>({...m,totalText:compact(m.total),inputText:compact(m.input),outputText:compact(m.output)}));return {id:u.id,name:u.name,identity:u.identity,rank:i+1,totalText:compact(u.total),outputText:compact(u.output),model:detail[0].model,models:detail,reportedDays:u.days.size,partial:u.partial,cacheRate:u.input?(u.cached/u.input*100).toFixed(1)+'%':'—'};});
  return {rows,totalText:compact(total),outputText:compact(output),people:rows.length,modelCount:models.size};
}
module.exports={shiftDay,yesterday,compact,aggregate};
