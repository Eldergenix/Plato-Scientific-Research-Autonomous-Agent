/* Plato scientist UI: Linear-style shell, live campaign views, results analytics, and the
   paper as it is written. Loading states, morphs, charts and layout transitions come from
   Kit (kit.js). Views render to strings; Kit.hydrate keeps continuity across re-renders. */
"use strict";
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ls={get(k,d=""){try{return localStorage.getItem(k)??d}catch{return d}},set(k,v){try{localStorage.setItem(k,v)}catch{}}};
const fmt=n=>Number(n||0).toLocaleString();
const short=n=>{n=Number(n||0);return n>=1e6?(n/1e6).toFixed(n%1e6?1:0)+"M":n>=1e3?Math.round(n/1e3)+"k":String(n)};
const ago=t=>{if(!t)return"";const s=(Date.now()-new Date(t))/1000;if(s<60)return"just now";if(s<3600)return Math.floor(s/60)+"m ago";if(s<86400)return Math.floor(s/3600)+"h ago";
  if(s<86400*7)return Math.floor(s/86400)+"d ago";return new Date(t).toLocaleDateString(undefined,{month:"short",day:"numeric"})};
const when=t=>t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}):"";
const cid=id=>esc("PLT-"+String(id).slice(0,4).toUpperCase());
const eid=id=>encodeURIComponent(String(id??""));
const obj=v=>v&&typeof v==="object"&&!Array.isArray(v)?v:{};
const num=v=>typeof v==="number"&&Number.isFinite(v)?v:null;
const sig=v=>{if(v==null)return"–";const a=Math.abs(v);return a!==0&&(a<1e-3||a>=1e6)?v.toExponential(2):String(+v.toPrecision(4))};
const pct=v=>v>0&&v<0.01?"<1%":Math.round(Math.min(1,v)*100)+"%";

/* ---------- icons (status glyphs in the style of issue trackers) ---------- */
const C=2*Math.PI*3;
function ring(color,frac,dashed){return `<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="none" stroke="${color}" stroke-width="1.5"${dashed?' stroke-dasharray="1.6 1.9"':""}/>`+
  (frac?`<circle cx="7" cy="7" r="3" fill="none" stroke="${color}" stroke-width="6" stroke-dasharray="${(frac*C).toFixed(2)} ${C.toFixed(2)}" transform="rotate(-90 7 7)"/>`:"")+"</svg>"}
const check=color=>`<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6.5" fill="${color}"/><path d="M4.3 7.2 6.2 9l3.5-3.8" fill="none" stroke="var(--bg)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const cross=color=>`<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6.5" fill="${color}"/><path d="m4.9 4.9 4.2 4.2m0-4.2-4.2 4.2" stroke="var(--bg)" stroke-width="1.5" stroke-linecap="round"/></svg>`;
const minus=color=>`<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="none" stroke="${color}" stroke-width="1.5"/><path d="M4.5 7h5" stroke="${color}" stroke-width="1.5" stroke-linecap="round"/></svg>`;
const ico=(d,w=14)=>`<svg width="${w}" height="${w}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const PHASES=["ideation","investigating","ablating","sealed_eval","writing","completed"];
const PHASE_LABEL={ideation:"Ideation",investigating:"Investigating",ablating:"Ablating",sealed_eval:"Sealed eval",writing:"Writing",completed:"Completed",halted:"Halted"};
const PHASE_HINT={ideation:"Scouting the literature and sharpening the question.",investigating:"Running experiments in parallel sandboxes.",ablating:"Judging claims: replication, statistics, figures and a skeptic review.",
  sealed_eval:"Scoring verified findings on the held-out data.",writing:"Writing the paper. It appears in the Paper panel as it is written."};
function campaignIcon(s){return {ideation:ring("var(--text-3)",0,true),investigating:ring("var(--yellow)",.25),ablating:ring("var(--yellow)",.5),
  sealed_eval:ring("var(--yellow)",.75),writing:ring("var(--blue)",.75),completed:check("var(--indigo)"),halted:cross("var(--gray)")}[s]||ring("var(--text-3)")}
function nodeIcon(s){return {open:ring("var(--text-2)"),claimed:ring("var(--yellow)",.25),running:ring("var(--yellow)",.5),verified:check("var(--green)"),
  refuted:cross("var(--red)"),exhausted:minus("var(--text-3)")}[s]||ring("var(--text-3)")}
const TYPE={goal:{c:"var(--indigo)",l:"Goal"},intent:{c:"var(--orange)",l:"Experiment"},fact:{c:"var(--blue)",l:"Claim"},finding:{c:"var(--purple)",l:"Finding"},hint:{c:"var(--gray)",l:"Lead"}};
const typeChip=t=>`<span class="chip"><i style="background:${TYPE[t]?.c||"var(--gray)"}"></i>${esc(TYPE[t]?.l||t)}</span>`;
const GATE_LABEL={replicated:"Replicated",stats_ok:"Statistics",figures_ok:"Figures",skeptic:"Skeptic review"};
const GATE_COLOR={replicated:"--green",stats_ok:"--blue",figures_ok:"--purple",skeptic:"--orange"};   // CSS tokens, resolved for the canvas charts
// Claims keep gates under metrics.gates; findings carry them as top-level booleans.
const gatesOf=n=>{const m=obj(n&&n.metrics);if(Object.keys(obj(m.gates)).length)return Object.entries(m.gates);
  return n&&n.node_type==="finding"?Object.keys(GATE_LABEL).filter(k=>typeof m[k]==="boolean").map(k=>[k,m[k]]):[]};
function gateDots(n){const g=gatesOf(n);if(!g.length)return"";const ok=g.filter(([,v])=>v).length;
  return `<span class="gates" title="${esc(g.map(([k,v])=>(v?"✓ ":"✕ ")+(GATE_LABEL[k]||k)).join("\n"))}" aria-label="${ok} of ${g.length} checks passed">${g.map(([,v])=>`<i class="${v?"ok":""}"></i>`).join("")}</span>`}
function gateChips(n){const g=gatesOf(n);if(!g.length)return"";
  return `<div class="sep"></div><h4>Verification checks</h4><div class="gchips">${g.map(([k,v])=>`<span class="chip ${v?"pass":"fail"}">${v?"✓":"✕"} ${esc(GATE_LABEL[k]||k)}</span>`).join("")}</div>`}
const STATUS_LABEL={open:"Open",claimed:"Claimed",running:"Running",verified:"Verified",refuted:"Refuted",exhausted:"Exhausted"};

/* ---------- state ---------- */
const jsonLS=(k,d)=>{try{const v=JSON.parse(ls.get(k,""));return Array.isArray(v)?v:d}catch{return d}};
const S={me:null,projects:null,proj:null,projTimer:0,next:"",campaigns:null,route:{},summary:null,graph:null,manuscript:undefined,selected:null,prov:{},timer:null,msView:"paper",lastView:"",
  panel:{mode:ls.get("plato_panel")==="split"?"split":"panel",view:"details",auto:new Set()},
  draft:undefined,firstDraft:null,draftTimer:null,draftBusy:false,paperEl:null,lp:null,lpRaf:0,follow:true,
  res:{q:"",filter:"all",sort:null,page:0,size:[10,25,50].includes(+ls.get("plato_grid_size"))?+ls.get("plato_grid_size"):10,dense:ls.get("plato_grid_dense")==="1",hidden:new Set(jsonLS("plato_grid_hidden",[]))},
  rows:null,rowsFor:null,usage:undefined,usageKey:null,t0:0};

/* ---------- API ---------- */
class ApiError extends Error{constructor(m,status){super(m);this.status=status}}
async function api(path,opt={}){
  const r=await fetch("/api/"+path,opt);   // the session cookie rides along (same origin)
  if(!r.ok){let m=`Request failed (${r.status})`;try{m=(await r.json()).error||m}catch{}
    if(r.status===401&&!/^(auth\/|me$)/.test(path))signedOut();throw new ApiError(m,r.status)}
  return r}
const getJSON=p=>api(p).then(r=>r.json());

/* ---------- toasts ---------- */
function toast(msg,bad){const el=document.createElement("div");el.className="toast";el.innerHTML=(bad?cross("var(--red)"):check("var(--green)"))+`<span>${esc(msg)}</span>`;
  $("#toasts").append(el);setTimeout(()=>el.remove(),4500)}

/* ---------- theme ---------- */
const themeText=()=>document.documentElement.dataset.theme==="dark"?"Light theme":"Dark theme";
$("#themeBtn").onclick=()=>savePref("theme",document.documentElement.dataset.theme==="dark"?"light":"dark");
$("#themeLbl").textContent=themeText();

/* ---------- health ---------- */
function setHealth(ok,text){$("#health").innerHTML=`<span class="dot ${ok?"ok":"bad"}"></span><span class="trunc">${esc(text)}</span>`}
async function health(){if(!S.me?.account)return;
  try{const h=await getJSON("health");setHealth(true,`Connected · ${h.model}`)}catch(e){if(e.status!==401)setHealth(false,"API unreachable")}}

/* ---------- routing ----------
   #/ (home: the agent or campaigns, per preference)  #/agent  #/campaigns  #/p/<project>
   #/c/<campaign>/<tab>  #/settings/<section>  #/login  #/signup */
const dec=s=>{try{return decodeURIComponent(s)}catch{return ""}};
function parseRoute(){const p=location.hash.replace(/^#\/?/,"").split("/").map(dec);
  if(p[0]==="c"&&p[1])return {view:"campaign",id:p[1],tab:p[2]||"overview",node:p[3]||null};
  if(p[0]==="p"&&p[1])return {view:"project",pid:p[1]};
  if(p[0]==="settings")return {view:"settings",section:p[1]||"preferences"};
  if(["login","signup","agent","campaigns"].includes(p[0]))return {view:p[0]};
  return {view:pref("home")==="campaigns"?"campaigns":"agent"}}
const go=(id,tab="overview")=>{location.hash=id?`#/c/${eid(id)}/${tab}`:"#/campaigns"};
addEventListener("hashchange",route);

/* ---------- skeleton samples: the real views rendered with representative data ---------- */
const SAMPLE=(()=>{const t=new Date().toISOString(),id=i=>"00000000-0000-4000-8000-0000000000"+String(i).padStart(2,"0");
  const Q=["Does the nominal 95% interval for the OLS slope keep its coverage under heteroskedastic errors","Do HC3 standard errors restore nominal coverage at small sample sizes","Is the percentile bootstrap interval conservative for skewed residuals"];
  const campaign={id:id(0),research_question:Q[0],status:"investigating",tokens_used:120000,token_budget_max:2000000,gpu_seconds_used:420,gpu_seconds_max:86400,created_at:t,updated_at:t,program_domain:"statistics",config:{model:"claude-haiku-5-5",workers:4,max_rounds:2}};
  const titles=["Classical interval coverage falls to 0.89 when the variance grows with x","HC3 errors bring coverage back within one point of nominal","The slope estimate stays unbiased across all four designs",
    "Percentile bootstrap undercovers at n = 20 with skewed errors","The coverage gap shrinks once the sample passes 200","Wild bootstrap matches HC3 at every sample size tested"];
  const fact=(title,i)=>({id:id(i+1),node_type:"fact",status:i<3?"verified":"refuted",title,hypothesis_or_spec:"Sample observation text for the claim.",created_at:t,confidence_score:.8,
    metrics:{primary_metric:"coverage_rate",coverage_rate:.95-i*.01,coverage_rate_se:.004,p_value:.01,test_kind:"difference",gates:{replicated:true,stats_ok:true,figures_ok:true,skeptic:i<3},replication:{coverage_rate:.95-i*.012}}});
  const nodes=[{id:id(0),node_type:"goal",status:"open",title:"Research question",metrics:{},created_at:t},...titles.map(fact)];
  return {summary:{campaign,node_counts:[{node_type:"fact",status:"verified",n:3},{node_type:"fact",status:"refuted",n:3},{node_type:"intent",status:"verified",n:4}],
      guard_events:[0,1,2].map(()=>({kind:"sandbox",decision:"allow",detail:{node:"execute_intent"},created_at:t}))},
    graph:{nodes,edges:[]},campaigns:Q.map((q,i)=>({...campaign,id:id(i),research_question:q,status:i?"completed":"investigating"}))}})();
function sampleHtml(fn){const keep=[S.summary,S.graph,S.selected,S.prov,S.panel.view,S.manuscript,S.draft];
  Object.assign(S,{summary:SAMPLE.summary,graph:SAMPLE.graph,selected:null,prov:{},manuscript:undefined,draft:undefined});S.panel.view="details";
  try{return fn()}finally{[S.summary,S.graph,S.selected,S.prov,S.panel.view,S.manuscript,S.draft]=keep}}
const LINE="Sample text standing in for a typical line of the paper body ";
const paperSample=()=>`<h1>Coverage of the ordinary least squares slope interval under heteroskedastic errors</h1><p class="by">Plato autonomous scientist</p>
  <div class="abs"><b>Abstract.</b> ${LINE.repeat(5)}</div><h2>Introduction</h2><p>${LINE.repeat(6)}</p><p>${LINE.repeat(4)}</p><h2>Methods</h2><p>${LINE.repeat(5)}</p>`;

/* ---------- sidebar ---------- */
const ACTIVE=c=>!["completed","halted"].includes(c.status);
const NAV_CLOSED=new Set(jsonLS("plato_nav_closed",[]));   // collapsed sidebar sections, remembered
function renderNav(){if(S.route.view==="settings")return renderSettingsNav();
  const v=S.route.view,cur=S.route.id,list=S.campaigns||[],act=list.filter(ACTIVE),done=list.filter(c=>!ACTIVE(c));
  const link=(href,on,icon,label,attrs="")=>`<a class="item${on?" on":""}" href="${href}"${on?' aria-current="page"':""}${attrs}>${icon}${label}</a>`;
  const item=c=>link(`#/c/${eid(c.id)}/overview`,c.id===cur,campaignIcon(c.status),`<span class="trunc">${esc(c.research_question)}</span>`,` title="${esc(c.research_question)}"`);
  const pitem=p=>link(`#/p/${eid(p.id)}`,p.id===S.route.pid,pico(p.agent_status==="working"?SPIN:ico(CHAT)),`<span class="trunc">${esc(p.title)}</span>`,` title="${esc(p.title)}"`);
  const sec=(k,label,l,fn)=>{if(!l.length)return"";const open=!NAV_CLOSED.has(k);
    return `<button class="nav-h" type="button" data-sec="${k}" aria-expanded="${open}">${label}${ico('<path d="m5 6.5 3 3 3-3"/>',12)}<span class="n">${l.length}</span></button>`+(open?l.slice(0,30).map(fn).join(""):"")};
  $("#nav").innerHTML=link("#/agent",v==="agent",ico(SPARK),"Agent")+
    link("#/campaigns",v==="campaigns",ico('<rect x="2.5" y="2.5" width="11" height="11" rx="2.5"/><path d="M5.5 6h5M5.5 8.5h5M5.5 11h3"/>'),`All campaigns<span class="n">${list.length||""}</span>`)+
    sec("projects","Projects",S.projects||[],pitem)+sec("running","Running",act,item)+sec("finished","Finished",done,item)}
