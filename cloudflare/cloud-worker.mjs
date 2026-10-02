import {setup,all,get,put,state,pump,createProfile,analyzeProfile,createDate,rankings,chemistry} from './engine.mjs';
const limits=new Map();
let initialized;
export default {
  async fetch(request,env,ctx) {
    const url=new URL(request.url),path=url.pathname;
    const headers={'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','X-Pairlit-Hosting':'cloudflare-workers-d1-ai'};
    const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers});
    if(!path.startsWith('/api/')&&path!=='/health')return env.ASSETS.fetch(request);
    try {
      if(!env.DB)return json({detail:'Cloud database is not configured'},503);
      initialized ||= setup(env.DB);await initialized;
      if(path==='/health')return json({status:'ok',product:'Pairlit Social',storage:'cloudflare-d1',model:env.PAIRLIT_MODEL||'@cf/meta/llama-3.1-8b-instruct-fast',hosting:'cloudflare-workers',ingestion_configured:!!env.APIFY_TOKEN,migration_enabled:!!env.PAIRLIT_ADMIN_TOKEN});
      if(path==='/api/admin/import'&&request.method==='POST') {
        if(!env.PAIRLIT_ADMIN_TOKEN||request.headers.get('Authorization')!=='Bearer '+env.PAIRLIT_ADMIN_TOKEN)return json({detail:'Unauthorized'},401);
        const text=await request.text();if(text.length>4000000)return json({detail:'Import too large'},413);
        const payload=JSON.parse(text),existing=await all(env.DB,'profiles');if(existing.length)return json({detail:'Database already initialized; no overwrite permitted'},409);
        for(const name of ['profiles','dates','jobs'])for(const row of payload[name]||[])await put(env.DB,name,row);
        return json({imported:(payload.profiles||[]).length});
      }
      let body={};
      if(request.method==='POST') {
        if(request.headers.get('X-Pairlit-Client')!=='web')return json({detail:'Pairlit client header required'},403);
        const ip=request.headers.get('CF-Connecting-IP')||'local',timestamps=(limits.get(ip)||[]).filter(t=>t>Date.now()-60000);
        if(timestamps.length>=12)return json({detail:'Please wait one minute before starting more work'},429);
        timestamps.push(Date.now());limits.set(ip,timestamps);
        const text=await request.text();if(text.length>10000)return json({detail:'Request too large'},413);body=JSON.parse(text||'{}');
      }
      if(request.method==='GET'&&path==='/api/state'){ctx.waitUntil(pump(env));return json(await state(env.DB,env));}
      if(request.method==='POST'&&path==='/api/profiles'){const p=await createProfile(env.DB,body);ctx.waitUntil(pump(env));return json(p,202);}
      let match;
      if((match=path.match(/^\/api\/profiles\/([a-z0-9]{1,40})\/analyze$/))&&request.method==='POST'){const job=await analyzeProfile(env.DB,match[1]);ctx.waitUntil(pump(env));return json(job,202);}
      if((match=path.match(/^\/api\/profiles\/([a-z0-9]{1,40})\/rankings$/))&&request.method==='GET')return json(rankings(await all(env.DB,'profiles'),await all(env.DB,'dates'),match[1]));
      if((match=path.match(/^\/api\/profiles\/([a-z0-9]{1,40})\/portrait$/))&&request.method==='GET') {
        const p=await get(env.DB,'profiles',match[1]);
        const asset=await env.ASSETS.fetch(new Request(new URL('/portraits/'+match[1]+'.image',url)));
        if(asset.ok&&asset.headers.get('Content-Type')!=='text/html')return new Response(asset.body,{headers:{'Content-Type':'image/jpeg','Cache-Control':'public,max-age=3600','X-Content-Type-Options':'nosniff'}});
        const source=p.sources.map(s=>s.portrait).findLast(u=>typeof u==='string'&&/^https:\/\/([a-z0-9.-]+\.)?(cdninstagram\.com|fbcdn\.net|licdn\.com)\//i.test(u));
        if(!source)return json({detail:'Portrait unavailable'},404);
        const response=await fetch(source,{redirect:'manual'});const mime=response.headers.get('Content-Type')||'';
        if(!response.ok||!/^image\/(jpeg|png|webp)/.test(mime))return json({detail:'Portrait unavailable'},404);
        return new Response(response.body,{headers:{'Content-Type':mime,'Cache-Control':'public,max-age=3600','X-Content-Type-Options':'nosniff'}});
      }
      if((match=path.match(/^\/api\/profiles\/([a-z0-9]{1,40})$/))&&request.method==='GET')return json(await get(env.DB,'profiles',match[1]));
      if(path==='/api/dates'&&request.method==='POST'){const date=await createDate(env.DB,body);ctx.waitUntil(pump(env));return json(date,202);}
      if((match=path.match(/^\/api\/dates\/([a-z0-9]{1,40})$/))&&request.method==='GET')return json(await get(env.DB,'dates',match[1]));
      if((match=path.match(/^\/api\/chemistry\/([a-z0-9]{1,40})\/([a-z0-9]{1,40})$/))&&request.method==='GET')return json(chemistry(await all(env.DB,'profiles'),await all(env.DB,'dates'),match[1],match[2]));
      if(path==='/api/round'&&request.method==='POST') {
        const profiles=await all(env.DB,'profiles'),dates=await all(env.DB,'dates'),ids=new Set();
        const ready=profiles.filter(p=>p.status==='ready');if(ready.length<2)throw new Error('At least two analyzed profiles are required');
        for(const p of ready){const ranked=rankings(profiles,dates,p.id);for(const other of [ranked[0],ranked.at(-1)])ids.add((await createDate(env.DB,{a_id:p.id,b_id:other.profile_id})).id);}
        ctx.waitUntil(pump(env));return json({date_ids:[...ids]},202);
      }
      return json({detail:'Not found'},404);
    } catch(error) {return json({detail:String(error.message||'Operation failed').slice(0,300)},422);}
  },
  async scheduled(event,env,ctx){initialized ||= setup(env.DB);await initialized;ctx.waitUntil(pump(env));}
};
