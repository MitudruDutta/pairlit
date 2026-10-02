import {analyze,turn,MODEL} from './model.mjs';
import {canonical,clean,identity,apify,actors} from './sources.mjs';
export const now=()=>new Date().toISOString();
export const uid=()=>crypto.randomUUID().replaceAll('-','');
export async function setup(db) {
  await db.batch([
    db.prepare('CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, data TEXT NOT NULL)'),
    db.prepare('CREATE TABLE IF NOT EXISTS dates (id TEXT PRIMARY KEY, data TEXT NOT NULL)'),
    db.prepare('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL, lease INTEGER DEFAULT 0)'),
    db.prepare('CREATE TABLE IF NOT EXISTS runs (fingerprint TEXT PRIMARY KEY, data TEXT NOT NULL, cap REAL NOT NULL)'),
    db.prepare("CREATE UNIQUE INDEX IF NOT EXISTS profile_li ON profiles(json_extract(data,'$.linkedin_url'))"),
    db.prepare("CREATE UNIQUE INDEX IF NOT EXISTS profile_ig ON profiles(json_extract(data,'$.instagram_url'))")
  ]);
}
const table=t=>{if(!['profiles','dates','jobs'].includes(t))throw new Error('Invalid table');return t;};
export async function all(db,t) {return (await db.prepare(`SELECT data FROM ${table(t)} ORDER BY rowid`).all()).results.map(r=>JSON.parse(r.data));}
export async function get(db,t,id) {const r=await db.prepare(`SELECT data FROM ${table(t)} WHERE id=?`).bind(id).first();if(!r)throw new Error('Record not found');return JSON.parse(r.data);}
export async function put(db,t,record) {
  try {await db.prepare(`INSERT INTO ${table(t)} (id,data) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data`).bind(record.id,JSON.stringify(record)).run();}
  catch(error){if(String(error).includes('UNIQUE'))throw new Error('This source account already belongs to an agent');throw error;}
  return record;
}
export async function patch(db,t,id,fields) {return put(db,t,{...await get(db,t,id),...fields,updated_at:now()});}
async function job(db,kind,target) {
  const active=(await all(db,'jobs')).find(j=>j.kind===kind&&j.target===target&&['queued','running'].includes(j.status));
  if(active)return active;
  return put(db,'jobs',{id:uid(),kind,target,status:'queued',stage:'start',progress:'Waiting for an agent…',created_at:now(),error:null});
}
export async function createProfile(db,input) {
  if(!input.permission)throw new Error('Confirm matching public accounts and acknowledge the fictional simulation');
  const li=canonical(input.linkedin_url,'linkedin'),ig=canonical(input.instagram_url,'instagram');
  const records=await all(db,'profiles'),existing=records.find(p=>p.linkedin_url===li&&p.instagram_url===ig);
  if(existing)return existing;
  if(records.length>=150)throw new Error('Workspace profile limit reached');
  const p={id:uid(),name:li.split('/').filter(Boolean).at(-1).replaceAll('-',' '),linkedin_url:li,instagram_url:ig,status:'queued',sources:[],analysis:null,portrait:'',identity:null,created_at:now(),error:null,demo:false};
  await put(db,'profiles',p);await job(db,'profile',p.id);return p;
}
export async function analyzeProfile(db,id) {await get(db,'profiles',id);return job(db,'profile',id);}
export async function createDate(db,input) {
  const {a_id,b_id}=input,scenario=input.scenario||'A bookshop café. Choose a book for one another, then plan a relaxed afternoon together.';
  if(a_id===b_id)throw new Error('Choose two different agents');
  if(typeof scenario!=='string'||scenario.length<20||scenario.length>400)throw new Error('Setting must contain 20–400 characters');
  const a=await get(db,'profiles',a_id),b=await get(db,'profiles',b_id);
  if(a.status!=='ready'||b.status!=='ready')throw new Error('Both profiles must finish analysis first');
  const existing=(await all(db,'dates')).find(d=>[d.a_id,d.b_id].includes(a_id)&&[d.a_id,d.b_id].includes(b_id)&&d.scenario===scenario);
  if(existing&&existing.status!=='failed')return existing;
  const d=existing||{id:uid(),a_id,b_id,scenario,turns:[],created_at:now()};
  d.agents ||= Object.fromEntries([a,b].map(p=>[p.id,{id:p.id,name:p.name,portrait:p.portrait,analysis:p.analysis}]));
  d.status='queued';d.error=null;await put(db,'dates',d);await job(db,'date',d.id);return d;
}
export function rankings(profiles,dates,id) {
  const ready=profiles.filter(p=>p.status==='ready'),own=ready.find(p=>p.id===id);if(!own)throw new Error('Analyze this profile before viewing rankings');
  const stop=new Set(['the','and','for','with','from','that','this','into','their','about','public','profile','interest','interests','content']);
  const words=p=>new Set(p.analysis.traits.flatMap(t=>(t.label.toLowerCase().match(/[a-z]{3,}/g)||[]).filter(w=>!stop.has(w))));
  const a=words(own);
  return ready.filter(p=>p.id!==id).map(other=>{
    const b=words(other),shared=[...a].filter(w=>b.has(w)).sort(),baseline=Math.round(25+55*shared.length/Math.max(1,a.size));
    const matches=dates.filter(d=>d.status==='complete'&&[d.a_id,d.b_id].includes(id)&&[d.a_id,d.b_id].includes(other.id));
    const assessments=matches.map(d=>d.turns.findLast(t=>t.speaker_id===id)).filter(Boolean),last=assessments.at(-1),score=assessments.length?Math.round(assessments.reduce((s,t)=>s+t.fit,0)/assessments.length):null;
    return {profile_id:other.id,name:other.name,portrait:other.portrait,score:score===null?baseline:Math.round(.4*baseline+.6*score),baseline_score:baseline,date_score:score,settings_tested:matches.length,fit_range:assessments.length?[Math.min(...assessments.map(t=>t.fit)),Math.max(...assessments.map(t=>t.fit))]:null,shared_topics:shared,basis:matches.length?'completed_date':'profile_comparison',date_id:matches.at(-1)?.id||null,reason:last?.reflection||(shared.length?'Shared public themes: '+shared.join(', '):'Few explicit shared themes; a conversation may reveal more.'),uncertainty:last?.curiosity||'These agents have not dated yet.'};
  }).sort((a,b)=>b.score-a.score||a.name.localeCompare(b.name));
}
export function chemistry(profiles,dates,a_id,b_id) {
  if(a_id===b_id)throw new Error('Choose two different agents');
  const a=profiles.find(p=>p.id===a_id),b=profiles.find(p=>p.id===b_id);if(!a||!b)throw new Error('Record not found');
  const records=dates.filter(d=>d.status==='complete'&&[d.a_id,d.b_id].includes(a_id)&&[d.a_id,d.b_id].includes(b_id)).map(d=>{
    const left=d.turns.findLast(t=>t.speaker_id===a_id),right=d.turns.findLast(t=>t.speaker_id===b_id);
    return {date_id:d.id,scenario:d.scenario,a_fit:left.fit,b_fit:right.fit,mutual_fit:Math.min(left.fit,right.fit),assessment_gap:Math.abs(left.fit-right.fit),a_reflection:left.reflection,b_reflection:right.reflection};
  });
  return {a_id,b_id,a_name:a.name,b_name:b.name,settings_tested:records.length,mutual_fit_range:records.length>1?Math.max(...records.map(r=>r.mutual_fit))-Math.min(...records.map(r=>r.mutual_fit)):null,context_evidence:records.length>1?'Multiple simulated settings':'One setting only; variation remains unknown',dates:records};
}
async function fingerprint(value) {const data=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)));return [...data].map(x=>x.toString(16).padStart(2,'0')).join('');}
async function sourceStep(env,db,j,p,kind) {
  const payload=kind==='linkedin'?{urls:[p.linkedin_url],profileScraperMode:'Profile details no email ($4 per 1k)'}:{usernames:[p.instagram_url.split('/').filter(Boolean).at(-1)],includeAboutSection:false};
  const fp=await fingerprint(JSON.stringify([kind,payload])),cap=kind==='linkedin'?.08:.029;
  let saved=await db.prepare('SELECT data FROM runs WHERE fingerprint=?').bind(fp).first(),run=saved?JSON.parse(saved.data):null;
  if(!run) {
    const total=Number(env.PAIRLIT_TOTAL_CAP_USD||'.50');
    const reserved=await db.prepare('INSERT OR IGNORE INTO runs (fingerprint,data,cap) SELECT ?,?,? WHERE (SELECT coalesce(sum(cap),0) FROM runs)+?<=?').bind(fp,JSON.stringify({status:'STARTING',kind,created_at:now()}),cap,cap,total).run();
    if(!reserved.meta.changes)throw new Error('Extraction budget reached; operator review required');
    // Reservation precedes provider start. An uncertain network outcome must never trigger an automatic second paid run.
    run=(await apify(env,'POST','acts/'+actors[kind]+'/runs?maxTotalChargeUsd='+cap+'&timeout=600&maxItems=1',payload)).data;
    await db.prepare('UPDATE runs SET data=? WHERE fingerprint=?').bind(JSON.stringify({id:run.id,status:run.status,defaultDatasetId:run.defaultDatasetId,usageTotalUsd:run.usageTotalUsd}),fp).run();
  } else if(run.status==='STARTING')throw new Error('An earlier provider start has an uncertain outcome; operator review required');
  if(!['SUCCEEDED','FAILED','TIMED-OUT','ABORTED'].includes(run.status)) {
    run=(await apify(env,'GET','actor-runs/'+run.id)).data;
    await db.prepare('UPDATE runs SET data=? WHERE fingerprint=?').bind(JSON.stringify({id:run.id,status:run.status,defaultDatasetId:run.defaultDatasetId,usageTotalUsd:run.usageTotalUsd}),fp).run();
  }
  if(['FAILED','TIMED-OUT','ABORTED'].includes(run.status))throw new Error(kind+' extraction ended '+run.status);
  await patch(db,'jobs',j.id,{status:'queued',progress:'Reading '+kind+' public profiles…'});
  if(run.status!=='SUCCEEDED')return false;
  await db.prepare('UPDATE runs SET cap=? WHERE fingerprint=?').bind(Number(run.usageTotalUsd||0),fp).run();
  const rows=await apify(env,'GET','datasets/'+run.defaultDatasetId+'/items?clean=true&limit=2');
  if(rows.length!==1)throw new Error('Expected exactly one result from '+kind);
  const source=clean(kind,rows[0],kind==='linkedin'?p.linkedin_url:p.instagram_url,run.id);
  await patch(db,'profiles',p.id,{sources:[...p.sources.filter(s=>s.platform!==kind),source],status:'reading',error:null});
  return true;
}
export async function pump(env) {
  const db=env.DB;
  const row=await db.prepare("SELECT id,data FROM jobs WHERE json_extract(data,'$.status') IN ('queued','running') AND lease<? ORDER BY rowid LIMIT 1").bind(Date.now()).first();
  if(!row)return;
  const claimed=await db.prepare('UPDATE jobs SET lease=? WHERE id=? AND lease<?').bind(Date.now()+120000,row.id,Date.now()).run();
  if(!claimed.meta.changes)return;
  const j=JSON.parse(row.data);
  try {
    await patch(db,'jobs',j.id,{status:'running',error:null});
    if(j.kind==='date') {
      const d=await get(db,'dates',j.target),index=d.turns.length;
      if(index>=4){await patch(db,'jobs',j.id,{status:'complete',progress:'Complete'});return;}
      const a=d.agents[d.a_id],b=d.agents[d.b_id],person=index%2===0?a:b,other=index%2===0?b:a;
      await patch(db,'dates',d.id,{status:'running',error:null});
      await patch(db,'jobs',j.id,{progress:person.name+'’s agent is considering its next move…'});
      const response=await turn(env,person,other,d.turns,d.scenario,index);
      const turns=[...d.turns,response],done=turns.length===4;
      await patch(db,'dates',d.id,{turns,status:done?'complete':'running',...(done?{finished_at:now()}:{}),error:null});
      await patch(db,'jobs',j.id,{status:done?'complete':'queued',progress:done?'Complete':'The other agent is thinking…'});
    } else {
      let p=await get(db,'profiles',j.target);
      const kind=!p.sources.some(s=>s.platform==='linkedin')?'linkedin':!p.sources.some(s=>s.platform==='instagram')?'instagram':null;
      if(kind){await sourceStep(env,db,j,p,kind);return;}
      const li=p.sources.find(s=>s.platform==='linkedin'),ig=p.sources.find(s=>s.platform==='instagram'),checked=identity(li,ig);
      p=await patch(db,'profiles',p.id,{name:li.name,identity:checked,portrait:ig.portrait||li.portrait,location:li.location||'',country_code:li.country_code||'',status:'analyzing',error:null});
      await patch(db,'jobs',j.id,{progress:'Reading both sources and grounding profile traits…'});
      const analysis=await analyze(env,p);
      await patch(db,'profiles',p.id,{analysis,status:'ready',error:null});
      await patch(db,'jobs',j.id,{status:'complete',progress:'Complete'});
    }
  } catch(error) {
    const message=String(error.message||'Operation failed; retry to resume.').slice(0,300);
    await patch(db,'jobs',j.id,{status:'failed',error:message,progress:'Needs attention'});
    await patch(db,j.kind==='date'?'dates':'profiles',j.target,{status:'failed',error:message});
  } finally {await db.prepare('UPDATE jobs SET lease=0 WHERE id=?').bind(j.id).run();}
}
export async function state(db,env) {
  const [profiles,dates,jobs]=await Promise.all([all(db,'profiles'),all(db,'dates'),all(db,'jobs')]);
  return {profiles,dates,jobs:jobs.slice(-150),stats:{profiles:profiles.length,ready:profiles.filter(p=>p.status==='ready').length,dates:dates.filter(d=>d.status==='complete').length,active:jobs.filter(j=>['queued','running'].includes(j.status)).length},model:env.PAIRLIT_MODEL||MODEL,source_policy:'Exactly LinkedIn and public Instagram. Fictional public-profile simulations.',hosting:'Cloudflare Workers + D1 + Workers AI'};
}