async function loadList(){if(!S.me?.account)return;try{S.campaigns=(await getJSON("campaigns")).campaigns;renderNav();if(S.route.view==="campaigns")renderHome()}
  catch(e){if(S.campaigns===null){S.campaigns=[];if(S.route.view==="campaigns")renderHome()}if(e.status!==401)toast(e.message,true)}}

/* ---------- home (campaign list) ---------- */
function homeRows(list){
  const groups=[["Running",list.filter(ACTIVE)],["Completed",list.filter(c=>c.status==="completed")],["Halted",list.filter(c=>c.status==="halted")]];
  return groups.filter(g=>g[1].length).map(([name,l])=>`<div class="group">${campaignIcon(l[0].status)}${name}<span class="n">${l.length}</span></div>`+
    l.map(c=>{const p=Math.min(100,100*c.tokens_used/Math.max(1,c.token_budget_max));
      return `<a class="row" href="#/c/${eid(c.id)}/overview" style="text-decoration:none;color:inherit"><span class="id mono">${cid(c.id)}</span>${campaignIcon(c.status)}<span class="title trunc">${esc(c.research_question)}</span>
      <span class="meta"><span class="chip hide-sm" data-mk="home:ph:${esc(c.id)}">${esc(PHASE_LABEL[c.status]||c.status)}</span><span class="hide-sm" title="${fmt(c.tokens_used)} / ${fmt(c.token_budget_max)} tokens" style="display:flex;align-items:center;gap:6px"><span class="bar"><span style="width:${p}%"></span></span><span data-mk="home:tok:${esc(c.id)}" data-num data-v="${c.tokens_used}">${short(c.tokens_used)}</span></span><span style="width:64px;text-align:right">${ago(c.created_at)}</span></span></a>`}).join("")).join("")}
function renderHome(){
  $("#crumb").innerHTML=`<b>Campaigns</b>`;$("#tabs").innerHTML="";$("#tabs").className="";
  $("#topActions").innerHTML=`<button class="btn primary" id="newTop" type="button">New campaign</button>`;$("#newTop").onclick=openNew;
  const body=$("#body");body.className="body full";S.lastView="";
  if(S.campaigns===null){body.innerHTML=`<div class="pane" id="pane"></div>`;Kit.skeleton($("#pane"),homeRows(SAMPLE.campaigns),"home");return}
  if(!S.campaigns.length){body.innerHTML=`<div class="pane" id="pane"><div class="empty"><div>${ring("var(--text-3)",0,true)}<h3>No campaigns yet</h3>
    <p>Give Plato a question or idea. A swarm of agents researches it, runs experiments and writes up what holds.</p><button class="btn primary" type="button" id="newEmpty">New campaign</button></div></div></div>`;$("#newEmpty").onclick=openNew;Kit.reveal($("#pane"),"home");return}
  const sc=$("#pane")?.scrollTop||0;
  body.innerHTML=`<div class="pane" id="pane"><div data-seq>${homeRows(S.campaigns)}</div></div>`;$("#pane").scrollTop=sc;
  Kit.hydrate(body);Kit.reveal($("#pane"),"home")}

/* ---------- campaign view ---------- */
const TABS=[["overview","Overview"],["results","Results"],["graph","Graph"],["findings","Findings"],["experiments","Experiments"],["manuscript","Manuscript"],["guardrails","Guardrails"]];
function resetCampaignState(){clearTimeout(S.draftTimer);cancelAnimationFrame(S.lpRaf);
  Object.assign(S,{summary:null,graph:null,manuscript:undefined,prov:{},draft:undefined,firstDraft:null,draftTimer:null,paperEl:null,lp:null,lpRaf:0,follow:pref("follow_live_writing"),rows:null,rowsFor:null,lastView:"",usage:undefined,usageKey:null,t0:0});
  S.res.page=0;S.panel.view="details";if(S.panel.mode==="focus")S.panel.mode="panel"}
async function openCampaign(id){
  const fresh=S.summary?.campaign?.id!==id;
  if(fresh){resetCampaignState();
    const body=$("#body"),full=S.route.tab==="manuscript";body.className="body "+(full?"full":"mode-"+S.panel.mode);
    body.innerHTML=`<div class="pane" id="pane"></div>`+(full?"":`<aside class="props" id="props"></aside>`);
    $("#tabs").className="tabs";$("#tabs").innerHTML=TABS.map(([k,l])=>`<span class="tab${S.route.tab===k?" on":""}">${l}</span>`).join("");
    Kit.skeleton($("#crumb"),`<b>${esc(SAMPLE.summary.campaign.research_question.slice(0,60))}</b>`,"crumb");$("#topActions").innerHTML="";
    Kit.skeleton($("#pane"),sampleHtml(()=>full?`<div class="paper">${paperSample()}</div>`:tabView(S.route.tab)),"pane");
    if(!full)Kit.skeleton($("#props"),sampleHtml(propsView),"props")}
  try{const [s,g]=await Promise.all([getJSON("campaigns/"+id),getJSON("campaigns/"+id+"/graph")]);if(S.route.id!==id)return;S.summary=s;S.graph=g}
  catch(e){if(S.route.id!==id)return;$("#crumb").innerHTML=`<b>Campaign</b>`;$("#body").className="body full";
    $("#body").innerHTML=`<div class="pane" id="pane"><div class="empty"><div>${cross("var(--red)")}<h3>${e.status===404?"Campaign not found":"Could not load campaign"}</h3><p>${esc(e.message)}</p></div></div></div>`;
    ["crumb","pane","props"].forEach(k=>Kit.reveal(document.getElementById(k),k));return}
  renderCampaign();["crumb","pane","props"].forEach(k=>Kit.reveal($("#"+k),k));schedulePoll();loadUsage();renderAskCtx();
  if(S.summary.campaign.status==="writing")pollDraft();
}
function counts(){const out={};(S.summary?.node_counts||[]).forEach(r=>{(out[r.node_type]??={})[r.status]=r.n});return out}
const sum=o=>Object.values(o||{}).reduce((a,b)=>a+b,0);
function renderCampaign(){
  const c=S.summary.campaign,nodes=S.graph.nodes,cnt=counts();
  $("#crumb").innerHTML=`<a href="#/campaigns" style="text-decoration:none">Campaigns</a><span class="t3">›</span>${campaignIcon(c.status)}<b class="trunc">${esc(c.research_question)}</b>`;
  const act=$("#topActions");
  if(ACTIVE(c)){if(!$("#resume")){act.innerHTML=`<button class="btn" id="resume" type="button" title="Ask the runner to resume now"><span data-lbl>Resume</span></button>`;
      $("#resume").onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await api(`campaigns/${c.id}/run`,{method:"POST"});Kit.flash(b,"Requested",2200)}catch(err){toast(err.message,true)}finally{b.disabled=false}}}}
  else act.innerHTML="";
  const n={findings:nodes.filter(x=>x.node_type==="finding"||x.node_type==="fact").length,experiments:sum(cnt.intent),guardrails:S.summary.guard_events.length};
  $("#tabs").className="tabs";
  $("#tabs").innerHTML=TABS.map(([k,l])=>`<a class="tab${S.route.tab===k?" on":""}" href="#/c/${eid(c.id)}/${k}" style="text-decoration:none"${S.route.tab===k?' aria-current="page"':""}>${l}${n[k]!=null?`<span class="c">${n[k]}</span>`:""}</a>`).join("");
  renderTab();
}
function tabView(tab){return ({overview,results:resultsView,graph:graphView,findings:findingsView,experiments:experimentsView,manuscript:manuscriptView,guardrails:guardView}[tab]||overview)()}
/* Re-rendering the same view (live polling) keeps focus, caret and scroll positions. */
function keepUI(){const a=document.activeElement,o={id:a&&a.id&&$("#body").contains(a)?a.id:null,ss:null,se:null,sc:{}};
  try{o.ss=a.selectionStart;o.se=a.selectionEnd}catch{}
  ["pane","props","gwrap"].forEach(id=>{const e=document.getElementById(id);if(e)o.sc[id]=[e.scrollTop,e.scrollLeft]});return o}
function restoreUI(o){for(const [id,[t,l]] of Object.entries(o.sc)){const e=document.getElementById(id);if(e){e.scrollTop=t;e.scrollLeft=l}}
  if(o.id){const e=document.getElementById(o.id);if(e){e.focus({preventScroll:true});try{if(o.ss!=null)e.setSelectionRange(o.ss,o.se)}catch{}}}}
function renderTab(){
  const tab=S.route.tab,body=$("#body"),key=S.route.id+"/"+tab,ui=S.lastView===key?keepUI():null;S.lastView=key;
  const full=tab==="manuscript";autoPanel();
  if(tab==="manuscript"||S.panel.view==="paper")ensureManuscript();
  body.className="body "+(full?"full":"mode-"+S.panel.mode);
  body.innerHTML=`<div class="pane" id="pane">${tabView(tab)}</div>`+(full?"":`<aside class="props" id="props" aria-label="Details panel">${propsView()}</aside>`);
  mountPaper();bindPane();bindProps();mountCharts();Kit.hydrate(body,S.route.id+":");Kit.paint(body);if(ui)restoreUI(ui);KB=-1;
}
function refreshProps(keepScroll=true){const p=$("#props");if(!p||!S.summary)return;const st=p.scrollTop;
  if(S.panel.view==="paper")ensureManuscript();
  p.innerHTML=propsView();mountPaper();bindProps();Kit.hydrate(p,S.route.id+":");Kit.paint(p);if(keepScroll)p.scrollTop=st}

/* ---------- right panel: Details | Paper, in three zoom states ---------- */
const PANEL=[["panel","Side panel","[",'<rect x="2" y="3" width="12" height="10" rx="2"/><path d="M10.5 3v10"/>'],["split","Split view","",'<rect x="2" y="3" width="12" height="10" rx="2"/><path d="M8 3v10"/>'],
  ["focus","Focus panel","]",'<path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9"/>']];
const wide=()=>innerWidth>1100;
const msExists=c=>c.status==="completed"||(c.status==="halted"&&c.halted_from==="writing");
const paperAvail=()=>{const c=S.summary.campaign;return c.status==="writing"||msExists(c)||!!S.draft?.stage||(S.manuscript&&typeof S.manuscript==="object")};
function autoPanel(){const c=S.summary.campaign;   // writing starts: open the paper beside the work, once per campaign
  if(c.status!=="writing"||S.panel.auto.has(c.id)||!wide()||!pref("open_paper_while_writing"))return;S.panel.auto.add(c.id);S.panel.view="paper";if(S.panel.mode==="panel")S.panel.mode="split"}
function setPanel(mode,view){
  if(!S.summary||S.route.tab==="manuscript")return;
  if(!wide()){if(view&&view!==S.panel.view){S.panel.view=view;refreshProps(false)}return}
  if(mode===S.panel.mode&&(!view||view===S.panel.view))return;
  Kit.transition(()=>{S.panel.mode=mode;if(view)S.panel.view=view;if(mode!=="focus")ls.set("plato_panel",mode);
    $("#body").className="body mode-"+mode;refreshProps(!view)})}
function stepPanel(d){const order=["panel","split","focus"],i=order.indexOf(S.panel.mode);setPanel(order[Math.max(0,Math.min(2,i+d))])}
function panelHead(){
  const av=paperAvail(),v=av?S.panel.view:"details",writing=S.summary.campaign.status==="writing";
  const tab=(k,l,extra="")=>`<button type="button" role="tab" data-pv="${k}" aria-selected="${v===k}" class="${v===k?"on":""}">${extra}${l}</button>`;
  return `<div class="ph"><div class="seg" role="tablist" aria-label="Panel view">${tab("details","Details")}${av?tab("paper","Paper",writing?'<span class="live" style="--c:var(--blue);width:6px;height:6px"></span>':""):""}</div>
    <div class="zoom" role="radiogroup" aria-label="Panel size">${PANEL.map(([m,l,k,d])=>`<button type="button" role="radio" data-pm="${m}" aria-checked="${S.panel.mode===m}" title="${l}${k?` (${k})`:""}" aria-label="${l}">${ico(d)}</button>`).join("")}</div></div>`}
function propsView(){
  const node=S.selected&&S.graph.nodes.find(n=>n.id===S.selected);
  const inner=paperAvail()&&S.panel.view==="paper"?`<div id="paperSlot"></div>`:node?nodeProps(node):campaignProps();
  return panelHead()+inner}
function campaignProps(){
  const c=S.summary.campaign,cfg=c.config||{};
  return `<div class="pp"><h4>Properties</h4>
  <div class="prop"><span>Status</span><span>${campaignIcon(c.status)}<span data-mk="pstatus">${PHASE_LABEL[c.status]||esc(c.status)}</span></span></div>
  <div class="prop"><span>Model</span><span class="trunc">${esc(cfg.model||"claude-haiku-5-5")}</span></div>
  <div class="prop"><span>Workers</span><span>${esc(cfg.workers??"–")}</span></div>
  <div class="prop"><span>Rounds</span><span>${esc(cfg.max_rounds??"–")}</span></div>
  <div class="prop"><span>Domain</span><span class="trunc">${esc(c.program_domain||"general")}</span></div>
  <div class="prop"><span>Created</span><span>${when(c.created_at)}</span></div>
  <div class="prop"><span>Updated</span><span>${ago(c.updated_at)}</span></div>
  <div class="sep"></div><h4>Graph</h4>
  ${Object.entries(counts()).map(([t,st])=>`<div class="prop"><span>${typeChip(t)}</span><span class="t2">${Object.entries(st).map(([k,v])=>`${v} ${k}`).join(" · ")}</span></div>`).join("")||'<p class="t3">Empty</p>'}
  <div class="sep"></div><div class="prop"><span>ID</span><span class="mono t3 trunc" title="${esc(c.id)}">${esc(c.id)}</span></div>
  <p class="t3" style="font-size:12px;margin-top:12px">Select any node to see its evidence and lineage.</p></div>`}
const EV_LABEL={stdout_log:"Run log",git_patch:"Code",plot_png:"Plot",vlm_critique:"Figure critique",sealed_eval_json:"Sealed evaluation",latex_section:"LaTeX",bibtex:"BibTeX",peer_review:"Peer review",citation_report:"Citation checks",evidence_matrix:"Claim support",review_panel:"Reviewer panel"};
function evIcon(t){const p={plot_png:'<rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="m4.5 10.5 2.5-3 2 2 2.5-3.5"/>',git_patch:'<path d="m6 4.5-3.5 3.5L6 11.5m4-7 3.5 3.5-3.5 3.5"/>',stdout_log:'<rect x="2.5" y="3" width="11" height="10" rx="2"/><path d="m5 6.5 2 1.5-2 1.5M8.5 10h2.5"/>'}[t]||'<path d="M4 2.5h5l3 3v8H4z"/><path d="M9 2.5v3h3"/>';
  return `<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--text-2)" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`}
