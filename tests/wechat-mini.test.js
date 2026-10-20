import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import fs from 'node:fs';
import vm from 'node:vm';
const require=createRequire(import.meta.url);
const logic=require('../miniprogram/lib/board.js');
const r={id:'wx_a',wechat_name:'昵称',identity:'wechat-login',date:'2026-10-19',coverage:'recorded-window',models:[{model:'m',input_tokens:100,output_tokens:10,cached_input_tokens:80,total_tokens:110}]};
test('mini program day and model rollups use cache subset',()=>{
 const out=logic.aggregate({reports:[r,{...r,date:'2026-10-18'},{...r,date:'2026-10-12'}]},'2026-10-19',7,'m');
 assert.equal(out.totalText,'220');assert.equal(out.people,1);assert.equal(out.rows[0].reportedDays,2);assert.equal(out.rows[0].cacheRate,'80.0%');
});
test('same nickname does not merge WeChat identities',()=>{
 const out=logic.aggregate({reports:[r,{...r,id:'wx_b'}]},'2026-10-19',1,'');assert.equal(out.people,2);
});
test('legacy GitHub names are not labeled WeChat verified',()=>{
 const out=logic.aggregate({reports:[{...r,identity:undefined}]},'2026-10-19',1,'');assert.equal(out.rows[0].identity,'网页账号');
});
test('business date is UTC+8 regardless of machine timezone',()=>{
 assert.equal(logic.yesterday(Date.parse('2026-10-19T16:30:00Z')),'2026-10-19');
 assert.equal(logic.yesterday(Date.parse('2026-10-19T15:30:00Z')),'2026-10-18');
});
test('retained mini program refresh recalculates yesterday across midnight',async()=>{
 let page,day='2026-10-19';
 const data={reports:[r,{...r,date:'2026-10-20'}]};
 const context={Page:p=>{page=p;},require:name=>name.includes('/board')?{...logic,yesterday:()=>day}:{},
   getApp:()=>({globalData:{apiBase:'',publicBoardUrl:'https://example.test/data.json'}}),
   wx:{request:o=>o.success({statusCode:200,data})},Promise,Error,Map,Set};
 vm.runInNewContext(fs.readFileSync(new URL('../miniprogram/pages/board/index.js',import.meta.url),'utf8'),context);
 page.setData=values=>Object.assign(page.data,values);
 await page.onShow();assert.equal(page.data.day,'2026-10-19');
 day='2026-10-20';await page.refresh();assert.equal(page.data.day,'2026-10-20');assert.equal(page.data.people,1);
});
test('independent project enables only login testing while public signup stays closed',()=>{
 const config=JSON.parse(fs.readFileSync(new URL('../miniprogram/project.config.json',import.meta.url)));
 assert.match(config.appid,/^wx[0-9a-f]{16}$/);
 const build=require('../miniprogram/config.js');assert.equal(new URL(build.API_BASE).protocol,'https:');assert.equal(build.ENROLLMENT_OPEN,false);
 const app=JSON.parse(fs.readFileSync(new URL('../miniprogram/app.json',import.meta.url)));
 for(const page of app.pages)for(const suffix of ['.js','.json','.wxml','.wxss'])assert.ok(fs.existsSync(new URL('../miniprogram/'+page+suffix,import.meta.url)));
});
test('mini program shows a server-validated user after code login, never sends supplied OpenID',async()=>{
 let loginPayload;
 const store=new Map();
 const wx={getStorageSync:k=>store.get(k),setStorageSync:(k,v)=>store.set(k,v),removeStorageSync:k=>store.delete(k),
   login:o=>o.success({code:'temporary-code'}),request:o=>{loginPayload=o.data;o.success({statusCode:200,data:{access_token:'synthetic-session',user:{id:'wx_server',nickname:'n'}}});}};
 const context={wx,getApp:()=>({globalData:{apiBase:'https://example.test'}}),module:{exports:{}},Promise,Error};
 vm.runInNewContext(fs.readFileSync(new URL('../miniprogram/lib/api.js',import.meta.url),'utf8'),context);
 const user=await context.module.exports.login();assert.equal(user.id,'wx_server');assert.equal(loginPayload.code,'temporary-code');assert.equal(loginPayload.openid,undefined);
 assert.equal(store.get('sparkArenaSession'),'synthetic-session');
});

