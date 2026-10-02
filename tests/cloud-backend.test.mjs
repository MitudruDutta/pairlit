import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {canonical,clean,identity} from '../cloudflare/sources.mjs';
import {analyze} from '../cloudflare/model.mjs';
import {setup,put,get,all,createDate,pump,rankings,chemistry} from '../cloudflare/engine.mjs';

class D1 {
  constructor(){this.sqlite=new DatabaseSync(':memory:');}
  prepare(sql){const db=this.sqlite;let values=[];return {
    bind(...v){values=v;return this;},
    async first(){return db.prepare(sql).get(...values)||null;},
    async all(){return {results:db.prepare(sql).all(...values)};},
    async run(){const r=db.prepare(sql).run(...values);return {meta:{changes:Number(r.changes)}};}
  };}
  async batch(statements){return Promise.all(statements.map(s=>s.run()));}
}
const LI='https://www.linkedin.com/in/fixture-person/',IG='https://www.instagram.com/fixture.person/';
function sources(){return [clean('linkedin',{fullName:'Fixture Person',about:'I design thoughtful products and mentor creative teams. Instagram: '+IG},LI),clean('instagram',{username:'fixture.person',fullName:'Fixture Person',isPrivate:false,biography:'Photography, books and long walks inspire creative projects.'},IG)];}
function analysis(){return {summary:'Public profile themes',traits:[{category:'priority',label:'Creative teams',source:'linkedin',quote:'mentor creative teams',confidence:'explicit'},{category:'quality',label:'Thoughtful design',source:'linkedin',quote:'thoughtful products',confidence:'explicit'},{category:'interest',label:'Photography',source:'instagram',quote:'Photography, books and long walks',confidence:'explicit'}],opening_question:'What creative project would you explore?',conversation_style:'Curious',unknowns:[]};}
function profile(id){return {id,name:id,sources:sources(),analysis:analysis(),status:'ready',portrait:'',linkedin_url:LI.replace('fixture-person',id),instagram_url:IG.replace('fixture.person',id)};}

test('cloud source adapter enforces URL, visibility and identity boundaries',()=>{
  for(const url of ['http://instagram.com/person/','https://instagram.com/p/123/','https://instagram.com:443/person/','https://instagram.com.attacker.example/person/'])assert.throws(()=>canonical(url,'instagram'));
  assert.equal(canonical('https://uk.linkedin.com/in/Fixture-Person/?tracking=1','linkedin'),LI);
  assert.throws(()=>clean('instagram',{username:'fixture.person',isPrivate:true},IG));
  assert.throws(()=>clean('instagram',{username:'fixture.person',biography:'No known visibility'},IG));
  const s=sources();assert.equal(identity(...s).status,'cross_linked');
  assert.equal('contactInfo' in s[0],false);
});
test('cloud model copies real quotes and requires both source platforms',async()=>{
  const env={AI:{run:async()=>({response:{traits:[{category:'priority',label:'Creative teams',evidence_id:0,confidence:'explicit'},{category:'quality',label:'Thoughtful design',evidence_id:0,confidence:'explicit'},{category:'interest',label:'Photography',evidence_id:2,confidence:'explicit'}],opening_question:'What creative project interests you?',conversation_style:'Curious'}})}};
  const p=profile('a');const result=await analyze(env,p);
  assert.equal(result.traits.length,3);
  for(const trait of result.traits)assert.ok(p.sources.find(s=>s.platform===trait.source).text.includes(trait.quote));
  env.AI.run=async()=>({response:{traits:[{category:'interest',label:'Unsupported',evidence_id:999}]}});
  await assert.rejects(()=>analyze(env,p),/grounded traits/);
});
test('durable cloud jobs alternate actual model calls, deduplicate, preserve evidence and rank directionally',async()=>{
  const DB=new D1();await setup(DB);await put(DB,'profiles',profile('a'));await put(DB,'profiles',profile('b'));
  const calls=[];
  const env={DB,AI:{run:async(model,payload)=>{
    const p=JSON.parse(payload.messages[1].content);calls.push([p.person,p.transcript.length]);
    return {response:{message:'Could we explore a bookshop and compare ideas about photography together?',evidence_ids:[0],reflection:'A shared creative topic made this conversation interesting.',curiosity:'How would our approaches differ?',fit:p.person==='a'?72:61}};
  }}};
  const d=await createDate(DB,{a_id:'a',b_id:'b',scenario:'A quiet afternoon in a bookshop café.'});
  for(let i=0;i<4;i++)await pump(env);
  assert.deepEqual(calls,[['a',0],['b',1],['a',2],['b',3]]);
  const saved=await get(DB,'dates',d.id);assert.equal(saved.status,'complete');assert.equal(saved.turns.length,4);
  assert.equal((await createDate(DB,{a_id:'a',b_id:'b',scenario:d.scenario})).id,d.id);
  const a=await get(DB,'profiles','a');a.analysis.summary='Later analysis';await put(DB,'profiles',a);
  assert.notEqual((await get(DB,'dates',d.id)).agents.a.analysis.summary,'Later analysis');
  const p=await all(DB,'profiles'),dates=await all(DB,'dates');
  assert.equal(rankings(p,dates,'a')[0].date_score,72);assert.equal(rankings(p,dates,'b')[0].date_score,61);
  assert.equal(rankings(p,dates,'a').some(r=>r.profile_id==='a'),false);
  assert.equal(chemistry(p,dates,'a','b').dates[0].mutual_fit,61);
  assert.equal(chemistry(p,dates,'a','b').dates[0].assessment_gap,11);
  await assert.rejects(()=>createDate(DB,{a_id:'a',b_id:'a',scenario:d.scenario}));
});