const evRow=e=>`<div class="lin" role="button" tabindex="0" data-ev="${esc(e.id)}" data-type="${esc(e.artifact_type)}">${evIcon(e.artifact_type)}<span class="trunc">${esc(EV_LABEL[e.artifact_type]||e.artifact_type)}</span><span class="t3 mono" style="margin-left:auto;font-size:11px">${esc(e.sha256_checksum.slice(0,8))}</span></div>`;
const EV_SAMPLE=["git_patch","stdout_log","plot_png"].map((t,i)=>evRow({id:"s"+i,artifact_type:t,sha256_checksum:"0000000000"})).join("");
function nodeProps(n){
  const p=S.prov[n.id],m=obj(n.metrics),pk=typeof m.primary_metric==="string"?m.primary_metric:null;
  // Gate booleans render as chips; the primary metric gets its own row; the rest is a table.
  const metrics=Object.entries(m).filter(([k])=>!["gates","primary_metric","replication","test_kind",pk,pk&&pk+"_se",...Object.keys(GATE_LABEL)].includes(k));
  const f=v=>typeof v==="number"?String(+v.toPrecision(5)):JSON.stringify(v);
  const rep=pk?obj(m.replication)[pk]:undefined;
  // A finding's code, logs and plots live on the claim that proves it.
  const provers=p?p.edges.filter(e=>e.edge_type==="proves"&&e.target_node_id===n.id).map(e=>p.nodes.find(x=>x.id===e.source_node_id)).filter(Boolean):[];
  const evGroups=p?[[null,p.evidence.filter(e=>e.node_id===n.id)],...provers.map(x=>[x,p.evidence.filter(e=>e.node_id===x.id)])].filter(([,l])=>l.length):[];
  const lineage=p?p.nodes.filter(x=>x.id!==n.id):[],anchors=p?p.anchors:[];
  return `<div class="pp"><div style="display:flex;align-items:center;gap:8px"><button class="icon-btn" type="button" data-close aria-label="Back to properties">${ico('<path d="M10 3 5 8l5 5"/>')}</button>${typeChip(n.node_type)}<span class="chip">${nodeIcon(n.status)}${STATUS_LABEL[n.status]||esc(n.status)}</span></div>
  <div class="node-t">${esc(n.title)}</div>
  ${n.hypothesis_or_spec?`<div class="para">${esc(n.hypothesis_or_spec)}</div>`:""}
  ${n.confidence_score!=null?`<div class="sep"></div><div class="prop"><span>Confidence</span><span><span class="bar" style="width:90px"><span style="width:${Math.round(100*n.confidence_score)}%"></span></span>${Number(n.confidence_score).toFixed(2)}</span></div>`:""}
  ${gateChips(n)}
  ${pk&&pk in m?`<div class="sep"></div><h4>Primary metric</h4><div class="prim"><span class="mono t2" title="${esc(pk)}">${esc(pk)}</span><span class="pv">${esc(f(m[pk]))}</span>${m[pk+"_se"]!=null?`<span class="t3">± ${esc(f(m[pk+"_se"]))} SE</span>`:""}${rep!==undefined?`<span class="t3">seed 2: ${esc(f(rep))}</span>`:""}${m.test_kind?`<span class="chip">${esc(m.test_kind)} test</span>`:""}</div>`:""}
  ${metrics.length?`<div class="sep"></div><h4>Metrics</h4><div class="kv mono">${metrics.slice(0,24).map(([k,v])=>`<span title="${esc(k)}">${esc(k)}</span><span title="${esc(JSON.stringify(v))}">${esc(f(v))}</span>`).join("")}</div>`:""}
  <div class="sep"></div><h4>Evidence</h4>
  ${!p?Kit.skel(EV_SAMPLE):evGroups.length?evGroups.map(([x,l])=>(x?`<div class="t3" style="font-size:11px;margin:6px 0 2px">From claim · ${esc(x.title)}</div>`:"")+l.map(evRow).join("")).join(""):'<p class="t3">No artifacts on this node.</p>'}
  ${anchors.length?`<div class="sep"></div><h4>Sources</h4>${anchors.slice(0,12).map(a=>`<div class="lin" style="cursor:default"><span class="chip">${esc(a.anchor_role)}</span><span class="trunc" title="${esc(a.canonical_name)}">${esc(a.canonical_name)}</span></div>`).join("")}`:""}
  ${lineage.length?`<div class="sep"></div><h4>Lineage</h4>${lineage.slice(0,20).map(x=>`<div class="lin" role="button" tabindex="0" data-node="${esc(x.id)}">${nodeIcon(x.status)}<span class="trunc">${esc(x.title)}</span></div>`).join("")}`:""}
  </div>`}
async function selectNode(id){
  S.selected=id;S.panel.view="details";
  document.querySelectorAll("#pane [data-node].on").forEach(e=>e.classList.remove("on"));document.querySelectorAll(`#pane [data-node="${CSS.escape(id)}"]:not(button)`).forEach(e=>e.classList.add("on"));
  refreshProps(false);
  if(!S.prov[id]){try{S.prov[id]=await getJSON("nodes/"+id+"/provenance")}catch(e){toast(e.message,true);return}if(S.selected===id&&S.panel.view==="details")refreshProps()}
  if(!wide())$("#props")?.scrollIntoView({behavior:Kit.still()?"auto":"smooth",block:"start"});
}
function bindProps(){const p=$("#props");if(!p)return;
  p.onclick=e=>{const t=e.target.closest("[data-node],[data-close],[data-ev],[data-pv],[data-pm],[data-copy],[data-follow],[data-open-ms]");if(!t||!p.contains(t))return;
    if(t.dataset.pv){if(t.dataset.pv!==S.panel.view){if(t.dataset.pv==="paper"&&S.panel.mode==="panel"&&wide())setPanel("split","paper");else{S.panel.view=t.dataset.pv;refreshProps(false)}}}
    else if(t.dataset.pm)setPanel(t.dataset.pm);
    else if(t.dataset.close!=null){S.selected=null;refreshProps(false);document.querySelectorAll("#pane [data-node].on").forEach(x=>x.classList.remove("on"))}
    else if(t.dataset.ev)openEvidence(t.dataset.ev,t.dataset.type);
    else if(t.dataset.copy)copyPaper(t);
    else if(t.dataset.follow!=null)follow(true);
    else if(t.dataset.openMs!=null)go(S.route.id,"manuscript");
    else if(t.dataset.node)selectNode(t.dataset.node)};
  p.onkeydown=e=>{if((e.key==="Enter"||e.key===" ")&&e.target.matches(".lin[role=button]")){e.preventDefault();e.target.click()}}}

/* ---------- overview ---------- */
function overview(){
  const c=S.summary.campaign,cnt=counts(),halted=c.status==="halted",idx=PHASES.indexOf(c.status),reached=halted?Math.max(0,lastPhase()):idx;
  const steps=PHASES.map((p,i)=>{const done=i<reached||(c.status==="completed"),cur=i===reached&&!halted&&c.status!=="completed",fail=halted&&i===reached;
    return (i?`<span class="link${done||cur||fail?" done":""}"></span>`:"")+`<span class="step${done?" done":""}${cur?" cur":""}${fail?" fail":""}">${fail?cross("var(--red)"):done?check("var(--accent)"):cur?campaignIcon(p):ring("var(--text-3)")}<span class="sl">${PHASE_LABEL[p]}</span></span>`}).join("");
  const verified=cnt.finding?.verified||0,claimsV=cnt.fact?.verified||0,claimsR=cnt.fact?.refuted||0,claimsO=(cnt.fact?.open||0)+(cnt.fact?.claimed||0)+(cnt.fact?.running||0);
  const exps=sum(cnt.intent),expsDone=(cnt.intent?.verified||0)+(cnt.intent?.refuted||0);
  let call="";
  if(halted)call=`<div class="callout bad">${cross("var(--red)")}<div><b>Halted.</b> <span class="t2">${esc(c.halted_reason||"No reason recorded.")}</span></div></div>`;
  else if(c.status==="completed")call=`<div class="callout ${verified?"good":""}">${verified?check("var(--green)"):minus("var(--text-2)")}<div><b>${verified?`${verified} verified finding${verified>1?"s":""}.`:"Completed with no verified finding."}</b>
    <span class="t2">${claimsR} claim${claimsR===1?"":"s"} refuted, ${claimsV} supported across ${exps} experiment${exps===1?"":"s"}. ${verified?"":"Negative results are recorded in the graph and the manuscript."}</span></div></div>`;
  else call=`<div class="callout"><span class="live" style="margin:6px 2px 0"></span><div style="flex:1;min-width:0"><b data-mk="phase">${PHASE_LABEL[c.status]}</b><span class="t2"> · <span data-mk="phint">${esc(PHASE_HINT[c.status]||"The swarm is working.")}</span></span></div>${c.status==="writing"&&wide()?'<button class="btn" type="button" data-pv="paper">Watch the paper</button>':""}</div>`;
  const root=S.graph.nodes.find(x=>x.node_type==="goal"&&x.title==="Research question"),rm=obj(root&&root.metrics),rq=rm.refined_question;
  const judged=judgedFacts(),allPass=judged.filter(passedAll).length;
  const rounds=num(rm.rounds_completed)??0,maxR=num(obj(c.config).max_rounds)??0;
  const ev=S.summary.guard_events.slice(0,12);
  return `<div class="doc"><div data-seq><div><h1>${esc(c.research_question)}</h1>${rq&&rq!==c.research_question?`<p class="refined">${esc(rq)}</p>`:""}
  <div class="sub" style="margin-top:10px"><span class="mono t3">${cid(c.id)}</span>${typeChip("goal")}<span>${esc(c.program_domain||"general")}</span><span class="t3">·</span><span>Started ${ago(c.created_at)}</span></div></div>
  <div class="steps">${steps}</div>${call}
  <div class="stats">
    <div class="stat"><div class="k">Experiments</div><div class="v"><span data-mk="exd" data-num data-v="${expsDone}">${expsDone}</span> <small>/ <span data-mk="ext" data-num data-v="${exps}">${exps}</span> done</small></div><div class="t3" style="font-size:12px">${cnt.intent?.exhausted||0} out of attempts</div></div>
    <div class="stat"><div class="k">Claims</div><div class="v" data-mk="cla" data-num data-v="${claimsV+claimsR+claimsO}">${claimsV+claimsR+claimsO}</div><div style="display:flex;gap:8px;font-size:12px" class="t2"><span style="color:var(--green)">${claimsV} ✓</span><span style="color:var(--red)">${claimsR} ✕</span><span>${claimsO} open</span></div></div>
    <div class="stat"><div class="k">Verified findings</div><div class="v" data-mk="fnd" data-num data-v="${verified}">${verified}</div><div class="t3" style="font-size:12px">${judged.length?`${allPass} of ${judged.length} judged claims`:"None judged yet"}</div></div>
    <div class="stat"><div class="k">Rounds</div><div class="v"><span data-mk="rnd" data-num data-v="${rounds}">${rounds}</span> <small>/ ${maxR||"–"}</small></div><div class="bar wide"><span style="width:${maxR?Math.min(100,100*rounds/maxR):0}%"></span></div></div>
  </div>
  <div class="charts"><section class="card"><div class="card-h"><b>Research progress</b><span class="t3">Experiments finished, claims supported or refuted, and findings verified, over the run</span></div>
      ${chartSlot("progress",220,`Research progress: ${expsDone} of ${exps} experiments finished, ${claimsV} claims verified, ${claimsR} refuted, ${verified} findings verified`)}</section>
    <section class="card"><div class="card-h"><b>Token burn</b><span class="t3"><span data-mk="tokv">${short(c.tokens_used)}</span> of ${short(c.token_budget_max)} tokens · sandbox <span data-mk="gpuv">${short(c.gpu_seconds_used)}s</span> of ${short(c.gpu_seconds_max)}s</span></div>
      ${chartSlot("burn",220,`Token burn: ${fmt(c.tokens_used)} of ${fmt(c.token_budget_max)} tokens used, ${fmt(c.gpu_seconds_used)} of ${fmt(c.gpu_seconds_max)} sandbox seconds`)}</section></div>
  <div><div class="sec-h">Guardrail activity</div>
  ${ev.length?`<div class="feed">${ev.map(e=>`<div class="ev ${esc(e.decision)}"><b>${esc(e.kind)}</b> ${esc(e.decision)}${e.detail?.node?` in <span class="mono">${esc(e.detail.node)}</span>`:""}${e.detail?.error?` · <span class="t3">${esc(String(e.detail.error).slice(0,140))}</span>`:""}<span class="t3"> · ${ago(e.created_at)}</span></div>`).join("")}</div>`:`<p class="t3">No guardrail events. Every sandbox run, budget check and data-scope check passed.</p>`}</div>
  </div></div>`}
function lastPhase(){// phase a halted campaign stopped in: recorded by the store; inferred for older campaigns
  const from=PHASES.indexOf(S.summary.campaign.halted_from);if(from>=0)return from;
  const cnt=counts();if(sum(cnt.intent)===0)return 0;if((cnt.finding&&sum(cnt.finding))||S.manuscript)return 4;return 1}

/* ---------- results: verification over time + advanced data grid ---------- */
const STATUS_RANK={verified:0,running:1,claimed:2,open:3,refuted:4,exhausted:5};
function resultRows(){
  if(S.rowsFor===S.graph&&S.rows)return S.rows;
  const nodes=S.graph.nodes,byId=new Map(nodes.map(n=>[n.id,n])),proverOf=new Map(),provedBy=new Map();
  S.graph.edges.forEach(e=>{if(e.edge_type==="proves"){proverOf.set(e.target_node_id,byId.get(e.source_node_id));provedBy.set(e.source_node_id,byId.get(e.target_node_id))}});
  const relTol=num(obj(S.summary.campaign.config).replication_rel_tolerance)??0.10;
  const rows=nodes.filter(n=>n.node_type==="fact"||n.node_type==="finding").map(n=>{
    const m=obj(n.metrics),fact=n.node_type==="finding"?obj(proverOf.get(n.id)?.metrics):m,twin=n.node_type==="fact"?obj(provedBy.get(n.id)?.metrics):{};
    const pk=typeof m.primary_metric==="string"?m.primary_metric:typeof fact.primary_metric==="string"?fact.primary_metric:null;
    // Seed-2 values: on the node (new campaigns), else on the finding it proves / the claim behind it.
    const rep=Object.keys(obj(m.replication)).length?obj(m.replication):Object.keys(obj(twin.replication)).length?obj(twin.replication):obj(fact.replication);
    const v1=pk?num(m[pk])??num(fact[pk]):null,v2=pk?num(rep[pk]):null,se1=pk?num(fact[pk+"_se"]):null,se2=pk?num(rep[pk+"_se"]):null;
    // Same rule as nodes.replicates(): within 3 combined SEs or the relative tolerance.
    const rel=v1!=null&&v2!=null?relTol*Math.max(Math.abs(v1),Math.abs(v2)):null,seTol=se1!=null&&se2!=null?3*Math.hypot(se1,se2):null;
    const tol=rel!=null||seTol!=null?Math.max(rel??0,seTol??0):null,tolKind=seTol!=null&&seTol>=(rel??0)?"3 combined SE":`${Math.round(relTol*100)}% relative`;
    const drift=v1!=null&&v2!=null?(tol>0?(v2-v1)/tol:v1===v2?0:null):null;
    const g=Object.fromEntries(gatesOf(n));
    const replicated=typeof g.replicated==="boolean"?g.replicated:drift!=null?Math.abs(drift)<=1:null;
    return {id:n.id,type:n.node_type,status:n.status,title:n.title,pk,v1,v2,se1,se2,tol,tolKind,drift,replicated,p:num(fact.p_value),test:typeof fact.test_kind==="string"?fact.test_kind:null,
      gates:Object.keys(g).length?g:null,conf:num(n.confidence_score),created:n.created_at}});
  S.rowsFor=S.graph;return S.rows=rows}
