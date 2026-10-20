import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {aggregate,shellQuote} from '../web/logic.js';
const code=fs.readFileSync(new URL('../platform/join.js',import.meta.url),'utf8').replace(/^import .*;\n/,'').replace('export function installCommand','function installCommand');
function harness({saved='',failMe=false}={}){
 const fields=new Map(),calls=[],storage=new Map(saved?[['sparkArenaPlatformKey',saved]]:[]);
 const $=id=>{if(!fields.has(id))fields.set(id,{value:'',textContent:'',hidden:false,disabled:false,handlers:{},addEventListener(type,fn){this.handlers[type]=fn;}});return fields.get(id);};
 const context={document:{getElementById:$,querySelectorAll:()=>[]},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  location:{origin:'https://example.test'},window:{dispatchEvent(){}},Event:class{},URL,Date,Error,Promise,shellQuote,
  fetch:async(url,options)=>{calls.push({url,...options});if(url.endsWith('/me'))return {ok:!failMe,json:async()=>failMe?{error:'expired'}:{id:'web_fixture',nickname:'fixture',consent_public:true,device_count:0}};
   return {ok:true,json:async()=>url.endsWith('/join')?{access_token:'synthetic-management-key-abcdefghijklmnopqrstuvwxyz',user:{nickname:'fixture',consent_public:true,device_count:0}}:{pairing_code:'synthetic-pairing-code',expires_in:600}};}};
 vm.runInNewContext(code,context);return {$,calls,storage,context};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('browse and fill are request-free; active join sends nickname only, never source URL',async()=>{
 const h=harness();h.$('join-name').value='fixture';h.$('join-url').value='http://fixture.invalid:5555';
 assert.equal(h.calls.length,0);
 h.$('join-form').handlers.submit({preventDefault(){}});await tick();
 assert.equal(h.calls.length,2);assert.equal(h.calls[0].url,'/api/v1/join');
 assert.deepEqual(JSON.parse(h.calls[0].body),{nickname:'fixture'});
 assert.equal(h.calls[1].url,'/api/v1/pair');
 assert.ok(!JSON.stringify(h.calls).includes('fixture.invalid'));
 const command=h.$('join-command').textContent;
 assert.ok(command.includes("--api-base 'https://example.test/api'"));
 assert.ok(command.includes('https://example.test/reporter.zip'));
 assert.ok(!command.includes('gh auth'));assert.ok(!command.includes('synthetic-management-key'));
});
test('stored key that fails validation remains removable and is not silently replaced',async()=>{
 const h=harness({saved:'synthetic-old-management-key',failMe:true});await tick();
 assert.equal(h.$('forget-key').hidden,false);assert.equal(h.storage.get('sparkArenaPlatformKey'),'synthetic-old-management-key');
 h.$('join-name').value='fixture';h.$('join-url').value='http://fixture.invalid';
 h.$('join-form').handlers.submit({preventDefault(){}});await tick();
 assert.equal(h.calls.filter(r=>r.url.endsWith('/join')).length,0);
});
test('invalid source URL cannot enroll or leak credentials',async()=>{
 const h=harness();h.$('join-name').value='fixture';h.$('join-url').value='http://user:secret@fixture.invalid';
 h.$('join-form').handlers.submit({preventDefault(){}});await tick();assert.equal(h.calls.length,0);
});
test('account-free participants with equal totals have stable distinct rows',()=>{
 const models=[{model:'m',input_tokens:10,output_tokens:1,cached_input_tokens:5,total_tokens:11}];
 const result=aggregate({reports:['web_b','web_a'].map(id=>({id,wechat_name:'same',date:'2026-10-19',models}))},{day:'2026-10-19'});
 assert.equal(result.ranking.length,2);assert.equal(result.ranking[0].id,'web_a');assert.equal(result.totals.total_tokens,22);
});
