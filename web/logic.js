export function shiftDay(day, offset) {
  const d = new Date(`${day}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}
export function yesterday() {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const get = type => parts.find(p => p.type === type).value;
  return shiftDay(`${get('year')}-${get('month')}-${get('day')}`, -1);
}
export function compact(n) {
  const [value,suffix] = n >= 1e9 ? [n/1e9,'B'] : n >= 1e6 ? [n/1e6,'M'] : n >= 1e3 ? [n/1e3,'K'] : [n,''];
  return `${value.toLocaleString('en-US',{maximumFractionDigits:suffix ? 2 : 0})}${suffix}`;
}
export function aggregate(data, {day, days=1, model='', search='', metric='total_tokens'}) {
  const start = shiftDay(day, 1-days), users = new Map(), models = new Map();
  for (const report of data.reports) {
    if (report.date < start || report.date > day) continue;
    if (search && !`${report.wechat_name} ${report.github||""}`.toLowerCase().includes(search.toLowerCase())) continue;
    const found = report.models.filter(m => !model || m.model === model);
    if (!found.length) continue;
    let user = users.get(report.id);
    if (!user) { user = {...report,models:new Map(),total_tokens:0,input_tokens:0,output_tokens:0,cached_input_tokens:0,dates:new Set(),partial:false,issueNumbers:new Set()}; users.set(report.id,user); }
    user.dates.add(report.date); user.issueNumbers.add(report.issue); user.partial ||= report.coverage === 'partial';
    for (const m of found) {
      let um = user.models.get(m.model);
      if (!um) {um={model:m.model,total_tokens:0,input_tokens:0,output_tokens:0,cached_input_tokens:0};user.models.set(m.model,um);}
      let global = models.get(m.model);
      if (!global) {global={model:m.model,total_tokens:0};models.set(m.model,global);}
      global.total_tokens += m.total_tokens;
      for (const key of ['total_tokens','input_tokens','output_tokens','cached_input_tokens']) { user[key]+=m[key]; um[key]+=m[key]; }
    }
  }
  const ranking=[...users.values()].sort((a,b)=>b[metric]-a[metric] || String(a.github||a.id).localeCompare(String(b.github||b.id)));
  const totals=ranking.reduce((a,u)=>{for(const k of Object.keys(a))a[k]+=u[k];return a;},{total_tokens:0,input_tokens:0,output_tokens:0,cached_input_tokens:0});
  return {ranking,totals,models:[...models.values()].sort((a,b)=>b.total_tokens-a.total_tokens)};
}
export function shellQuote(value) { return `'${value.replaceAll("'", "'\\''")}'`; }
export function connectionCommand(name,url,repo='OWAngel/token-arena') {
  return `git clone https://github.com/${repo}.git\ncd ${repo.split('/')[1]}\ngh auth login\n# sparkDash 需要令牌时，先运行：python3 -m arena.client token\npython3 -m arena.client connect --repo ${shellQuote(repo)} --name ${shellQuote(name)} --url ${shellQuote(url)} --consent-public\npython3 -m arena.client run\npython3 -m arena.client install-schedule`;
}
export function csvCell(value) {
  let s=String(value);
  if (/^[\s]*[=+@-]/.test(s)) s="'"+s;
  return `"${s.replaceAll('"','""')}"`;
}