const RES_FILTERS=[["all","All results",()=>true,"var(--accent)"],["findings","Findings",r=>r.type==="finding","var(--purple)"],["verified","Verified claims",r=>r.type==="fact"&&r.status==="verified","var(--green)"],
  ["refuted","Refuted",r=>r.status==="refuted","var(--red)"],["pending","In progress",r=>["open","claimed","running"].includes(r.status),"var(--yellow)"]];
const fmtDrift=d=>d==null?"–":(d<0?"−":"+")+Math.abs(d).toFixed(2)+"×";
const dash='<span class="t3">–</span>';
const RES_COLS=[
  {k:"status",l:"Status",pin:1,sort:r=>STATUS_RANK[r.status]??9,csv:r=>r.status,cell:r=>`<span title="${esc(STATUS_LABEL[r.status]||r.status)}">${nodeIcon(r.status)}<span class="sr">${esc(STATUS_LABEL[r.status]||r.status)}</span></span>`},
  {k:"title",l:"Result",pin:2,sort:r=>r.title.toLowerCase(),csv:r=>r.title,cell:r=>`<span class="gt" title="${esc(r.title)}">${esc(r.title)}</span>`},
  {k:"kind",l:"Kind",sort:r=>r.type,csv:r=>TYPE[r.type]?.l,cell:r=>typeChip(r.type)},
  {k:"metric",l:"Metric",sort:r=>r.pk,csv:r=>r.pk,cell:r=>r.pk?`<span class="mono t2">${esc(r.pk)}</span>`:dash},
  {k:"v1",l:"Seed 1",num:1,sort:r=>r.v1,csv:r=>r.v1,cell:r=>r.v1==null?dash:`<span class="mono">${sig(r.v1)}</span>`},
  {k:"se",l:"SE",num:1,sort:r=>r.se1,csv:r=>r.se1,cell:r=>r.se1==null?dash:`<span class="mono t2">${sig(r.se1)}</span>`},
  {k:"v2",l:"Seed 2",num:1,sort:r=>r.v2,csv:r=>r.v2,cell:r=>r.v2==null?dash:`<span class="mono">${sig(r.v2)}</span>`},
  {k:"drift",l:"Drift",desc:1,sort:r=>r.drift==null?null:Math.abs(r.drift),csv:r=>r.drift,cell:driftCell},
  {k:"p",l:"p-value",num:1,sort:r=>r.p,csv:r=>r.p,cell:r=>r.p==null?dash:`<span class="mono ${r.p<0.05?"sig":"t2"}">${r.p<0.001?"<0.001":sig(r.p)}</span>`},
  {k:"test",l:"Test",sort:r=>r.test,csv:r=>r.test,cell:r=>r.test?`<span class="t2">${esc(r.test)}</span>`:dash},
  {k:"checks",l:"Checks",sort:r=>r.gates?Object.values(r.gates).filter(Boolean).length:null,csv:r=>r.gates?Object.entries(r.gates).map(([k,v])=>`${GATE_LABEL[k]||k}:${v?"pass":"fail"}`).join("; "):"",
    cell:r=>r.gates?gateDots({metrics:{gates:r.gates}}):dash},
  {k:"conf",l:"Confidence",num:1,sort:r=>r.conf,csv:r=>r.conf,cell:r=>r.conf==null?dash:`<span class="conf"><span class="bar"><span style="width:${Math.round(r.conf*100)}%"></span></span><span class="mono">${r.conf.toFixed(2)}</span></span>`},
  {k:"created",l:"Created",sort:r=>r.created,csv:r=>r.created,cell:r=>`<span class="t3">${ago(r.created)}</span>`}];
function driftCell(r){if(r.drift==null)return dash;const p=(Math.max(-3,Math.min(3,r.drift))+3)/6*100,ok=r.replicated!==false;
  return `<span class="drift" style="--c:${ok?"var(--green)":"var(--red)"}" title="Seed 2 minus seed 1 = ${sig(r.v2-r.v1)}; tolerance ±${sig(r.tol)} (${esc(r.tolKind)})"><span class="dtrack"><i class="dtol"></i><i class="dbar" style="left:${Math.min(50,p)}%;width:${Math.abs(p-50)}%"></i><i class="dmark" style="left:${p}%"></i></span><span class="mono">${fmtDrift(r.drift)}</span></span>`}
const defaultOrder=(a,b)=>(a.type===b.type?0:a.type==="finding"?-1:1)||(STATUS_RANK[a.status]??9)-(STATUS_RANK[b.status]??9)||(b.conf??-1)-(a.conf??-1);
function filteredRows(all){
  const R=S.res,f=(RES_FILTERS.find(x=>x[0]===R.filter)||RES_FILTERS[0])[2],q=R.q.trim().toLowerCase();
  let rows=all.filter(f).filter(r=>!q||`${r.title} ${r.pk||""} ${r.status} ${TYPE[r.type]?.l||""} ${r.test||""}`.toLowerCase().includes(q));
  const c=R.sort&&RES_COLS.find(x=>x.k===R.sort.k);
  if(c){const d=R.sort.dir;rows=[...rows].sort((a,b)=>{const x=c.sort(a),y=c.sort(b);if(x==null||y==null)return x==null&&y==null?0:x==null?1:-1;return (x<y?-1:x>y?1:0)*d||defaultOrder(a,b)})}
  else rows=[...rows].sort(defaultOrder);
  return rows}
function tilesHtml(all){return RES_FILTERS.map(([k,l,f,col])=>{const n=all.filter(f).length;
  return `<button type="button" class="tile" data-filter="${k}" aria-pressed="${S.res.filter===k}" style="--c:${col}"><span class="k"><i style="background:${col}"></i>${l}</span><b data-mk="tile:${k}" data-num data-v="${n}">${n}</b><span class="tbar"><i style="width:${all.length?100*n/all.length:0}%"></i></span></button>`}).join("")}
function gridHtml(all){
  const R=S.res,rows=filteredRows(all),n=rows.length,pages=Math.max(1,Math.ceil(n/R.size));R.page=Math.max(0,Math.min(R.page,pages-1));
  const from=R.page*R.size,page=rows.slice(from,from+R.size),cols=RES_COLS.filter(c=>c.pin||!R.hidden.has(c.k));
  const sortIco=k=>{const s=R.sort?.k===k?R.sort.dir:0;return `<span class="sarr${s?" on":""}" aria-hidden="true">${s===-1?"↓":"↑"}</span>`};
  const head=`<tr>${cols.map(c=>`<th scope="col" class="${c.num?"num ":""}${c.pin?"pin"+c.pin:""}" aria-sort="${R.sort?.k===c.k?(R.sort.dir===1?"ascending":"descending"):"none"}"><button type="button" data-sort="${c.k}">${c.pin===1?`<span class="sr">${c.l}</span>`:c.l}${sortIco(c.k)}</button></th>`).join("")}</tr>`;
  const body=page.length?page.map(r=>`<tr data-node="${esc(r.id)}" class="${S.selected===r.id?"on":""}">${cols.map(c=>`<td class="${c.num?"num ":""}${c.pin?"pin"+c.pin:""}">${c.cell(r)}</td>`).join("")}</tr>`).join("")
    :`<tr><td colspan="${cols.length}" class="gempty">No results match these filters. <button type="button" class="btn ghost sm" data-clear>Clear filters</button></td></tr>`;
  return `<div class="gwrap" id="gwrap" tabindex="0" aria-label="Results table"><table class="dg${R.dense?" dense":""}"><caption class="sr">Claims and findings with their metrics, replication and checks</caption><thead>${head}</thead><tbody>${body}</tbody></table></div>
  <div class="gfoot"><span data-mk="grange">${n?`${from+1}–${Math.min(n,from+R.size)} of ${n}`:"No results"}</span>
    <label class="gsize">Rows <select id="gsize" aria-label="Rows per page">${[10,25,50].map(s=>`<option${s===R.size?" selected":""}>${s}</option>`).join("")}</select></label>
    <span class="pg"><button type="button" class="icon-btn" data-page="-1" aria-label="Previous page"${R.page<=0?" disabled":""}>${ico('<path d="M10 3 5 8l5 5"/>')}</button><span>Page ${R.page+1} of ${pages}</span><button type="button" class="icon-btn" data-page="1" aria-label="Next page"${R.page>=pages-1?" disabled":""}>${ico('<path d="m6 3 5 5-5 5"/>')}</button></span></div>`}
function resultsView(){
  const all=resultRows();
  if(!all.length)return emptyPane("No results yet","Claims and findings land here with their metrics, replication and checks as experiments finish.");
  const R=S.res,judged=judgedFacts(),allPass=judged.filter(passedAll).length;
  return `<div class="res"><div data-seq>
  <div class="tiles" role="group" aria-label="Filter results">${tilesHtml(all)}</div>
  <section class="card"><div class="card-h"><b>Verification</b><span class="t3">Share of judged claims passing each check, as claims were judged${judged.length?` · <span data-mk="allpass">${allPass} of ${judged.length}</span> passed all four`:""}</span></div>
    ${judged.length?chartSlot("gates",240,`Verification: ${allPass} of ${judged.length} judged claims passed all four checks. `+Object.keys(GATE_LABEL).map(k=>`${GATE_LABEL[k]} ${pct(judged.filter(f=>obj(f.metrics).gates[k]).length/judged.length)}`).join(", ")):`<p class="t3" style="margin:0">No claim has been judged yet. Each claim gets replication, statistics, figure and skeptic checks when its experiment finishes.</p>`}</section>
  <section class="card"><div class="gbar">
    <label class="gsearch">${ico('<circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/>',13)}<input id="gq" type="search" placeholder="Filter by title, metric or status" value="${esc(R.q)}" aria-label="Filter results" autocomplete="off"><span class="kbd">/</span></label>
    <span class="menu-w"><button class="btn" type="button" id="colBtn" aria-haspopup="true" aria-expanded="false" aria-controls="colMenu">${ico('<rect x="2.5" y="3" width="11" height="10" rx="1.5"/><path d="M6.5 3v10M10 3v10"/>')}Columns</button>
      <div class="menu" id="colMenu" hidden>${RES_COLS.filter(c=>!c.pin).map(c=>`<label><input type="checkbox" data-col="${c.k}"${R.hidden.has(c.k)?"":" checked"}>${c.l}</label>`).join("")}</div></span>
    <div class="seg" role="group" aria-label="Row density"><button type="button" data-dense="0" class="${R.dense?"":"on"}" aria-pressed="${!R.dense}">Comfortable</button><button type="button" data-dense="1" class="${R.dense?"on":""}" aria-pressed="${R.dense}">Compact</button></div>
    <button class="btn" type="button" data-csv="grid" style="margin-left:auto">${ico('<path d="M8 2.5v8M4.5 7 8 10.5 11.5 7M3 13.5h10"/>')}<span data-lbl>Export CSV</span></button></div>
  <div id="grid">${gridHtml(all)}</div></section>
  </div></div>`}
function renderGrid(){const g=$("#grid");if(!g)return;const w=$("#gwrap"),sx=w?.scrollLeft||0;g.innerHTML=gridHtml(resultRows());$("#gwrap").scrollLeft=sx;Kit.hydrate(g,S.route.id+":");KB=-1;
  document.querySelectorAll("#pane .tile").forEach(t=>t.setAttribute("aria-pressed",String(t.dataset.filter===S.res.filter)))}
function exportCsv(btn){const all=resultRows(),cols=RES_COLS.filter(c=>c.pin||!S.res.hidden.has(c.k));
  Kit.download(`${cid(S.route.id).toLowerCase()}-results.csv`,Kit.csv([["id",...cols.map(c=>c.l)],...filteredRows(all).map(r=>[r.id,...cols.map(c=>c.csv(r))])]),"text/csv");Kit.flash(btn,"Exported")}

/* ---------- live charts (Liveline) ----------
   Liveline's right edge is the wall clock. A running campaign plots at real time; a finished
   one is shifted so its last event sits at the edge, and formatTime shifts the labels back. */
const tsec=t=>new Date(t).getTime()/1000;
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const chartSlot=(key,h,label)=>`<div class="ll" data-ll="${key}" data-sk-box role="img" aria-label="${esc(label)}" style="height:${h}px"></div>`;
const passedAll=f=>Object.values(obj(obj(f.metrics).gates)).every(Boolean);
const judgedAt=n=>tsec(n.updated_at||n.created_at);
const judgedFacts=()=>S.graph.nodes.filter(n=>n.node_type==="fact"&&Object.keys(obj(obj(n.metrics).gates)).length).sort((a,b)=>judgedAt(a)-judgedAt(b));
function frame(c){const start=tsec(c.created_at);
  if(ACTIVE(c)){const now=Date.now()/1000;return{start,end:now,shift:0,window:Math.max(120,(now-start)*1.04)}}
  const ts=S.graph.nodes.map(n=>tsec(n.updated_at||n.created_at)).concat((S.usage||[]).map(p=>p.t)).filter(Number.isFinite);
  const end=Math.max(start+60,...ts);S.t0||=Date.now()/1000;   // anchored once, so re-renders don't nudge the line
  return{start,end,shift:S.t0-end,window:(end-start)*1.05}}
const clockFmt=f=>t=>new Date((t-f.shift)*1000).toLocaleString([],f.end-f.start>86400?{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}:{hour:"2-digit",minute:"2-digit"});
/* A step line through [time, value] events (sorted): flat until each event, then a short ramp. */
function steps(ev,f,v0){const r=f.window/600,pts=v0==null?[]:[{time:f.start+f.shift,value:v0}];
  for(const [t,v] of ev){const x=Math.min(f.end,Math.max(t,f.start))+f.shift,last=pts[pts.length-1];
    if(last&&x<=last.time){last.value=v;continue}
    if(last&&x-r>last.time)pts.push({time:x-r,value:last.value});
    pts.push({time:x,value:v})}
  const last=pts[pts.length-1],end=f.end+f.shift;if(last&&end>last.time)pts.push({time:end,value:last.value});
  return{data:pts,value:last?last.value:v0??0}}
