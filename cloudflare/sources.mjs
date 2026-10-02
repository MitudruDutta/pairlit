export const actors={linkedin:'harvestapi~linkedin-profile-scraper',instagram:'apify~instagram-profile-scraper'};
export function canonical(value,platform) {
  let u;try{u=new URL(String(value).trim());}catch{throw new Error('Invalid profile URL');}
  if(u.protocol!=='https:'||u.username||u.password||u.port||/https:\/\/[^/]+:\d+/.test(String(value)))throw new Error('Use a public HTTPS profile URL without credentials or port');
  if(platform==='linkedin') {
    if(!(u.hostname==='linkedin.com'||u.hostname.endsWith('.linkedin.com')))throw new Error('LinkedIn URL required');
    const m=u.pathname.match(/^\/in\/([A-Za-z0-9%_-]{2,120})\/?$/);if(!m)throw new Error('Use an individual LinkedIn /in/ profile');
    return 'https://www.linkedin.com/in/'+m[1].toLowerCase()+'/';
  }
  if(!['instagram.com','www.instagram.com'].includes(u.hostname))throw new Error('Instagram URL required');
  const m=u.pathname.match(/^\/([A-Za-z0-9._]{1,30})\/?$/);
  if(!m||['p','reel','reels','stories','explore','accounts','direct'].includes(m[1].toLowerCase()))throw new Error('Use an Instagram profile, not a post');
  return 'https://www.instagram.com/'+m[1].toLowerCase()+'/';
}
function text(v) {
  if(typeof v==='string')return v;
  if(Array.isArray(v))return v.map(text).join('\n');
  if(v&&typeof v==='object')return Object.entries(v).filter(([k])=>['title','name','description','companyName','skill','schoolName','text','caption','url','link','website'].includes(k)).map(([,x])=>text(x)).join('\n');
  return '';
}
export function clean(kind,row,url,run_id='') {
  if(!row||row.error||row.errorDescription)throw new Error(kind+' profile could not be retrieved');
  let name,content,portrait,links,followers,verified;
  if(kind==='instagram') {
    if(row.private===true||row.isPrivate===true)throw new Error('Instagram account is private');
    if(row.private!==false&&row.isPrivate!==false)throw new Error('Instagram public visibility could not be verified');
    if(String(row.username||'').toLowerCase()!==url.split('/').filter(Boolean).at(-1))throw new Error('Instagram returned a different identity');
    name=row.fullName||row.full_name||row.username;
    content=[row.biography||'',...(row.latestPosts||[]).slice(0,12).filter(p=>!p.ownerUsername||p.ownerUsername.toLowerCase()===row.username.toLowerCase()).map(p=>p.caption||'')].join('\n\n').slice(0,18000);
    portrait=row.profilePicUrlHD||row.profilePicUrl||'';
    links=[row.externalUrl||'',...(row.externalUrls||[]).map(x=>x.url||'')];followers=row.followersCount||0;verified=!!(row.verified||row.isVerified);
  } else {
    name=row.fullName||row.name||[row.firstName,row.lastName].filter(Boolean).join(' ');
    if(!name)throw new Error('LinkedIn profile has no verifiable name');
    const actual=row.linkedinUrl||row.url||row.profileUrl;
    if(actual&&canonical(actual,'linkedin')!==url)throw new Error('LinkedIn returned a different identity');
    content=['headline','about','summary','experience','education','skills','interests','publications','projects','websites','website','featured','profileActions'].map(k=>text(row[k])).join('\n\n').slice(0,18000);
    portrait=row.photo||row.profilePicture||row.profilePicUrl||'';if(typeof portrait==='object')portrait=portrait.url||'';
    links=(content.match(/https?:\/\/[^\s"<>]+/g)||[]);
    const cross=JSON.stringify([row.links,row.contactInfo]).matchAll(/instagram\.com\/([A-Za-z0-9._]{1,30})/g);
    for(const m of cross)links.push('https://www.instagram.com/'+m[1]+'/');
    followers=row.followersCount||0;verified=false;
  }
  content=content.replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,'[contact omitted]').replace(/\+?\d[\d ().-]{7,}\d/g,m=>(m.match(/\d/g)||[]).length>=10?'[contact omitted]':m);
  if(content.trim().length<30)throw new Error(kind+' returned too little public text');
  const loc=kind==='linkedin'?row.location||{}:{};
  return {platform:kind,url,name,text:content,portrait:typeof portrait==='string'&&portrait.startsWith('https://')?portrait:'',links,public:true,verified_badge:verified,followers,location:typeof loc==='string'?loc:(loc.linkedinText||''),country_code:loc.countryCode||'',fetched_at:new Date().toISOString(),run_id};
}
export function identity(li,ig) {
  const names=s=>new Set(String(s).normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().match(/[a-z]{3,}/g)||[]);
  const a=names(li.name),b=names(ig.name),shared=[...a].filter(x=>b.has(x)).length;
  const target=ig.url.replace(/\/$/,'').toLowerCase();
  const linked=li.text.toLowerCase().includes(target)||(li.links||[]).some(x=>String(x).toLowerCase().includes(target));
  if(shared<2&&!linked)throw new Error('Account identity is uncertain: public names do not match');
  return {status:linked?'cross_linked':'name_match_review',name_tokens_matched:shared,explanation:linked?'LinkedIn links to this Instagram account.':'Public names match; official ownership still needs review.'};
}
export async function apify(env,method,path,payload) {
  if(!env.APIFY_TOKEN)throw new Error('Apify is not configured on this server');
  const response=await fetch('https://api.apify.com/v2/'+path,{method,headers:{Authorization:'Bearer '+env.APIFY_TOKEN,'Content-Type':'application/json'},body:payload?JSON.stringify(payload):undefined});
  if(!response.ok)throw new Error('Apify request failed ('+response.status+'); check provider access or budget');
  return response.json();
}