test('native visibility directives bind expressions instead of truthy literal strings',()=>{
 const app=JSON.parse(fs.readFileSync(new URL('../miniprogram/app.json',import.meta.url)));
 let count=0;
 for(const page of app.pages){
   const wxml=fs.readFileSync(new URL('../miniprogram/'+page+'.wxml',import.meta.url),'utf8');
   for(const directive of wxml.matchAll(/wx:(?:if|elif)="([^"]*)"/g)){
     count++;assert.match(directive[1],/^\{\{[\s\S]+\}\}$/);
   }
 }
 assert.ok(count>0);
});

test('failed public snapshot keeps browse-only notice and stops loading',async()=>{
 let page;
 const context={Page:p=>{page=p;},require:name=>name.includes('/board')?logic:{},
   getApp:()=>({globalData:{apiBase:'',publicBoardUrl:'https://example.test/data.json'}}),
   wx:{request:o=>o.fail()},Promise,Error,Map,Set};
 vm.runInNewContext(fs.readFileSync(new URL('../miniprogram/pages/board/index.js',import.meta.url),'utf8'),context);
 page.setData=values=>Object.assign(page.data,values);
 await page.refresh();
 assert.equal(page.data.browseOnly,true);assert.equal(page.data.loading,false);
 assert.match(page.data.error,/合法域名/);assert.equal(page.data.rows.length,0);
});

test('login-only stage refuses enrollment and pairing before making requests',async()=>{
 let page,calls=0;
 const context={Page:p=>{page=p;},require:()=>({request:()=>{calls++;throw new Error('must not call');}}),
   getApp:()=>({globalData:{apiBase:'https://example.test',enrollmentOpen:false}}),wx:{},Promise,Error,Date};
 vm.runInNewContext(fs.readFileSync(new URL('../miniprogram/pages/me/index.js',import.meta.url),'utf8'),context);
 page.setData=values=>Object.assign(page.data,values);page.onLoad();
 assert.equal(page.data.configured,true);assert.equal(page.data.enrollmentOpen,false);
 page.data.nickname='fixture';
 await page.enroll();assert.match(page.data.error,/报名尚未开放/);
 await page.pair();assert.match(page.data.error,/绑定尚未开放/);assert.equal(calls,0);
});

test('live board keeps signup-closed notice during login-only stage',async()=>{
 let page;
 const context={Page:p=>{page=p;},require:name=>name.includes('/board')?logic:{request:async()=>({reports:[]})},
   getApp:()=>({globalData:{apiBase:'https://example.test',enrollmentOpen:false}}),wx:{},Promise,Error,Map,Set};
 vm.runInNewContext(fs.readFileSync(new URL('../miniprogram/pages/board/index.js',import.meta.url),'utf8'),context);
 page.setData=values=>Object.assign(page.data,values);await page.refresh();
 assert.equal(page.data.browseOnly,true);assert.equal(page.data.loading,false);assert.equal(page.data.error,'');
});


test('join button enrolls a filled nickname without a separate consent checkbox',async()=>{
 let page,calls=[];
 const context={Page:p=>{page=p;},require:()=>({request:async(...args)=>{calls.push(args);return {nickname:'fixture',consent_public:true};}}),
   getApp:()=>({globalData:{apiBase:'https://example.test',enrollmentOpen:true}}),wx:{},Promise,Error,Date};
 vm.runInNewContext(fs.readFileSync(new URL('../miniprogram/pages/me/index.js',import.meta.url),'utf8'),context);
 page.setData=values=>Object.assign(page.data,values);page.onLoad();
 assert.equal(calls.length,0);
 await page.enroll();assert.match(page.data.error,/填写展示昵称/);assert.equal(calls.length,0);
 page.nickname({detail:{value:' fixture '}});assert.equal(calls.length,0);
 await page.enroll();assert.equal(calls.length,1);assert.equal(calls[0][0],'/v1/profile');
 assert.equal(calls[0][1],'PUT');assert.equal(calls[0][2].nickname,'fixture');assert.equal(calls[0][2].consent_public,true);
});