const cumulative=ts=>ts.filter(Number.isFinite).sort((a,b)=>a-b).map((t,i)=>[t,i+1]);
const theme=()=>document.documentElement.dataset.theme==="dark"?"dark":"light";
function mountCharts(){const pane=$("#pane"),c=S.summary?.campaign;
  if(pane&&c){const f=frame(c),live=ACTIVE(c),slot=k=>pane.querySelector(`[data-ll="${k}"]`);
    const base={theme:theme(),window:f.window,grid:true,scrub:true,lineWidth:1.75,formatTime:clockFmt(f),pulse:live,windowStyle:"rounded",seriesToggleCompact:pane.clientWidth<480};
    const series=(id,label,color,s)=>({id,label,color:cssv(color),...s});
    if(slot("progress")){const nodes=S.graph.nodes,at=(type,st)=>nodes.filter(n=>n.node_type===type&&st.includes(n.status)).map(n=>tsec(n.updated_at||n.created_at));
      Kit.chart(slot("progress"),"progress",{...base,data:[],value:0,formatValue:v=>String(Math.round(v)),series:[
        series("exp","Experiments","--accent",steps(cumulative(at("intent",["verified","refuted","exhausted"])),f,0)),
        series("ver","Supported","--green",steps(cumulative(at("fact",["verified"])),f,0)),
        series("ref","Refuted","--red",steps(cumulative(at("fact",["refuted"])),f,0)),
        series("fnd","Findings","--purple",steps(cumulative(at("finding",["verified"])),f,0))]})}
    if(slot("burn")){const pts=(S.usage||[]).filter(p=>Number.isFinite(p.t)),budget=c.token_budget_max;
      const data=pts.length?[{time:Math.min(f.start,pts[0].t)+f.shift,value:0},...pts.map(p=>({time:p.t+f.shift,value:p.tokens}))]:[];
      const value=data.length?data[data.length-1].value:0;
      Kit.chart(slot("burn"),"burn",{...base,data,value,color:cssv("--accent"),loading:S.usage===undefined,emptyText:"No call-by-call history for this campaign",
        momentum:live,badgeVariant:"minimal",fill:true,formatValue:short,referenceLine:value>=0.35*budget?{value:budget,label:"Budget"}:undefined})}
    if(slot("gates")){const judged=judgedFacts(),rate=test=>{let pass=0;return steps(judged.map((j,i)=>[judgedAt(j),100*(pass+=test(j)?1:0)/(i+1)]),f)};
      Kit.chart(slot("gates"),"gates",{...base,data:[],value:0,formatValue:v=>Math.round(v)+"%",series:[
        ...Object.keys(GATE_LABEL).map(k=>series(k,GATE_LABEL[k],GATE_COLOR[k],rate(j=>!!obj(j.metrics).gates[k]))),
        series("all","All four","--text-2",rate(passedAll))]})}}
  Kit.sweepCharts()}
/* Token burn comes from the usage ledger; refetched only when the campaign's totals move. */
async function loadUsage(){const c=S.summary?.campaign;if(!c)return;const id=c.id,key=`${id}:${c.tokens_used}:${c.gpu_seconds_used}`;
  if(S.usageKey===key)return;S.usageKey=key;
  try{const r=await getJSON(`campaigns/${id}/usage`);if(S.summary?.campaign?.id!==id||S.usageKey!==key)return;S.usage=Array.isArray(r.points)?r.points:[]}
  catch(e){if(S.summary?.campaign?.id!==id||S.usageKey!==key)return;S.usage=[];S.usageKey=null}
  mountCharts()}

/* ---------- lists ---------- */
function nodeRow(n,extra=""){return `<div class="row${S.selected===n.id?" on":""}" data-node="${esc(n.id)}">${nodeIcon(n.status)}<span class="title trunc">${esc(n.title)}</span><span class="meta">${extra}<span class="hide-sm">${ago(n.created_at)}</span></span></div>`}
function grouped(list,order,label){const g={};list.forEach(n=>(g[n.status]??=[]).push(n));
  return order.filter(s=>g[s]?.length).map(s=>`<div class="group">${nodeIcon(s)}${label(s)}<span class="n">${g[s].length}</span></div>`+g[s].map(n=>nodeRow(n,gateDots(n)+(n.confidence_score!=null?`<span class="chip">conf ${Number(n.confidence_score).toFixed(2)}</span>`:""))).join("")).join("")}
function findingsView(){const nodes=S.graph.nodes,f=nodes.filter(n=>n.node_type==="finding"),facts=nodes.filter(n=>n.node_type==="fact");
  if(!f.length&&!facts.length)return emptyPane("No findings or claims yet","Claims appear as the swarm turns literature and experiments into testable statements.");
  return (f.length?grouped(f,["verified","open","running","claimed","refuted","exhausted"],s=>s==="verified"?"Verified findings":"Findings · "+STATUS_LABEL[s]):"")+
    grouped(facts,["verified","refuted","open","running","claimed","exhausted"],s=>"Claims · "+STATUS_LABEL[s])}
function experimentsView(){const xs=S.graph.nodes.filter(n=>n.node_type==="intent");
  if(!xs.length)return emptyPane("No experiments yet","The planner proposes experiments after the literature scout finishes.");
  return grouped(xs,["running","claimed","open","verified","refuted","exhausted"],s=>({verified:"Succeeded",refuted:"Failed",exhausted:"Out of attempts"}[s]||STATUS_LABEL[s]))}
function guardView(){const ev=S.summary.guard_events;if(!ev.length)return emptyPane("No guardrail events","Sandbox, budget and data-scope checks log here when they fire.");
  return `<div class="group">Latest ${ev.length} events</div>`+ev.map(e=>`<div class="row" data-gev>${e.decision==="deny"?cross("var(--red)"):e.decision==="allow"?check("var(--green)"):minus("var(--yellow)")}
    <span class="chip">${esc(e.kind)}</span><span class="title trunc">${esc(guardSummary(e))}</span><span class="meta">${ago(e.created_at)}</span></div>
    <div hidden style="padding:10px 20px;border-bottom:1px solid var(--border)"><pre class="src">${esc(JSON.stringify(e.detail,null,2))}</pre></div>`).join("")}
function guardSummary(e){const d=e.detail||{};if(d.error||d.reason||d.message)return (d.node?d.node+": ":"")+(d.error||d.reason||d.message);
  return Object.entries(d).slice(0,4).map(([k,v])=>`${k}: ${typeof v==="object"?JSON.stringify(v):v}`).join(" · ")||"(no detail)"}
const emptyPane=(h,p)=>`<div class="empty"><div>${ring("var(--text-3)",0,true)}<h3>${esc(h)}</h3><p>${esc(p)}</p></div></div>`;

/* graph: columns by depth, edges as curves */
function graphView(){
  const nodes=S.graph.nodes,edges=S.graph.edges;if(!nodes.length)return emptyPane("Graph is empty","Nodes appear as soon as the campaign starts.");
  const byId=Object.fromEntries(nodes.map(n=>[n.id,n])),inc={};edges.forEach(e=>{if(byId[e.source_node_id]&&byId[e.target_node_id])(inc[e.target_node_id]??=[]).push(e.source_node_id)});
  const depth={},seen=new Set();const d=id=>{if(depth[id]!=null)return depth[id];if(seen.has(id))return 0;seen.add(id);const p=inc[id]||[];depth[id]=p.length?1+Math.max(...p.map(d)):0;return depth[id]};
  nodes.forEach(n=>d(n.id));
  const order={goal:0,hint:1,intent:2,fact:3,finding:4},cols={};
  nodes.forEach(n=>(cols[depth[n.id]]??=[]).push(n));
  const keys=Object.keys(cols).map(Number).sort((a,b)=>a-b),CW=264,RH=40,TOP=44,LEFT=20,pos={};
  keys.forEach((k,i)=>{cols[k].sort((a,b)=>(order[a.node_type]-order[b.node_type])||String(a.created_at).localeCompare(String(b.created_at)));cols[k].forEach((n,j)=>pos[n.id]=[LEFT+i*CW,TOP+j*RH])});
  const W=LEFT*2+keys.length*CW,H=TOP+Math.max(...keys.map(k=>cols[k].length))*RH+20;
  const ecol={refutes:"var(--red)",proves:"var(--green)"};
  const paths=edges.map(e=>{const a=pos[e.source_node_id],b=pos[e.target_node_id];if(!a||!b)return"";const x1=a[0]+216,y1=a[1]+15,x2=b[0],y2=b[1]+15,mx=(x1+x2)/2;
    return `<path d="M${x1} ${y1}C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}" fill="none" stroke="${ecol[e.edge_type]||"var(--border-2)"}" stroke-width="1.2"${e.edge_type==="derived_from"?' stroke-dasharray="3 3"':""}/>`}).join("");
  const colName=k=>{const ts=new Set(cols[k].map(n=>n.node_type));return [...ts].map(t=>TYPE[t]?.l||t).join(" · ")};
  return `<div class="gtools"><div class="legend">${Object.entries(TYPE).map(([k,v])=>`<span><i class="dot" style="background:${v.c}"></i>${v.l}</span>`).join("")}
    <span><svg width="18" height="6" aria-hidden="true"><path d="M0 3h18" stroke="var(--green)" stroke-width="1.5"/></svg>proves</span><span><svg width="18" height="6" aria-hidden="true"><path d="M0 3h18" stroke="var(--red)" stroke-width="1.5"/></svg>refutes</span></div>
    <span class="t3" style="margin-left:auto;font-size:12px">${nodes.length} nodes · ${edges.length} edges</span></div>
  <div class="gcanvas" style="width:${W}px;height:${H}px"><svg class="edges" width="${W}" height="${H}" aria-hidden="true">${paths}</svg>
  ${keys.map((k,i)=>`<div class="gcol" style="left:${LEFT+i*CW+2}px">${esc(colName(k))}</div>`).join("")}
  ${nodes.map(n=>{const [x,y]=pos[n.id];return `<div class="gn${S.selected===n.id?" on":""}${["refuted","exhausted"].includes(n.status)?" dim":""}" data-node="${esc(n.id)}" style="left:${x}px;top:${y}px" title="${esc((TYPE[n.node_type]?.l||n.node_type)+" · "+n.status+"\n"+n.title)}">
    <i class="dot" style="background:${TYPE[n.node_type]?.c};flex:none"></i>${nodeIcon(n.status)}<span class="trunc">${esc(n.title)}</span></div>`}).join("")}</div>`}

/* ---------- manuscript ---------- */
function ensureManuscript(){if(S.manuscript!==undefined||!S.summary)return;if(!msExists(S.summary.campaign)){S.manuscript=false;return}loadManuscript()}
async function loadManuscript(){const id=S.route.id;S.manuscript=null;let m;
  try{m=await getJSON(`campaigns/${id}/manuscript`)}catch(e){m=e.status===404?false:e.message}
  if(S.route.id!==id||!S.summary)return;S.manuscript=m;
  if(S.route.tab==="manuscript"){renderTab();Kit.reveal($("#pane"),"ms")}else refreshProps()}
/* Math: KaTeX is vendored (same origin, no CDN) and loaded only when a paper is shown. */
const KATEX="/vendor/katex-0.16.11/";let katexP=null;
function loadKatex(){if(window.katex)return Promise.resolve();if(katexP)return katexP;
  katexP=new Promise((res,rej)=>{const l=document.createElement("link");l.rel="stylesheet";l.href=KATEX+"katex.min.css";document.head.appendChild(l);
    const sc=document.createElement("script");sc.src=KATEX+"katex.min.js";sc.onload=res;sc.onerror=()=>{katexP=null;rej(new Error("KaTeX failed to load"))};document.head.appendChild(sc)});
  return katexP}
const MATH=new Map();
function renderMath(tex,display){
  // trust:false + strict:"ignore": KaTeX escapes all text and never emits links, styles or HTML from the source.
  if(window.katex){const k=(display?"D":"I")+tex;let h=MATH.get(k);
    if(h===undefined){try{h=katex.renderToString(tex,{displayMode:display,throwOnError:false,trust:false,strict:"ignore",output:"htmlAndMathml"})}catch{h=null}if(MATH.size>600)MATH.clear();MATH.set(k,h)}
    if(h)return h}
  return display?`<pre class="mono">${esc(tex)}</pre>`:`<code>${esc(tex)}</code>`}
function latexToHtml(src){
  // Math is lifted out of the raw source first (KaTeX renders it safely), then the rest is
  // escaped and a safe subset of LaTeX is rewritten into HTML (all text stays escaped).
  const math=[];const keep=(tex,display)=>{math.push([renderMath(tex.replace(/\\(label|nonumber|notag)(\{[^}]*\})?/g,"").trim(),display),display]);return `\u0000M${math.length-1}\u0000`};
  const ENV={equation:null,align:"aligned",gather:"gathered",multline:"gathered"};
  let raw=String(src).replace(/[\r\u0000-\u0002]/g,"").replace(/(^|[^\\])%.*$/gm,"$1")
    .replace(/\\begin\{(equation|align|gather|multline)(\*?)\}([\s\S]*?)\\end\{\1\2\}/g,(_,env,star,b)=>keep(ENV[env]?`\\begin{${ENV[env]}}${b}\\end{${ENV[env]}}`:b,true))
    .replace(/\$\$([\s\S]+?)\$\$/g,(_,b)=>keep(b,true)).replace(/\\\[([\s\S]+?)\\\]/g,(_,b)=>keep(b,true))
    .replace(/\\\(([\s\S]+?)\\\)/g,(_,b)=>keep(b,false)).replace(/(^|[^\\])\$((?:\\\$|[^$\n])+?)\$/g,(_,pre,b)=>pre+keep(b,false));
  let s=esc(raw);
  const doc=s.match(/\\begin\{document\}([\s\S]*?)(\\end\{document\}|$)/);
  const pre=doc?s.slice(0,doc.index):"";if(doc)s=doc[1];
  const title=(pre.match(/\\title\{([^}]*)\}/)||s.match(/\\title\{([^}]*)\}/)||[])[1],author=(pre.match(/\\author\{([^}]*)\}/)||s.match(/\\author\{([^}]*)\}/)||[])[1];
  s=s
   .replace(/\\(documentclass|usepackage)(\[[^\]]*\])?\{[^}]*\}/g,"").replace(/\\(title|author|date)\{[^}]*\}/g,"")
   .replace(/\\(label|vspace|hspace|bibliographystyle|bibliography)\*?\{[^}]*\}/g,"").replace(/\\(noindent|centering|maketitle|toprule|midrule|bottomrule|hline|small|footnotesize|newpage|clearpage)\b/g,"")
   .replace(/\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}/g,(_,a)=>`\n\n<div class="abs"><b>Abstract.</b> ${a.trim()}</div>\n\n`)
   .replace(/\\begin\{tabular\}\{[^}]*\}([\s\S]*?)\\end\{tabular\}/g,(_,body)=>{const rows=body.split(/\\\\/).map(r=>r.trim()).filter(Boolean);
      return "\n\n<table>"+rows.map(r=>"<tr>"+r.split(/(?<!\\)&amp;/).map(c=>`<td>${c.trim()}</td>`).join("")+"</tr>").join("")+"</table>\n\n"})
   .replace(/\\caption\{([^}]*)\}/g,"<figcaption>$1</figcaption>")
   .replace(/\\begin\{(table|figure)\}(\[[^\]]*\])?|\\end\{(table|figure)\}/g,"")
   .replace(/\\section\*?\{([^}]*)\}/g,"\n\n<h2>$1</h2>\n\n").replace(/\\subsection\*?\{([^}]*)\}/g,"\n\n<h3>$1</h3>\n\n").replace(/\\subsubsection\*?\{([^}]*)\}/g,"\n\n<h3>$1</h3>\n\n")
   .replace(/\\textbf\{([^}]*)\}/g,"<strong>$1</strong>").replace(/\\(emph|textit)\{([^}]*)\}/g,"<em>$2</em>").replace(/\\texttt\{([^}]*)\}/g,"<code>$1</code>")
   .replace(/\\cite[pt]?\{([^}]*)\}/g,(_,k)=>`<cite>[${k.split(",").map(x=>x.trim()).join(", ")}]</cite>`).replace(/\\(eq)?ref\{([^}]*)\}/g,"<code>$2</code>")
   .replace(/\\begin\{(itemize|enumerate)\}/g,"\n\n<ul>").replace(/\\end\{(itemize|enumerate)\}/g,"</ul>\n\n").replace(/\\item\s*/g,"<li>")
   .replace(/\\begin\{[^}]*\}(\{[^}]*\})?|\\end\{[^}]*\}/g,"").replace(/~/g,"&nbsp;").replace(/\\\\/g,"<br>")
   .replace(/\\&amp;/g,"&amp;").replace(/\\([%_#$])/g,"$1")
   // Text-mode leftovers the writer commonly emits.
   .replace(/\\par\b\s*/g,"\n\n").replace(/\\(med|big|small)skip\b\s*/g,"\n\n")
   .replace(/\\paragraph\*?\{([^}]*)\}\s*/g,"\n\n<strong>$1</strong> ")
   .replace(/\\href\{[^}]*\}\{([^}]*)\}/g,"$1").replace(/\\footnote\{([^}]*)\}/g," ($1)").replace(/\\url\{([^}]*)\}/g,"<code>$1</code>")
   .replace(/\\(ldots|dots)\b/g,"…").replace(/---/g,"—").replace(/--/g,"–").replace(/``/g,"“").replace(/&#39;&#39;/g,"”")
   .replace(/\\(textsc|underline|textrm|textsf|mbox|text)\{([^}]*)\}/g,"$2").replace(/\\[,;:! ]/g," ")
   // Anything still unrecognised: keep its braced argument, drop the command word.
   .replace(/\\[a-zA-Z]+\*?(\[[^\]]*\])?\{([^}]*)\}/g,"$2").replace(/\\[a-zA-Z]+\*?/g,"")
   // Bare braces only group in text mode ("10{,}000"); \{ and \} are the literal ones.
   .replace(/\\([{}])/g,(_,b)=>b==="{"?"\u0001":"\u0002").replace(/[{}]/g,"").replace(/\u0001/g,"{").replace(/\u0002/g,"}");
  const head=(title?`<h1>${plainTex(title)}</h1>`:"")+(author?`<p class="by">${plainTex(author)}</p>`:"");
  const html=head+s.split(/\n\s*\n/).map(b=>b.trim()).filter(Boolean).map(b=>/^<(h2|h3|ul|table|div|figcaption)/.test(b)||/^\u0000M\d+\u0000$/.test(b)?b:`<p>${b}</p>`).join("\n");
  // Inline math keeps touching punctuation on its line: "(SE 0.0047)" never wraps before ")".
  return html.replace(/([(\[“‘]*)\u0000M(\d+)\u0000([)\].,;:!?”’%]*)/g,(_,a,i,b)=>{const [h,d]=math[+i]||["",true];return d||!(a||b)?a+h+b:`<span class="nw">${a}${h}${b}</span>`})}
