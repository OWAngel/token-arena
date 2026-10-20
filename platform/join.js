import {shellQuote} from './logic.js';
const $=id=>document.getElementById(id),storageKey='sparkArenaPlatformKey';
let key='',user=null,busy=false,pairExpires=0;
try{key=localStorage.getItem(storageKey)||'';}catch{/* Recovery import still works without storage. */}

async function request(path,method='GET',data,credential=key){
 const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json',...(credential?{Authorization:'Bearer '+credential}:{})},body:data===undefined?undefined:JSON.stringify(data),cache:'no-store',redirect:'error',credentials:'omit'});
 const result=await response.json();
 if(!response.ok)throw new Error(result.error||'操作失败，请稍后重试');
 return result;
}
function saveKey(value){key=value;try{if(value)localStorage.setItem(storageKey,value);else localStorage.removeItem(storageKey);}catch{$('join-status').textContent='浏览器无法保存密钥，请立即下载备份。';}}
function changed(){window.dispatchEvent(new Event('arena-membership-changed'));}
function renderUser(){
 $('member-tools').hidden=!user;$('join-start').hidden=!!user;$('forget-key').hidden=!key;
 $('pair-panel').hidden=true;$('pair-code').textContent='';$('join-command').textContent='';pairExpires=0;
 if(user){$('join-name').value=user.nickname;$('member-status').textContent=`${user.nickname} · ${user.consent_public?'已加入':'已退出'} · 已绑定 ${user.device_count} 台设备`;$('make-pair').disabled=!user.consent_public;}
}
async function act(action){if(busy)return;busy=true;document.querySelectorAll('#join-dialog button').forEach(b=>b.disabled=true);$('join-status').textContent='正在处理…';try{await action();if($('join-status').textContent==='正在处理…')$('join-status').textContent='已完成。';}catch(e){$('join-status').textContent=e.message||'网络暂时不可用，请重试。';}finally{busy=false;document.querySelectorAll('#join-dialog button').forEach(b=>b.disabled=false);$('make-pair').disabled=!user?.consent_public;}}
function sourceUrl(){
 const value=$('join-url').value.trim(),p=new URL(value);
 if(!['http:','https:'].includes(p.protocol)||p.username||p.password||p.search||p.hash||/[\x00-\x1f\x7f-\x9f]/.test(value))throw new Error('请填写不含用户名、密码或参数的 sparkDash http(s) 地址。');
 return value;
}
export function installCommand(base,url){
 const archive=base+'/reporter.zip';
 return `set -e\ncurl --fail --silent --show-error --location ${shellQuote(archive)} --output spark-arena-reporter.zip\npython3 -m zipfile -e spark-arena-reporter.zip spark-arena-reporter\ncd spark-arena-reporter\npython3 -m arena.platform_client bind --api-base ${shellQuote(base+'/api')} --url ${shellQuote(url)}\npython3 -m arena.platform_client run\npython3 -m arena.platform_client install-schedule`;
}
async function pair(){
 const url=sourceUrl();
 const result=await request('/v1/pair','POST',{});pairExpires=Date.now()+result.expires_in*1000;
 $('pair-code').textContent=result.pairing_code;$('join-command').textContent=installCommand(location.origin,url);$('pair-panel').hidden=false;
}
$('join-form').addEventListener('submit',e=>{e.preventDefault();act(async()=>{
 sourceUrl();const nickname=$('join-name').value.trim();if(!nickname)throw new Error('请填写展示昵称。');
 if(user)throw new Error('你已有管理身份，请使用生成绑定码按钮。');
 if(key)throw new Error('已有管理密钥尚未验证，请先恢复管理，或移除本地密钥后再报名。');
 const result=await request('/v1/join','POST',{nickname},'');saveKey(result.access_token);user=result.user;renderUser();changed();await pair();$('join-status').textContent='已加入。请保存管理密钥，并在电脑上完成绑定。';
});});
$('make-pair').addEventListener('click',()=>act(pair));
$('save-name').addEventListener('click',()=>act(async()=>{const nickname=$('join-name').value.trim();if(!nickname)throw new Error('请填写展示昵称。');user=await request('/v1/profile','PUT',{nickname,consent_public:true});renderUser();changed();}));
$('revoke-devices').addEventListener('click',()=>{if(confirm('撤销所有设备？它们将停止上报，公开记录仍保留。'))act(async()=>{user=await request('/v1/devices','DELETE');renderUser();});});
$('leave-board').addEventListener('click',()=>{if(confirm('退出公开榜单？将撤销设备并隐藏该身份的历史记录。'))act(async()=>{user=await request('/v1/profile','DELETE');renderUser();changed();});});
$('forget-key').addEventListener('click',()=>{if(confirm('移除此浏览器的管理密钥？上报仍继续，请确保已经保存密钥备份。')){saveKey('');user=null;renderUser();$('join-status').textContent='本地管理密钥已移除。';}});
$('restore-member').addEventListener('click',()=>act(async()=>{const candidate=$('restore-key').value.trim();$('restore-key').value='';if(!/^[A-Za-z0-9_-]{32,128}$/.test(candidate))throw new Error('管理密钥格式不正确。');const restored=await request('/v1/me','GET',undefined,candidate);saveKey(candidate);user=restored;renderUser();}));
$('save-key').addEventListener('click',()=>{if(!key)return;const url=URL.createObjectURL(new Blob([key],{type:'text/plain'})),link=document.createElement('a');link.href=url;link.download='spark-arena-management-key.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
async function copy(id){try{await navigator.clipboard.writeText($(id).textContent);$('copy-status').textContent='已复制';}catch{$('copy-status').textContent='请选中文字手动复制。';}}
$('copy-command').addEventListener('click',()=>copy('join-command'));
$('copy-pair').addEventListener('click',()=>{if(Date.now()>=pairExpires){$('pair-panel').hidden=true;$('pair-code').textContent='';$('join-status').textContent='绑定码已过期，请重新生成。';return;}copy('pair-code');});
renderUser();
if(key)act(async()=>{user=await request('/v1/me');renderUser();});
