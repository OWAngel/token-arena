import test from 'node:test';
import assert from 'node:assert/strict';
import {aggregate,shellQuote,connectionCommand,csvCell,shiftDay} from '../web/logic.js';
const row={id:'1',github:'alice',wechat_name:'小林',date:'2026-10-19',issue:1,coverage:'recorded-window',models:[{model:'m',input_tokens:100,output_tokens:10,cached_input_tokens:80,total_tokens:110}]};
test('period boundaries, per-user grouping and cache subset',()=>{
 const data={reports:[row,{...row,date:'2026-10-18'},{...row,date:'2026-10-12'}]};
 const r=aggregate(data,{day:'2026-10-19',days:7});
 assert.equal(r.ranking.length,1);assert.equal(r.totals.total_tokens,220);assert.equal(r.totals.cached_input_tokens,160);assert.equal(r.ranking[0].dates.size,2);
});
test('model and identity search filters',()=>{
 assert.equal(aggregate({reports:[row]},{day:'2026-10-19',model:'other'}).ranking.length,0);
 assert.equal(aggregate({reports:[row]},{day:'2026-10-19',search:'ALICE'}).ranking.length,1);
});
test('shell metacharacters stay inside quoted argument',()=>{
 assert.equal(shellQuote("a'$(id)`x`"),"'a'\\''$(id)`x`'");
 assert.ok(connectionCommand('name','http://private').includes('--consent-public'));
 assert.ok(connectionCommand('name','http://private','another/fork').includes("--repo 'another/fork'"));
});
test('CSV spreadsheet formulas are neutralized',()=>{
 assert.equal(csvCell('=1+1'),'"\'=1+1"');assert.equal(csvCell('"hello"'),'"""hello"""');
});
test('calendar rollover',()=>assert.equal(shiftDay('2026-03-01',-1),'2026-02-28'));