// Title/author text: escaped LaTeX reduced to its words.
const plainTex=t=>t.replace(/\\([&%_#$])/g,"$1").replace(/\\&amp;/g,"&amp;").replace(/\\[a-zA-Z]+\*?\{([^}]*)\}/g,"$1").replace(/\\[a-zA-Z]+\*?/g,"");
const pj=t=>{try{return t?JSON.parse(t):null}catch{return null}};
const sevColor=v=>v==null?"var(--gray)":v>=4?"var(--red)":v>=3?"var(--orange)":v>=2?"var(--yellow)":"var(--green)";
// Reviewer panel, claim support and citation checks: the receipts of the paper's audit.
function auditHtml(m){const panel=pj(m.review_panel),mx=pj(m.evidence_matrix),cr=pj(m.citation_report);if(!panel&&!mx&&!cr)return"";
  const parts=[];
  if(panel){const rows=Object.entries(panel.reviewers||{});
    parts.push(`<div class="audit-row"><b>Reviewer panel</b><span class="audit-chips">${rows.map(([a,r])=>`<span class="chip" title="${esc(r.error?"Review unavailable":r.summary||"")}"><i style="background:${sevColor(r.error?null:r.severity)}"></i>${esc(a[0].toUpperCase()+a.slice(1))} ${r.error?"n/a":`${Number(r.severity)}/5`}</span>`).join("")}</span></div>`
      +`<details class="t2"><summary>Reviewer comments</summary>${rows.filter(([,r])=>!r.error).map(([a,r])=>`<p><b style="font-weight:500">${esc(a[0].toUpperCase()+a.slice(1))}</b>: ${esc(r.summary||"")}</p>${r.issues?.length?`<ul>${r.issues.map(i=>`<li>[${esc(i.section)}] ${esc(i.issue)} <span class="t3">Fix: ${esc(i.fix)}</span></li>`).join("")}</ul>`:""}`).join("")}</details>`)}
  if(mx){const cl=mx.claims||[],n=v=>cl.filter(c=>c.verdict===v).length;
    parts.push(`<div class="audit-row"><b>Claim support</b><span class="t2">${cl.length?`${n("supported")} of ${cl.length} cited claims supported by the cited abstract${n("refuted")?` · ${n("refuted")} contradicted`:""}`:"No cited claims"}</span></div>`
      +(cl.length?`<details class="t2"><summary>Claims and quotes</summary><ul>${cl.map(c=>`<li><span class="chip"><i style="background:${c.verdict==="supported"?"var(--green)":c.verdict==="refuted"?"var(--red)":"var(--orange)"}"></i>${esc(c.verdict)}</span> ${esc(c.text)}${c.citations.filter(x=>x.quote).map(x=>`<blockquote>“${esc(x.quote)}” <span class="t3">${esc(x.title)}</span></blockquote>`).join("")}</li>`).join("")}</ul></details>`:""))}
  if(cr){const cs=cr.cited||[],ok=cs.filter(c=>c.status==="verified").length,ex=cr.excluded||[];
    parts.push(`<div class="audit-row"><b>Citation checks</b><span class="t2">${ok} of ${cs.length} cited papers verified${ex.length?` · ${ex.length} retrieved paper${ex.length>1?"s":""} excluded`:""} · searched ${esc((cr.sources_searched||[]).join(", "))}</span></div>`
      +(ex.length||cs.length?`<details class="t2"><summary>Details</summary><ul>${cs.map(c=>`<li>${esc(c.key||"")} ${esc(c.title)}: ${esc(c.status)}${c.retracted?" (retracted)":""}${c.issues?.length?` <span class="t3">${esc(c.issues.join(", "))}</span>`:""}</li>`).join("")}${ex.map(x=>`<li>Excluded: ${esc(x.title)} <span class="t3">${esc(x.reason)}</span></li>`).join("")}</ul></details>`:""))}
  return `<div class="review audit">${parts.join("")}</div>`}
function reviewHtml(m){try{const r=m.peer_review?JSON.parse(m.peer_review):null;if(!r)return"";
  const pips=v=>{v=Number(v);v=Number.isFinite(v)?v:0;return `<span class="pips" title="${v} of 4">${[1,2,3,4].map(i=>`<i class="${i<=v?"on":""}"></i>`).join("")}</span>`};
  const dc={accept:"var(--green)",minor_revision:"var(--yellow)",major_revision:"var(--orange)",reject:"var(--red)"}[r.decision]||"var(--gray)";
  return `<div class="review"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><b style="font-weight:500">Automated peer review</b><span class="chip"><i style="background:${dc}"></i>${esc(String(r.decision).replace("_"," "))}</span></div>
    <div class="scores"><span class="score">Soundness ${pips(r.soundness)}</span><span class="score">Presentation ${pips(r.presentation)}</span><span class="score">Contribution ${pips(r.contribution)}</span></div>
    <div class="t2">${esc(r.summary)}</div>${r.required_changes?.length?`<ul class="t2" style="margin:8px 0 0;padding-left:18px">${r.required_changes.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:""}</div>`}catch{return""}}
function manuscriptView(){
  // undefined: not requested yet, null: loading, false: none yet, string: load error, object: loaded
  const c=S.summary.campaign;
  if(S.manuscript==null)return `<div class="paper">${Kit.skel(paperSample(),"ms")}</div>`;
  if(typeof S.manuscript==="string")return emptyPane("Could not load the manuscript",S.manuscript);
  if(S.manuscript===false){if(c.status==="writing"||S.draft?.stage)return `<div id="msSlot"></div>`;
    return emptyPane("No manuscript yet",c.status==="halted"?"This campaign halted before writing.":"The paper is written after the experiments and the sealed evaluation finish. It streams in live once writing starts.")}
  const m=S.manuscript;if(!window.katex)loadKatex().then(()=>{if(S.route.tab==="manuscript")renderTab()}).catch(()=>{});
  const dl=ico('<path d="M8 2.5v8M4.5 7 8 10.5 11.5 7M3 13.5h10"/>'),cp=ico('<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/>');
  return `<div class="paper"><div class="ms-bar"><div class="seg" role="tablist" aria-label="Manuscript view"><button type="button" role="tab" data-ms="paper" aria-selected="${S.msView==="paper"}" class="${S.msView==="paper"?"on":""}">Paper</button><button type="button" role="tab" data-ms="src" aria-selected="${S.msView==="src"}" class="${S.msView==="src"?"on":""}">LaTeX</button><button type="button" role="tab" data-ms="bib" aria-selected="${S.msView==="bib"}" class="${S.msView==="bib"?"on":""}">BibTeX</button></div>
    <span style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap"><button class="btn" type="button" data-copy="${S.msView==="bib"?"bib":"tex"}">${cp}<span data-lbl>${S.msView==="bib"?"Copy BibTeX":"Copy LaTeX"}</span></button><button class="btn" type="button" data-dl="tex">${dl}.tex</button>${m.bibtex?`<button class="btn" type="button" data-dl="bib">${dl}.bib</button>`:""}</span></div>
    ${reviewHtml(m)}${auditHtml(m)}${S.msView==="paper"?latexToHtml(m.latex_section||""):`<pre class="src">${esc(S.msView==="bib"?m.bibtex||"":m.latex_section||"")}</pre>`}</div>`}
function download(kind){const m=S.manuscript;if(!m)return;Kit.download(`${cid(S.route.id).toLowerCase()}.${kind}`,(kind==="bib"?m.bibtex:m.latex_section)||"")}
async function copyPaper(btn){const m=S.manuscript,kind=btn.dataset.copy;
  const text=kind==="bib"?m?.bibtex:kind==="draft"?draftLatex():m?.latex_section;
  if(!text){toast("Nothing to copy yet",true);return}
  if(await Kit.copyText(text))Kit.flash(btn,"Copied");else toast("Copy failed: the browser blocked clipboard access",true)}

/* ---------- live paper: the draft streamed from the writer, section by section ---------- */
const MS_FIELDS=[["title","Title"],["abstract","Abstract"],["introduction","Introduction"],["methods","Methods"],["results","Results"],["discussion","Discussion"],["limitations","Limitations"]];
const STAGES=[["drafting","Draft"],["reviewing","Review"],["revising","Revision"],["final","Final"]];
const STAGE_LABEL={drafting:"Drafting",reviewing:"Under peer review",revising:"Revising",final:"Final draft"};
/* The writer streams JSON ({"title": "...", "abstract": "...", ...}). Read the string fields
   it has produced so far, tolerating a body cut mid-string or mid-escape. */
function partialJSON(s){const fields={};let open=null,i=s.indexOf("{")+1;if(!i)return {fields,open};
  const ws=()=>{while(i<s.length&&/[\s,]/.test(s[i]))i++};
  const str=()=>{let v="";i++;while(i<s.length){const ch=s[i];if(ch==='"'){i++;return {v,done:true}}
      if(ch==="\\"){if(i+1>=s.length)break;const e=s[i+1];if(e==="u"){const h=s.slice(i+2,i+6);if(h.length<4)break;if(/^[0-9a-fA-F]{4}$/.test(h))v+=String.fromCharCode(parseInt(h,16));i+=6;continue}
        v+={n:"\n",t:"\t",r:"\r",b:"\b",f:"\f"}[e]??e;i+=2;continue}
      v+=ch;i++}
    return {v,done:false}};
  while(i<s.length){ws();if(s[i]!=='"')break;const k=str();if(!k.done)break;ws();if(s[i]!==":")break;i++;while(i<s.length&&/\s/.test(s[i]))i++;
    if(s[i]!=='"'){let d=0;while(i<s.length){const ch=s[i];if(ch==='"'){str();continue}if("[{".includes(ch))d++;else if("]}".includes(ch)){if(!d)break;d--}else if(ch===","&&!d)break;i++}continue}
    const v=str();fields[k.v]=v.v;if(!v.done){open=k.v;break}}
  return {fields,open}}
/* Cut a streaming LaTeX fragment before any construct that is still open, so the typing
   view never flashes raw math or half a command. */
function stableCut(t){let cut=t.length;
  const tail=t.match(/\\[a-zA-Z]*\*?(\[[^\]]*)?(\{[^}]*)?$/);if(tail)cut=Math.min(cut,tail.index);
  const env=[...t.matchAll(/\\begin\{(equation|align|gather|multline)\*?\}/g)].pop();if(env&&!t.slice(env.index).includes("\\end{"+env[1]))cut=Math.min(cut,env.index);
  for(const [o,c] of [["\\[","\\]"],["\\(","\\)"]]){const k=t.lastIndexOf(o);if(k>=0&&t.indexOf(c,k)<0)cut=Math.min(cut,k)}
  const dollars=[...t.slice(0,cut).matchAll(/(^|[^\\])\$/g)];if(dollars.length%2)cut=Math.min(cut,dollars[dollars.length-1].index+dollars[dollars.length-1][1].length);
  return t.slice(0,cut)}
const CARET='<span class="caret" aria-hidden="true"></span>';
function sectionHtml(f,label,text,active){
  const caret=active?CARET:"",t=active?stableCut(text):text;
  if(f==="title")return `<h1>${plainTex(esc(t))||(active?"":"Untitled")}${caret}</h1>`;
  let body=latexToHtml(t);if(caret)body=body.endsWith("</p>")?body.slice(0,-4)+caret+"</p>":body+`<p>${caret}</p>`;
  if(f==="abstract")return `<div class="abs">${body.startsWith("<p>")?"<p><b>Abstract.</b> "+body.slice(3):"<b>Abstract.</b> "+body}</div>`;
  return `<h2>${esc(label)}</h2>${body}`}
function pendingHtml(f,label){
  if(f==="title")return Kit.skel(`<h1>Coverage of the slope interval under heteroskedastic errors</h1>`);
  if(f==="abstract")return Kit.skel(`<div class="abs"><p><b>Abstract.</b> ${LINE.repeat(4)}</p></div>`);
  return `<h2 class="ghost">${esc(label)}</h2>${Kit.skel(`<p>${LINE.repeat(f==="limitations"?2:4)}</p>`)}`}
function draftLatex(){const f=S.draft?.parsed?.fields||{};return MS_FIELDS.filter(([k])=>f[k]).map(([k,l])=>k==="title"?`\\title{${f[k]}}`:k==="abstract"?`\\begin{abstract}\n${f[k]}\n\\end{abstract}`:`\\section{${l}}\n${f[k]}`).join("\n\n")}
function paperMode(){const c=S.summary.campaign,final=S.manuscript&&typeof S.manuscript==="object";
  if(final&&(!ACTIVE(c)||!S.draft?.stage||S.draft.stage==="final"))return "final";
  if(S.draft?.stage)return "live";
  if(S.manuscript===null||S.draft===undefined&&c.status==="writing")return "loading";return "empty"}
function mountPaper(){const slot=$("#paperSlot")||$("#msSlot");if(!slot)return;
  if(!S.paperEl){const el=S.paperEl=document.createElement("div");el.className="lp";
    const stop=()=>{if(S.follow&&S.draft&&["drafting","revising"].includes(S.draft.stage))follow(false)};
    el.addEventListener("wheel",stop,{passive:true});el.addEventListener("touchmove",stop,{passive:true})}
  S.paperEl.classList.toggle("in-tab",slot.id==="msSlot");slot.replaceWith(S.paperEl);
  if(!window.katex)loadKatex().then(()=>{S.lp=null;if(S.paperEl)S.paperEl.dataset.mode="";renderPaper()}).catch(()=>{});
  renderPaper();if(!S.draftBusy&&!S.draftTimer&&(S.summary.campaign.status==="writing"||S.draft===undefined))pollDraft()}
function renderPaper(){const el=S.paperEl;if(!el||!el.isConnected||!S.summary)return;
  const mode=paperMode(),was=el.dataset.mode;
  if(was!==mode){el.dataset.mode=mode;S.lp=null;el.innerHTML=paperShell(mode);Kit.paint(el);
    if(was==="live"&&mode==="final"&&!Kit.still())el.animate([{opacity:.35},{opacity:1}],{duration:320,easing:"ease-out"}).finished.catch(()=>{})}
  if(mode==="live")updateLive()}
function paperShell(mode){const c=S.summary.campaign;
  if(mode==="final"){const m=S.manuscript,words=(m.latex_section||"").replace(/\\[a-zA-Z]+|[{}$\\]/g," ").split(/\s+/).filter(Boolean).length;
    return `<div class="lp-head">${check("var(--green)")}<b data-stage>Final</b><span class="t3">·</span><span>${fmt(words)} words</span>
      <span class="lp-act"><button class="btn ghost sm" type="button" data-copy="tex"><span data-lbl>Copy LaTeX</span></button><button class="btn ghost sm" type="button" data-open-ms>Open in Manuscript</button></span></div>
      <div class="paper">${reviewHtml(m)}${latexToHtml(m.latex_section||"")}</div>`}
  if(mode==="loading")return `<div class="paper">${Kit.skel(paperSample())}</div>`;
  if(mode==="empty"){const before=ACTIVE(c)&&c.status!=="writing";
    return `<div class="lp-empty">${before?`<b>The paper streams in here once writing starts.</b><p class="t2">Writing begins after the experiments and the sealed evaluation. You will see each section appear as the writer produces it, then the peer review and the revision.</p>`
      :`<b>No paper for this campaign.</b><p class="t2">${c.status==="halted"?"It halted before the writer produced a draft.":"The writer has not saved a draft yet."}</p>`}
      <div class="ghost-paper" aria-hidden="true">${MS_FIELDS.slice(1).map(([,l])=>`<div class="gh">${esc(l)}</div><i></i><i></i><i style="width:62%"></i>`).join("")}</div></div>`}
  return `<div class="lp-head"><span class="live" style="--c:var(--blue)"></span><b data-stage>Drafting</b><span class="t3">·</span><span><span data-words data-num>0</span> words</span>
    <button class="btn ghost sm" type="button" data-follow hidden>${ico('<path d="M8 3v10M4 9l4 4 4-4"/>')}Follow live</button>
    <span class="lp-steps" aria-label="Writing stages">${STAGES.map(([k,l])=>`<span data-st="${k}">${l}</span>`).join('<i aria-hidden="true">›</i>')}</span>
    <span class="lp-act"><button class="btn ghost sm" type="button" data-copy="draft" title="Copy the draft as LaTeX"><span data-lbl>Copy</span></button></span></div>
    <div class="paper lp-body">${MS_FIELDS.map(([f])=>`<section data-f="${f}"></section>`).join("")}</div>`}
function updateLive(){const el=S.paperEl,d=S.draft;if(!el||!d?.parsed)return;
  const first=!S.lp;S.lp??={f:{},stage:null};
  const st=el.querySelector("[data-stage]"),label=STAGE_LABEL[d.stage]||d.stage;
  if(S.lp.stage!==d.stage){if(first){st.textContent=label;st.dataset.mt=label}else Kit.morph(st,label);S.lp.stage=d.stage;
    const j=STAGES.findIndex(x=>x[0]===d.stage);el.querySelectorAll("[data-st]").forEach(s=>{const i=STAGES.findIndex(x=>x[0]===s.dataset.st);s.className=i<j?"done":i===j?"cur":""});
    const dot=el.querySelector(".lp-head .live");if(dot)dot.hidden=d.stage==="final"}
  const {fields,open}=d.parsed,streaming=d.stage==="drafting"||d.stage==="revising";
  for(const [f,label] of MS_FIELDS){const sec=el.querySelector(`section[data-f="${f}"]`),s=S.lp.f[f]??={state:null,text:"",shown:0,drawn:-1,rate:0};
    let text=fields[f],state;
    if(text==null){const fd=d.stage==="revising"?S.firstDraft?.[f]:null;state=fd!=null?"first":"pending";text=fd??""}
    else state=streaming&&open===f?"active":"done";
    if(state==="pending"){if(s.state!=="pending"){sec.innerHTML=pendingHtml(f,label);Kit.paint(sec)}}
    else if(state==="first"){if(s.state!=="first"||s.text!==text){sec.innerHTML=`<div class="fd">${sectionHtml(f,label,text,false)}</div>`;sec.querySelector("h2")?.insertAdjacentHTML("beforeend",'<span class="fd-tag">first draft</span>')}}
    else if(state==="done"){if(s.state!=="done"||s.text!==text){sec.innerHTML=sectionHtml(f,label,text,false);if(s.state==="pending"&&!first)fadeIn(sec)}s.shown=text.length}
    else{// active: reveal what arrived since the last poll as typing, over ~1.5 s
      if(s.state!=="active")s.shown=first||Kit.still()?text.length:s.state==="first"?0:Math.min(s.shown,text.length);
      if(Kit.still())s.shown=text.length;
      s.rate=Math.max(0.03,(text.length-s.shown)/1500);if(s.state==="pending"&&!first)fadeIn(sec)}
    s.state=state;s.text=text;if(state==="active")drawActive(f,label,s)}
  updateWords();el.querySelector("[data-follow]").hidden=S.follow||!streaming;
  if(Object.values(S.lp.f).some(s=>s.state==="active"&&s.shown<s.text.length))tickPaper()}
function fadeIn(sec){if(!Kit.still())sec.animate([{opacity:0,transform:"translateY(4px)"},{opacity:1,transform:"none"}],{duration:280,easing:"cubic-bezier(.22,1,.36,1)"}).finished.catch(()=>{})}
function drawActive(f,label,s){const sec=S.paperEl?.querySelector(`section[data-f="${f}"]`);if(!sec||s.drawn===s.shown)return;
  sec.innerHTML=sectionHtml(f,label,s.text.slice(0,s.shown),true);s.drawn=s.shown;
  if(S.follow){const now=performance.now();if(now-(S.lpScroll||0)>180){S.lpScroll=now;sec.querySelector(".caret")?.scrollIntoView({block:"nearest"})}}}
function updateWords(){const el=S.paperEl?.querySelector("[data-words]");if(!el||!S.lp)return;
  const n=Object.values(S.lp.f).reduce((a,s)=>a+(s.state==="pending"?0:s.text.slice(0,s.state==="active"?s.shown:undefined).split(/\s+/).filter(Boolean).length),0);
  const t=fmt(n);if(el.dataset.mt==null){el.textContent=t;el.dataset.mt=t}else Kit.morph(el,t,{num:true,dir:1})}
function tickPaper(){if(S.lpRaf)return;let last=0,words=0;
  const step=ts=>{S.lpRaf=0;if(!S.paperEl?.isConnected||!S.lp)return;let busy=false;
    const dt=last?Math.min(100,ts-last):16;last=ts;
    for(const [f,label] of MS_FIELDS){const s=S.lp.f[f];if(s?.state!=="active"||s.shown>=s.text.length)continue;
      s.shown=Math.min(s.text.length,s.shown+Math.max(1,Math.round(s.rate*dt)));drawActive(f,label,s);if(s.shown<s.text.length)busy=true}
    if(ts-words>400){words=ts;updateWords()}
    if(busy)S.lpRaf=requestAnimationFrame(step);else updateWords()};
  S.lpRaf=requestAnimationFrame(step)}
function follow(on){S.follow=on;const b=S.paperEl?.querySelector("[data-follow]");if(b)b.hidden=on;
  if(on)S.paperEl?.querySelector(".caret")?.scrollIntoView({block:"center",behavior:Kit.still()?"auto":"smooth"})}
function onDraft(d){
  if(!d||!d.stage){const was=S.draft;S.draft=null;if(was!==null)renderPaper();return}
  if(S.draft&&S.draft.updated_at===d.updated_at&&S.draft.stage===d.stage)return;
  const had=paperAvail(),parsed=partialJSON(d.body||"");
  if(d.stage==="reviewing")S.firstDraft=parsed.fields;
  S.draft={...d,parsed};
  if(S.route.tab==="manuscript"){if(S.paperEl?.isConnected)renderPaper();else renderTab()}
  else if(!had)refreshProps();else renderPaper()}
async function pollDraft(){clearTimeout(S.draftTimer);S.draftTimer=null;const c=S.summary?.campaign;if(!c||S.draftBusy)return;const id=c.id;
  if(S.paperEl?.isConnected&&!document.hidden||S.draft===undefined){S.draftBusy=true;
    try{const d=await getJSON(`campaigns/${id}/draft`);if(S.summary?.campaign?.id===id)onDraft(d)}catch{}finally{S.draftBusy=false}}
  if(S.summary?.campaign?.id===id&&S.summary.campaign.status==="writing")S.draftTimer=setTimeout(pollDraft,2000)}

/* ---------- evidence viewer ---------- */
let blobUrl=null;
async function openEvidence(id,type){
  const sample=type==="plot_png"?'<div data-sk-box style="width:100%;aspect-ratio:4/3;border-radius:6px"></div>':`<pre class="src">${Array.from({length:14},(_,i)=>"sample output line ".repeat(2+(i*5)%6)).join("\n")}</pre>`;
  overlay(`<div class="modal wide" role="dialog" aria-label="${esc(EV_LABEL[type]||type)}"><div class="m-h">${evIcon(type)}<span>${esc(EV_LABEL[type]||type)}</span><button class="icon-btn" type="button" style="margin-left:auto" data-x aria-label="Close">✕</button></div><div class="m-b" id="evb"></div></div>`);
  Kit.skeleton($("#evb"),sample,"evb");
  try{const r=await api("evidence/"+id);let html;
    if(type==="plot_png"){if(blobUrl)URL.revokeObjectURL(blobUrl);blobUrl=URL.createObjectURL(await r.blob());html=`<img alt="Experiment plot" style="max-width:100%;border-radius:6px;background:#fff;display:block" src="${blobUrl}">`}
    else{let t=await r.text();try{t=JSON.stringify(JSON.parse(t),null,2)}catch{}html=`<pre class="src">${esc(t)}</pre>`}
    if($("#evb"))Kit.swap($("#evb"),html,"evb")}
  catch(e){if($("#evb"))Kit.swap($("#evb"),`<p class="err">${esc(e.message)}</p>`,"evb")}}

/* ---------- overlays ---------- */
function overlay(html){$("#overlay").innerHTML=`<div class="scrim">${html}</div>`;const sc=$("#overlay .scrim");
  sc.addEventListener("mousedown",e=>{if(e.target===sc)closeOverlay()});sc.querySelectorAll("[data-x]").forEach(b=>b.onclick=closeOverlay)}
function closeOverlay(){$("#overlay").innerHTML=""}

/* ---------- new campaign ---------- */
function openNew(){
  overlay(`<form class="modal" id="newForm" role="dialog" aria-label="New campaign"><div class="m-h"><span class="chip">${ring("var(--text-3)",0,true)}Ideation</span><span>New campaign</span><button type="button" class="icon-btn" style="margin-left:auto" data-x aria-label="Close">✕</button></div>
  <div class="m-b"><textarea class="bare big" name="question" rows="2" required minlength="3" maxlength="4000" placeholder="Research question or idea" aria-label="Research question"></textarea>
  <textarea class="bare t2" name="context" rows="3" maxlength="2000" placeholder="Add context, constraints or what a good answer looks like… (optional)" aria-label="Context"></textarea>
  <div class="pchips">
    <label class="pchip" title="Token budget">Budget <select name="token_budget"><option value="200000">200k</option><option value="500000">500k</option><option value="1000000">1M</option><option value="2000000" selected>2M</option><option value="5000000">5M</option><option value="10000000">10M</option></select></label>
    <label class="pchip" title="Parallel experiment workers">Workers <input name="workers" type="number" min="1" max="16" value="4"></label>
    <label class="pchip" title="Investigation rounds">Rounds <input name="max_rounds" type="number" min="1" max="10" value="2"></label>
    <label class="pchip" title="Research domain">Domain <input class="dom" name="domain" value="general" maxlength="64"></label>
  </div>
  <div class="files"><label class="btn ghost" style="cursor:pointer">${evIcon("file")}<span id="trainLbl">Attach training data</span><input name="train" type="file" multiple hidden accept=".csv,.tsv,.json,.parquet,.txt"></label>
  <label class="btn ghost" style="cursor:pointer" title="Held out from all experiments; only used for the final sealed evaluation">${evIcon("file")}<span id="sealLbl">Attach sealed holdout</span><input name="sealed" type="file" multiple hidden accept=".csv,.tsv,.json,.parquet,.txt"></label></div>
  </div><div class="m-f"><span class="t3" id="nmsg" style="font-size:12px" aria-live="polite">Runs on Claude Haiku 5.5</span><span style="margin-left:auto" class="kbd">⌘ ↵</span><button class="btn primary" id="createBtn"><span data-lbl>Create campaign</span></button></div></form>`);
  const f=$("#newForm");f.question.focus();
  const lbl=(inp,el,def)=>inp.onchange=()=>{el.textContent=inp.files.length?[...inp.files].map(x=>x.name).join(", "):def};
  lbl(f.train,$("#trainLbl"),"Attach training data");lbl(f.sealed,$("#sealLbl"),"Attach sealed holdout");
  f.addEventListener("keydown",e=>{if((e.metaKey||e.ctrlKey)&&e.key==="Enter")f.requestSubmit()});
  f.onsubmit=async e=>{e.preventDefault();const b=$("#createBtn"),l=b.querySelector("[data-lbl]"),msg=$("#nmsg"),files=[...f.train.files,...f.sealed.files];b.disabled=true;
    Kit.morph(l,files.length?"Uploading…":"Creating…");Kit.morph(msg,files.length?`Uploading ${files.length} file${files.length>1?"s":""}`:"Starting the swarm");
    try{const datasets=[];for(const [k,sealed] of [["train",false],["sealed",true]])for(const file of f[k].files)
        datasets.push({file_name:file.name.replace(/[^A-Za-z0-9._-]/g,"_").replace(/^[^A-Za-z0-9]+/,"d").slice(0,128),content_base64:await b64(file),sealed});
      if(files.length){Kit.morph(l,"Creating…");Kit.morph(msg,"Starting the swarm")}
      const q=f.question.value.trim(),ctx=f.context.value.trim();
      const body={question:ctx?`${q}\n\nContext: ${ctx}`:q,domain:f.domain.value.trim()||"general",token_budget:+f.token_budget.value,workers:+f.workers.value,max_rounds:+f.max_rounds.value,datasets};
      const r=await (await api("campaigns",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)})).json();
      Kit.morph(l,"Created");b.classList.add("done");await new Promise(res=>setTimeout(res,Kit.still()?0:560));
      closeOverlay();toast("Campaign started");await loadList();go(r.id)}
    catch(err){b.disabled=false;Kit.morph(l,"Create campaign");msg.innerHTML=`<span class="err">${esc(err.message)}</span>`;delete msg.dataset.mt}}}
const b64=f=>f.arrayBuffer().then(b=>{let s="";const u=new Uint8Array(b);for(let i=0;i<u.length;i+=0x8000)s+=String.fromCharCode(...u.subarray(i,i+0x8000));return btoa(s)});
$("#newBtn").onclick=openNew;

/* ---------- pane events (delegated: views re-render with innerHTML) ---------- */
function bindPane(){const pane=$("#pane");if(!pane)return;
  pane.onclick=e=>{const t=e.target.closest("[data-node],[data-ms],[data-dl],[data-gev],[data-filter],[data-sort],[data-page],[data-dense],[data-csv],[data-copy],[data-clear],[data-pv],#colBtn");if(!t||!pane.contains(t))return;
    const d=t.dataset,R=S.res;
    if(t.id==="colBtn"){const m=$("#colMenu");m.hidden=!m.hidden;t.setAttribute("aria-expanded",String(!m.hidden));if(!m.hidden)m.querySelector("input")?.focus()}
    else if(d.filter){R.filter=R.filter===d.filter&&d.filter!=="all"?"all":d.filter;R.page=0;renderGrid()}
    else if(d.sort){const s=R.sort,c=RES_COLS.find(c=>c.k===d.sort),first=c?.num||c?.desc?-1:1;R.sort=!s||s.k!==d.sort?{k:d.sort,dir:first}:s.dir===first?{k:d.sort,dir:-first}:null;renderGrid()}
    else if(d.page){R.page+=+d.page;renderGrid()}
    else if(d.dense){R.dense=d.dense==="1";ls.set("plato_grid_dense",R.dense?"1":"0");savePref("compact_grid",R.dense);pane.querySelectorAll("[data-dense]").forEach(b=>{const on=b.dataset.dense===d.dense;b.classList.toggle("on",on);b.setAttribute("aria-pressed",String(on))});$(".dg")?.classList.toggle("dense",R.dense)}
    else if(d.csv)exportCsv(t);
    else if(d.clear!=null){R.q="";R.filter="all";R.page=0;const q=$("#gq");if(q)q.value="";renderGrid()}
    else if(d.pv)setPanel(S.panel.mode==="panel"?"split":S.panel.mode,d.pv);
    else if(d.ms){S.msView=d.ms;renderTab()}
    else if(d.dl)download(d.dl);
    else if(d.copy)copyPaper(t);
    else if(d.gev!=null)t.nextElementSibling.hidden=!t.nextElementSibling.hidden;
    else if(d.node)selectNode(d.node)};
  pane.oninput=e=>{if(e.target.id==="gq"){S.res.q=e.target.value;S.res.page=0;renderGrid()}};
  pane.onchange=e=>{const t=e.target;
    if(t.id==="gsize"){S.res.size=+t.value;S.res.page=0;ls.set("plato_grid_size",t.value);renderGrid()}
    else if(t.dataset.col){t.checked?S.res.hidden.delete(t.dataset.col):S.res.hidden.add(t.dataset.col);ls.set("plato_grid_hidden",JSON.stringify([...S.res.hidden]));renderGrid()}}}
function closeMenus(){let any=false;document.querySelectorAll(".menu-w>.menu:not([hidden])").forEach(m=>{m.hidden=true;m.parentElement.querySelector("[aria-expanded]")?.setAttribute("aria-expanded","false");any=true});return any}
document.addEventListener("pointerdown",e=>{if(!e.target.closest?.(".menu-w"))closeMenus()});

/* ---------- live updates: summary every 5s while running, full reload when it changes ---------- */
function schedulePoll(){clearTimeout(S.timer);const c=S.summary?.campaign;if(!c||!ACTIVE(c))return;
  const sig=c.updated_at+JSON.stringify(S.summary.node_counts)+S.summary.guard_events.length;
  S.timer=setTimeout(async()=>{if(S.route.id!==c.id||document.hidden)return schedulePoll();
    try{const s=await getJSON("campaigns/"+c.id);if(S.route.id!==c.id)return;
      if(s.campaign.updated_at+JSON.stringify(s.node_counts)+s.guard_events.length!==sig){
        const g=await getJSON(`campaigns/${c.id}/graph`);if(S.route.id!==c.id)return;
        const was=S.summary.campaign.status;S.summary=s;S.graph=g;
        if(!ACTIVE(s.campaign)){S.manuscript=undefined;loadList()}
        (was!=="writing"&&s.campaign.status==="writing"&&wide()?Kit.transition:fn=>fn())(renderCampaign);loadUsage();
        if(s.campaign.status==="writing"&&!S.draftTimer&&!S.draftBusy)pollDraft()}}catch{}
    schedulePoll()},5000)}
document.addEventListener("visibilitychange",()=>{if(!document.hidden&&S.summary?.campaign?.status==="writing"&&!S.draftBusy)pollDraft()});

/* ---------- command menu ---------- */
let CMD={items:[],sel:0};
function openCmd(){overlay(`<div class="modal cmd" role="dialog" aria-label="Command menu"><input class="cmd-in" id="cmdIn" placeholder="Search projects, campaigns or commands…" autocomplete="off" aria-label="Command" role="combobox" aria-expanded="true" aria-controls="cmdL"><div class="cmd-l" id="cmdL" role="listbox"></div></div>`);
  const i=$("#cmdIn");CMD.sel=0;i.oninput=()=>{CMD.sel=0;renderCmd()};
  i.onkeydown=e=>{if(e.key==="ArrowDown"||(e.ctrlKey&&e.key==="n")){e.preventDefault();CMD.sel=Math.min(CMD.items.length-1,CMD.sel+1);renderCmd()}
    else if(e.key==="ArrowUp"||(e.ctrlKey&&e.key==="p")){e.preventDefault();CMD.sel=Math.max(0,CMD.sel-1);renderCmd()}
    else if(e.key==="Enter"){e.preventDefault();runCmd(CMD.sel)}};
  renderCmd();i.focus()}
function renderCmd(){const q=($("#cmdIn")?.value||"").trim().toLowerCase(),id=S.route.id;
  const acts=[{s:"Actions",l:"Ask Plato",k:"⌘J",run:askShortcut},{s:"Actions",l:"New project",run:()=>{location.hash="#/agent"}},{s:"Actions",l:"New campaign",k:"C",run:openNew},
    {s:"Actions",l:"All campaigns",run:()=>go(null)},{s:"Actions",l:document.documentElement.dataset.theme==="dark"?"Switch to light theme":"Switch to dark theme",run:()=>$("#themeBtn").click()},
    {s:"Actions",l:"Settings",run:()=>{location.hash="#/settings/preferences"}},{s:"Actions",l:"Log out",run:logout}];
  const tabs=id?TABS.map(([k,l],i)=>({s:"This campaign",l:"Open "+l,k:String(i+1),run:()=>go(id,k)})):[];
  const panel=id&&S.summary&&wide()&&S.route.tab!=="manuscript"?[...(paperAvail()?[{s:"Panel",l:S.summary.campaign.status==="writing"?"Watch the paper being written":"Show the paper",k:"P",run:()=>setPanel(S.panel.mode==="panel"?"split":S.panel.mode,"paper")}]:[]),
    {s:"Panel",l:"Panel: side",k:"[",run:()=>setPanel("panel")},{s:"Panel",l:"Panel: split view",run:()=>setPanel("split")},{s:"Panel",l:"Panel: focus",k:"]",run:()=>setPanel("focus")}]:[];
  const camps=(S.campaigns||[]).map(c=>({s:"Campaigns",l:c.research_question,icon:campaignIcon(c.status),run:()=>go(c.id)}));
  const projs=(S.projects||[]).map(p=>({s:"Projects",l:p.title,icon:ico(CHAT),run:()=>{location.hash=`#/p/${eid(p.id)}`}}));
  CMD.items=[...acts,...tabs,...panel,...projs,...camps].filter(x=>!q||x.l.toLowerCase().includes(q)).slice(0,50);CMD.sel=Math.min(CMD.sel,Math.max(0,CMD.items.length-1));
  let h="",last="";CMD.items.forEach((x,i)=>{if(x.s!==last){h+=`<div class="cmd-s">${esc(x.s)}</div>`;last=x.s}
    h+=`<button class="cmd-i${i===CMD.sel?" on":""}" data-ci="${i}" role="option" aria-selected="${i===CMD.sel}" type="button">${x.icon||'<span style="width:14px"></span>'}<span class="trunc">${esc(x.l)}</span>${x.k?`<span class="kbd">${esc(x.k)}</span>`:""}</button>`});
  const L=$("#cmdL");if(!L)return;L.innerHTML=h||'<p class="t3" style="padding:10px">No matches.</p>';
  L.querySelectorAll("[data-ci]").forEach(b=>{b.onclick=()=>runCmd(+b.dataset.ci);b.onmousemove=()=>{if(CMD.sel!==+b.dataset.ci){CMD.sel=+b.dataset.ci;renderCmd()}}});
  L.querySelector(".cmd-i.on")?.scrollIntoView({block:"nearest"})}
function runCmd(i){const x=CMD.items[i];if(!x)return;closeOverlay();x.run()}
$("#cmdBtn").onclick=openCmd;

/* ---------- list navigation: J/K moves, Enter opens ---------- */
let KB=-1;
function kbRows(){return [...document.querySelectorAll("#body .row[data-node], #body a.row, #body tr[data-node]")]}
function kbMove(d){const rows=kbRows();if(!rows.length)return;rows.forEach(r=>r.classList.remove("kb"));
  KB=Math.max(0,Math.min(rows.length-1,(rows.indexOf(document.querySelector("#body .kb"))>=0?KB:KB<0?-1:KB)+d));
  const r=rows[KB];r.classList.add("kb");r.scrollIntoView({block:"nearest"})}

/* ---------- keyboard ---------- */
/** ⌘J: the ask panel; on the agent's own pages, its composer. */
function askShortcut(){if(["agent","project"].includes(S.route.view)){$("#homeC,#projC")?.text.focus();return}closeOverlay();toggleAsk()}
addEventListener("keydown",e=>{
  if(!S.me?.account)return;
  const mod=e.metaKey||e.ctrlKey,k=e.key.toLowerCase();
  if(mod&&k==="k"){e.preventDefault();if($("#cmdIn"))closeOverlay();else openCmd();return}
  if(mod&&k==="j"&&!e.altKey&&!e.shiftKey){e.preventDefault();askShortcut();return}
  if(e.key==="Escape"){if(closeMenus())return;if($("#overlay .scrim")){closeOverlay();return}if(S.ask.open){closeAsk();return}
    if($("#body.show-threads")){$("#body").classList.remove("show-threads");return}
    $("#side").classList.remove("open");if(S.panel.mode==="focus"&&S.summary&&S.route.view==="campaign")setPanel("split");return}
  if($("#overlay .scrim"))return;
  if(/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)||e.metaKey||e.ctrlKey||e.altKey)return;
  if(e.key==="c"||e.key==="C"){e.preventDefault();openNew()}
  else if(e.key==="/"&&$("#gq")){e.preventDefault();$("#gq").focus()}
  else if(e.key==="j"||e.key==="ArrowDown"){if(kbRows().length&&!e.target.closest?.(".sl")){e.preventDefault();kbMove(1)}}
  else if(e.key==="k"||e.key==="ArrowUp"){if(kbRows().length&&!e.target.closest?.(".sl")){e.preventDefault();kbMove(-1)}}
  else if(e.key==="Enter"){const r=document.querySelector("#body .kb");if(r&&!e.target.closest?.("button,a,.sl")){e.preventDefault();r.click()}}
  else if(S.route.view==="campaign"&&S.summary){
    if(/^[1-7]$/.test(e.key))go(S.route.id,TABS[+e.key-1][0]);
    else if(e.key==="["||e.key==="]")stepPanel(e.key==="]"?1:-1);
    else if((e.key==="p"||e.key==="P")&&paperAvail()&&S.route.tab!=="manuscript"){if(S.panel.view==="paper")setPanel(S.panel.mode,"details");else setPanel(S.panel.mode==="panel"&&wide()?"split":S.panel.mode,"paper")}}});
$("#menuBtn").onclick=()=>$("#side").classList.toggle("open");
$("#nav").addEventListener("click",e=>{const h=e.target.closest("[data-sec]");
  if(!h){$("#side").classList.remove("open");return}
  const k=h.dataset.sec;NAV_CLOSED.has(k)?NAV_CLOSED.delete(k):NAV_CLOSED.add(k);ls.set("plato_nav_closed",JSON.stringify([...NAV_CLOSED]));renderNav();$(`#nav [data-sec="${k}"]`)?.focus()});

/* ---------- router ---------- */
function route(){const prev=S.route,r=S.route=parseRoute(),v=r.view;
  if(!S.me?.account){   // signed out: everything but the sign-in screens waits behind them
    if(v!=="login"&&v!=="signup"){S.next=location.hash.length>2?location.hash:"";location.replace("#/login");return}
    renderAuth(v);return}
  if(v==="login"||v==="signup"){location.replace(S.next||"#/");S.next="";return}
  document.body.classList.remove("signed-out");$("#auth").innerHTML="";$("#side").classList.remove("open");closeMenus();
  if(prev.id!==r.id)S.selected=null;
  if(prev.view==="campaign"&&v!=="campaign"){clearTimeout(S.timer);resetCampaignState()}
  if(v!=="project")clearTimeout(S.projTimer);
  if(v==="agent"||v==="project")closeAsk(true);
  renderNav();updateAskBtn();renderAskCtx();
  if(v==="campaign"){if(prev.id===r.id&&S.summary?.campaign?.id===r.id)renderCampaign();else openCampaign(r.id);return}
  if(v==="project")openProject(r.pid);
  else if(v==="settings")renderSettings();
  else if(v==="campaigns")renderHome();
  else renderAgentHome();
  Kit.sweepCharts()}
