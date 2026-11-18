/* The agent: the home composer, projects (a conversation with the orchestrator, which starts
   research threads), and the ask panel available on every page (⌘J). Loaded after app.js;
   defines functions only. */
"use strict";

const SPARK='<path d="M8 1.5c.4 2.9 1.7 4.3 4.6 4.7.3 0 .3.5 0 .6C9.7 7.2 8.4 8.6 8 11.5c0 .3-.5.3-.6 0C7 8.6 5.6 7.2 2.8 6.8c-.3-.1-.3-.6 0-.6C5.6 5.8 7 4.4 7.4 1.5c.1-.3.6-.3.6 0Z"/><path d="M12.5 10.5c.2 1.2.7 1.7 1.9 1.9-1.2.2-1.7.7-1.9 1.9-.2-1.2-.7-1.7-1.9-1.9 1.2-.2 1.7-.7 1.9-1.9Z"/>';
const CHAT='<path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h7A1.5 1.5 0 0 1 13 4.5v5a1.5 1.5 0 0 1-1.5 1.5H7l-3 2.5V11h.5"/>';
const SPIN='<svg class="spin" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M8 2a6 6 0 1 1-6 6"/></svg>';
const ARROW_UP='<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 13V3.5M3.8 7.5 8 3.3l4.2 4.2"/></svg>';
const EYE='<path d="M1.8 8s2.3-4.2 6.2-4.2S14.2 8 14.2 8 11.9 12.2 8 12.2 1.8 8 1.8 8Z"/><circle cx="8" cy="8" r="1.8"/>';
const LIST='<path d="M5.5 4.5h8M5.5 8h8M5.5 11.5h8"/><circle cx="2.8" cy="4.5" r=".6"/><circle cx="2.8" cy="8" r=".6"/><circle cx="2.8" cy="11.5" r=".6"/>';
const SUGGEST=["Does the 95% OLS slope interval keep its coverage when errors are heteroskedastic?","Compare bootstrap and HC3 intervals at small sample sizes",
  "Is Benford's law a reliable fraud signal for small ledgers?","Which simple models best forecast monthly CO₂ at Mauna Loa?"];
const hintText=()=>pref("send_with_mod_enter")?"⌘ Enter to send":"Enter to send · Shift Enter for a new line";

/* ---------- Markdown (escaped first: model text never becomes markup) ---------- */
function md(src){const code=[];let s=String(src??"").replace(/\r\n?/g,"\n");
  s=s.replace(/```[^\n]*\n([\s\S]*?)```/g,(_,c)=>{code.push(`<pre><code>${esc(c.replace(/\n$/,""))}</code></pre>`);return `\n\u0000${code.length-1}\u0000\n`});
  const inline=t=>esc(t).replace(/`([^`\n]+)`/g,"<code>$1</code>").replace(/\*\*([^*\n]+)\*\*/g,"<strong>$1</strong>").replace(/(^|[^*\w])\*([^*\s][^*\n]*?)\*(?!\w)/g,"$1<em>$2</em>")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+|#\/[^\s)]*)\)/g,(_,t,u)=>`<a href="${u}"${u[0]==="#"?"":' target="_blank" rel="noopener noreferrer"'}>${t}</a>`);
  const out=[];let para=[],list=null;
  const flush=()=>{if(para.length){out.push(`<p>${para.map(inline).join("<br>")}</p>`);para=[]}
    if(list){out.push(`<${list.t}>${list.items.map(i=>`<li>${inline(i)}</li>`).join("")}</${list.t}>`);list=null}};
  for(const line of s.split("\n")){const t=line.trim(),cb=/^\u0000(\d+)\u0000$/.exec(t);
    if(cb){flush();out.push(code[+cb[1]]);continue}
    if(!t){flush();continue}
    const h=/^#{1,6}\s+(.*)$/.exec(t);if(h){flush();out.push(`<h4>${inline(h[1])}</h4>`);continue}
    const ul=/^\s*[-*•]\s+(.*)$/.exec(line),ol=/^\s*\d+[.)]\s+(.*)$/.exec(line);
    if(ul||ol){const k=ul?"ul":"ol";if(para.length||(list&&list.t!==k))flush();(list??={t:k,items:[]}).items.push((ul||ol)[1]);continue}
    if(list&&/^\s{2,}\S/.test(line)){list.items[list.items.length-1]+=" "+t;continue}
    if(list)flush();para.push(t)}
  flush();return out.join("")}

/* ---------- composer ---------- */
function composerHtml(id,{big=false,placeholder="Ask Plato…"}={}){
  return `<form class="composer${big?" big":""}" id="${id}" autocomplete="off"><div class="ctxrow" hidden style="padding:10px 12px 0"></div>
    <textarea name="text" rows="1" maxlength="8000" placeholder="${esc(placeholder)}" aria-label="Message"></textarea>
    <div class="composer-f"><span class="hint trunc">${esc(hintText())}</span><button class="send" type="submit" aria-label="Send" disabled>${ARROW_UP}</button></div></form>`}
function bindComposer(form,onSend){const ta=form.text,btn=form.querySelector(".send");
  const fit=()=>{ta.style.height="auto";ta.style.height=Math.min(ta.scrollHeight+2,innerHeight*.4)+"px";btn.disabled=!ta.value.trim()||!!form.dataset.busy};
  form.fit=fit;ta.oninput=fit;
  ta.onkeydown=e=>{if(e.key!=="Enter"||e.isComposing)return;const mod=e.metaKey||e.ctrlKey;
    if(pref("send_with_mod_enter")?mod:(mod||!e.shiftKey)){e.preventDefault();form.requestSubmit()}};
  form.onsubmit=async e=>{e.preventDefault();const text=ta.value.trim();if(!text||form.dataset.busy)return;
    form.dataset.sending="1";ta.value="";fit();const ok=await onSend(text);delete form.dataset.sending;if(ok===false&&!ta.value)ta.value=text;fit()};
  fit()}
function setBusy(form,busy,label){if(!form)return;if(busy)form.dataset.busy="1";else delete form.dataset.busy;
  const h=form.querySelector(".hint");if(h)h.textContent=busy?label||"Plato is working…":hintText();form.fit?.()}

/* ---------- conversation ---------- */
const parseJSON=t=>{try{return JSON.parse(t)}catch{return null}};
const pico=html=>`<span class="pico">${html}</span>`;
function toolHtml(b,r,threads){
  if(b.name==="start_research_thread"){
    if(!r)return `<div class="tool">${SPIN}Starting a research thread…</div>`;
    if(r.is_error)return `<div class="tool bad">${cross("var(--red)")}<span>Couldn't start a thread: ${esc(r.content)}</span></div>`;
    const out=parseJSON(r.content)||{},id=out.thread_id,t=threads[id]||{},st=t.status||"ideation";
    return `<a class="tcard" href="#/c/${eid(id)}/overview">${pico(campaignIcon(st))}<div class="tcard-b"><div class="tcard-k">Research thread · <span class="mono">${cid(id)}</span> · ${esc(PHASE_LABEL[st]||st)}</div><div class="tcard-q">${esc(t.research_question||out.question||"")}</div></div></a>`}
  if(b.name==="list_threads")return `<div class="tool">${r?ico(LIST):SPIN}${r?"Checked":"Checking"} research threads</div>`;
  if(b.name==="get_thread")return `<div class="tool">${r?ico(EYE):SPIN}${r?"Read":"Reading"} thread <span class="mono">${cid(b.input?.thread_id||"")}</span></div>`;
  return ""}
function chatHtml(P){const results={},threads=Object.fromEntries((P.threads||[]).map(t=>[t.id,t]));
  for(const m of P.messages)if(m.role==="user")for(const b of m.content)if(b.type==="tool_result")results[b.tool_use_id]=b;
  let h="";
  for(const m of P.messages){
    if(m.role==="user"){const texts=m.content.filter(b=>b.type==="text");if(!texts.length)continue;
      const ctx=texts.find(b=>b.text.startsWith("<context>")),said=texts.filter(b=>b!==ctx).map(b=>b.text).join("\n\n"),cidm=ctx&&/thread ([0-9a-f-]{36})/.exec(ctx.text);
      h+=`<div class="msg me">${cidm?`<span class="ctxchip">${ico(EYE,12)}Viewing <span class="mono">${cid(cidm[1])}</span></span>`:""}<div class="bubble">${esc(said)}</div></div>`;continue}
    let inner="";for(const b of m.content){if(b.type==="text"&&b.text.trim())inner+=`<div class="md">${md(b.text)}</div>`;else if(b.type==="tool_use")inner+=toolHtml(b,results[b.id],threads)}
    if(m.stop_reason==="refusal")inner+=`<div class="tool">Plato declined to answer this.</div>`;
    if(inner)h+=`<div class="msg ai">${inner}</div>`}
  if(P.pending)h+=`<div class="msg me"><div class="bubble">${esc(P.pending)}</div></div>`;
  const st=P.project?.agent_status;
  if(st==="working"||P.pending)h+=`<div class="msg ai"><span class="thinking">Thinking…</span></div>`;
  else if(st==="error")h+=`<div class="msg ai"><div class="agent-err">${cross("var(--red)")}<span>${esc(P.project.agent_error||"Something went wrong.")}</span><button class="btn" type="button" data-retry>Retry</button></div></div>`;
  return h}
const nearBottom=el=>!el||el.scrollHeight-el.scrollTop-el.clientHeight<96;
/** Fetch what's new in a project into P; true if anything changed. */
async function fetchInto(P){const pid=P.project.id,after=P.messages.at(-1)?.id||0,was=P.project.agent_status;
  const d=await getJSON(`projects/${eid(pid)}${after?`?after=${after}`:""}`);
  const sig=JSON.stringify(P.threads.map(t=>[t.status,t.tokens_used]));
  P.project=d.project;P.threads=d.threads;P.loading=false;if(d.messages.length)P.messages=P.messages.concat(d.messages);
  if(was==="working"&&d.project.agent_status!=="working")loadProjects();
  return d.messages.length>0||was!==d.project.agent_status||sig!==JSON.stringify(d.threads.map(t=>[t.status,t.tokens_used]))}
async function retry(P){try{await api(`projects/${eid(P.project.id)}/retry`,{method:"POST"});P.project.agent_status="working";return true}catch(e){toast(e.message,true);return false}}
async function say(P,text,ctx){P.pending=text;
  try{await postJSON(`projects/${eid(P.project.id)}/messages`,{text,...(ctx?{context:{campaign_id:ctx}}:{})});P.project.agent_status="working";await fetchInto(P).catch(()=>{});return true}
  catch(e){toast(e.message,true);return false}finally{P.pending=null}}

/* ---------- projects ---------- */
async function loadProjects(){if(!S.me?.account)return;try{S.projects=(await getJSON("projects")).projects;renderNav();if(S.route.view==="agent")renderRecent()}
  catch(e){if(S.projects==null)S.projects=[];if(S.route.view==="agent")renderRecent()}}
const prow=p=>`<a class="prow" href="#/p/${eid(p.id)}">${pico(p.agent_status==="working"?SPIN:ico(CHAT))}<span class="title trunc">${esc(p.title)}</span>
  <span class="meta">${p.active?`<span class="chip"><i style="background:var(--yellow)"></i>${p.active} running</span>`:p.threads?`<span class="hide-sm">${p.threads} thread${p.threads>1?"s":""}</span>`:""}<span style="width:64px;text-align:right">${ago(p.updated_at)}</span></span></a>`;
function renderRecent(){const el=$("#recent");if(!el)return;const ps=S.projects;
  if(ps==null){Kit.skeleton(el,`<div class="ah-h">Recent projects</div>`+[0,1,2].map(i=>prow({id:"x"+i,title:"A sample project title of typical length",updated_at:new Date().toISOString(),threads:1})).join(""),"recent");return}
  el.innerHTML=ps.length?`<div class="ah-h">Recent projects</div>${ps.slice(0,10).map(prow).join("")}`:"";Kit.reveal(el,"recent")}

/* ---------- agent home ---------- */
function renderAgentHome(){$("#crumb").innerHTML=`<b>Agent</b>`;$("#tabs").innerHTML="";$("#tabs").className="";$("#topActions").innerHTML="";S.lastView="";
  if($("#pane")?.dataset.view==="agent"){renderRecent();return}   // keep a half-typed prompt
  const body=$("#body");body.className="body full";const first=(S.me.account.name||"").trim().split(/\s+/)[0];
  body.innerHTML=`<div class="pane" id="pane" data-view="agent"><div class="ah"><div class="ah-mark">${ico(SPARK,18)}</div>
    <h1>What should we research${first?", "+esc(first):""}?</h1><p class="lede">Describe what you want to find out. Plato starts research threads that run on their own and reports back.</p>
    ${composerHtml("homeC",{big:true,placeholder:"Ask a research question, or describe what you want to know…"})}
    <div class="sugg">${SUGGEST.map(s=>`<button type="button" data-s="${esc(s)}">${esc(s)}</button>`).join("")}</div>
    <div class="ah-recent" id="recent"></div></div></div>`;
  const f=$("#homeC");bindComposer(f,async text=>{setBusy(f,true,"Starting…");
    try{const r=await postJSON("projects",{text});S.proj=null;location.hash=`#/p/${eid(r.id)}`;loadProjects();return true}
    catch(e){toast(e.message,true);return false}finally{setBusy(f,false)}});
  $(".sugg").onclick=e=>{const b=e.target.closest("[data-s]");if(!b)return;f.text.value=b.dataset.s;f.fit();f.text.focus()};
  renderRecent();if(matchMedia("(pointer:fine)").matches)f.text.focus()}

/* ---------- project view ---------- */
const SAMPLE_CHAT={project:{agent_status:"idle"},threads:[],messages:[{role:"user",content:[{type:"text",text:"A sample question about a research topic of typical length"}]},
  {role:"assistant",content:[{type:"text",text:"Sample answer text standing in for the agent's reply while it loads. ".repeat(3)}]}]};
const threadsHtml=ts=>ts.length?ts.map(t=>{const p=Math.min(100,100*t.tokens_used/Math.max(1,t.token_budget_max));
  return `<a class="trow" href="#/c/${eid(t.id)}/overview">${pico(campaignIcon(t.status))}<div style="min-width:0;flex:1"><div class="q">${esc(t.research_question)}</div>
    <div class="m"><span class="mono">${cid(t.id)}</span><span>${esc(PHASE_LABEL[t.status]||t.status)}</span><span class="bar" style="width:44px"><span style="width:${p}%"></span></span><span>${short(t.tokens_used)}</span></div></div></a>`}).join("")
  :`<div class="threads-e">Research threads the agent starts appear here. Each runs on its own and writes up what holds.</div>`;

function openProject(pid){clearTimeout(S.projTimer);
  if(S.proj?.project?.id!==pid)S.proj={project:{id:pid,title:"",agent_status:"idle"},messages:[],threads:[],loading:true};
  const P=S.proj,body=$("#body");$("#tabs").innerHTML="";$("#tabs").className="";
  if($("#pane")?.dataset.pid!==pid){body.className="body proj";
    body.innerHTML=`<div class="pane" id="pane" data-pid="${esc(pid)}"><div class="chat"><div class="chat-s" id="chatS"><div class="chat-in" id="chatIn"></div></div>
      <div class="chat-c">${composerHtml("projC",{placeholder:"Reply to Plato…"})}</div></div></div><aside class="props" id="props"><div class="threads-h">Research threads<span class="n" id="tn"></span></div><div id="threads"></div></aside>`;
    bindComposer($("#projC"),async text=>{const ok=await say(P,text);renderProject(true);scheduleProject();return ok});
    $("#chatIn").onclick=async e=>{if(e.target.closest("[data-retry]")&&await retry(P)){renderProject(true);scheduleProject()}};
    if(P.loading){Kit.skeleton($("#chatIn"),chatHtml(SAMPLE_CHAT),"chat");Kit.skeleton($("#crumb"),`<a class="t2" href="#/agent">Agent</a><b>Sample project title</b>`,"crumb")}}
  if(!P.loading)renderProject(true);
  refreshProject()}
function renderProject(stick){const P=S.proj;if(!P||S.route.pid!==P.project.id||P.loading)return;const sc=$("#chatS"),near=stick||nearBottom(sc);
  $("#crumb").innerHTML=`<a class="t2" href="#/agent" style="text-decoration:none">Agent</a><span class="t3">›</span><b class="trunc">${esc(P.project.title)}</b>`;
  $("#topActions").innerHTML=`<button class="btn sm threads-btn" type="button" id="thBtn" aria-controls="props" aria-expanded="${$("#body").classList.contains("show-threads")}">Threads${P.threads.length?`<span class="t3">${P.threads.length}</span>`:""}</button><div class="menu-w"><button class="icon-btn" id="pmBtn" type="button" aria-label="Project actions" aria-haspopup="menu" aria-expanded="false">${ico('<circle cx="3.5" cy="8" r=".9"/><circle cx="8" cy="8" r=".9"/><circle cx="12.5" cy="8" r=".9"/>')}</button>
    <div class="menu" id="pm" role="menu" hidden style="left:auto;right:0"><button class="mi" type="button" data-pm="rename" role="menuitem">Rename…</button><button class="mi danger" type="button" data-pm="delete" role="menuitem">Delete project…</button></div></div>`;
  $("#thBtn").onclick=()=>{const on=$("#body").classList.toggle("show-threads");$("#thBtn").setAttribute("aria-expanded",String(on))};
  $("#pmBtn").onclick=()=>{const m=$("#pm");m.hidden=!m.hidden;$("#pmBtn").setAttribute("aria-expanded",String(!m.hidden))};
  $("#pm").onclick=e=>{const a=e.target.closest("[data-pm]")?.dataset.pm;$("#pm").hidden=true;if(a==="rename")renameProject(P);else if(a==="delete")deleteProject(P)};
  $("#chatIn").innerHTML=chatHtml(P);$("#tn").textContent=P.threads.length||"";$("#threads").innerHTML=threadsHtml(P.threads);
  setBusy($("#projC"),P.project.agent_status==="working"||!!P.pending);
  Kit.reveal($("#chatIn"),"chat");Kit.reveal($("#crumb"),"crumb");if(near)sc.scrollTop=sc.scrollHeight}
async function refreshProject(){const P=S.proj,pid=P?.project.id;if(!P)return;
  try{const changed=await fetchInto(P);if(S.route.pid!==pid)return;if(changed||!$("#chatIn").children.length||$("#chatIn [data-sk]"))renderProject(!P._seen);P._seen=true}
  catch(e){if(S.route.pid!==pid)return;if(e.status===404){$("#body").className="body full";$("#body").innerHTML=`<div class="pane" id="pane"><div class="empty"><div>${cross("var(--red)")}<h3>Project not found</h3><p>It may have been deleted.</p><a class="btn" href="#/agent" style="text-decoration:none">Back to the agent</a></div></div></div>`;$("#crumb").innerHTML="<b>Project</b>";return}}
  scheduleProject()}
function scheduleProject(){clearTimeout(S.projTimer);const P=S.proj;if(!P||S.route.view!=="project")return;
  S.projTimer=setTimeout(()=>{if(document.hidden)return scheduleProject();refreshProject()},P.project.agent_status==="working"?1200:8000)}
function renameProject(P){overlay(`<form class="modal" id="rnForm" style="width:min(420px,100%)" role="dialog" aria-label="Rename project"><div class="m-h" style="font-size:14px;color:var(--text);font-weight:500;padding-top:16px">Rename project</div>
  <div class="m-b"><input class="field" name="title" maxlength="200" required value="${esc(P.project.title)}" aria-label="Title"></div><div class="m-f" style="justify-content:flex-end"><button class="btn" type="button" data-x>Cancel</button><button class="btn primary">Save</button></div></form>`);
  const f=$("#rnForm");f.title.select();f.onsubmit=async e=>{e.preventDefault();try{const r=await postJSON(`projects/${eid(P.project.id)}`,{title:f.title.value.trim()},"PATCH");P.project.title=r.title;closeOverlay();renderProject();loadProjects()}catch(e2){toast(e2.message,true)}}}
async function deleteProject(P){if(!(await confirmModal("Delete this project?","The conversation is deleted. Research threads it started keep running and stay in Campaigns.","Delete project",true)))return;
  try{await api(`projects/${eid(P.project.id)}`,{method:"DELETE"});if(ls.get(askKey())===P.project.id)ls.set(askKey(),"");S.proj=null;toast("Project deleted");loadProjects();location.hash="#/agent"}catch(e){toast(e.message,true)}}

/* ---------- ask panel (⌘J) ---------- */
S.ask={open:false,P:null,timer:0,ctxOff:null};
const askKey=()=>"plato_ask_"+(S.me?.account?.id||"anon");
function askCtx(){const c=S.route.view==="campaign"&&S.summary?.campaign;return c&&S.ask.ctxOff!==c.id?c:null}
function updateAskBtn(){const f=$("#askFab");if(f)f.hidden=!S.me?.account||S.ask.open||["agent","project"].includes(S.route.view)}
function openAsk(){if(!S.me?.account)return;S.ask.open=true;const el=$("#ask");el.hidden=false;document.body.classList.add("ask-open");
  el.innerHTML=`<div class="ask-h"><b>${ico(SPARK)}Ask Plato</b><button class="icon-btn" type="button" data-ask="open" title="Open as a project" aria-label="Open as a project">${ico('<path d="M9.5 2.5h4v4M13.5 2.5 8.5 7.5M7 3.5H4A1.5 1.5 0 0 0 2.5 5v7A1.5 1.5 0 0 0 4 13.5h7a1.5 1.5 0 0 0 1.5-1.5V9"/>')}</button>
    <button class="icon-btn" type="button" data-ask="new" title="New conversation" aria-label="New conversation">${ico('<path d="M8 3v10M3 8h10"/>')}</button><button class="icon-btn" type="button" data-ask="close" title="Close (Esc)" aria-label="Close">${ico('<path d="m4 4 8 8M12 4l-8 8"/>')}</button></div>
    <div class="chat"><div class="chat-s" id="askS"><div class="chat-in" id="askIn"></div></div><div class="chat-c">${composerHtml("askC",{placeholder:"Ask about your research…"})}</div></div>`;
  bindComposer($("#askC"),sendAsk);
  el.onclick=e=>{const a=e.target.closest("[data-ask]")?.dataset.ask,P=S.ask.P;
    if(a==="close")closeAsk();
    else if(a==="new"){S.ask.P=null;ls.set(askKey(),"");renderAsk();$("#askC").text.focus()}
    else if(a==="open"){if(P?.project.id){location.hash=`#/p/${eid(P.project.id)}`}else toast("Ask something first")}
    else if(e.target.closest("[data-ctx-x]")){S.ask.ctxOff=askCtx()?.id;renderAsk()}
    else if(e.target.closest("[data-q]")){const f=$("#askC");f.text.value=e.target.closest("[data-q]").dataset.q;f.fit();f.requestSubmit()}
    else if(e.target.closest("[data-retry]")&&P)retry(P).then(ok=>{if(ok){renderAsk(true);scheduleAsk()}})};
  const pid=ls.get(askKey());
  if(pid&&S.ask.P?.project.id!==pid){S.ask.P={project:{id:pid,agent_status:"idle"},messages:[],threads:[],loading:true};refreshAsk()}
  renderAsk(true);updateAskBtn();$("#askC").text.focus()}
function closeAsk(silent){if(!S.ask)return;const was=S.ask.open;S.ask.open=false;clearTimeout(S.ask.timer);document.body.classList.remove("ask-open");const el=$("#ask");if(el){el.hidden=true;el.innerHTML=""}updateAskBtn();if(was&&!silent)$("#askBtn")?.focus()}
const toggleAsk=()=>S.ask.open?closeAsk():openAsk();
/** The thread being viewed rides along as context; follows navigation while the panel is open. */
function renderAskCtx(){const row=S.ask.open&&$("#askC .ctxrow");if(!row)return null;const c=askCtx(),key=c?c.id:"";
  if(row.dataset.cid!==key){row.dataset.cid=key;row.hidden=!c;
    row.innerHTML=c?`<span class="ctx" title="${esc(c.research_question)}">${ico(EYE,12)}<span class="trunc">${cid(c.id)} · ${esc(c.research_question)}</span><button type="button" data-ctx-x aria-label="Don't include this thread">${ico('<path d="m4.5 4.5 7 7m0-7-7 7"/>',11)}</button></span>`:""}
  return c}
function renderAsk(stick){if(!S.ask.open)return;const P=S.ask.P,el=$("#askIn"),sc=$("#askS"),near=stick||nearBottom(sc),c=renderAskCtx();
  if(P?.loading)Kit.skeleton(el,chatHtml(SAMPLE_CHAT),"ask");
  else if(!P||(!P.messages.length&&!P.pending)){const qs=c?["Summarize what this thread has found so far","What should I investigate next?","Explain this thread's results in plain words"]:["What are my research threads working on?","Which of my threads found something solid?","Start a thread on a question I describe"];
    el.innerHTML=`<div class="ask-empty">${ico(SPARK,20)}<h3>Ask about your research</h3><p>Plato can check on your threads, explain results, or start new research.</p><div class="sugg" style="flex-direction:column;align-items:center">${qs.map(q=>`<button type="button" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div></div>`}
  else{el.innerHTML=chatHtml(P);Kit.reveal(el,"ask")}
  setBusy($("#askC"),P?.project.agent_status==="working"||!!P?.pending);if(near&&sc)sc.scrollTop=sc.scrollHeight}
async function refreshAsk(){const P=S.ask.P;if(!P||!S.ask.open)return;
  try{const changed=await fetchInto(P);if(S.ask.P!==P)return;if(changed||P._first!==false){P._first=false;renderAsk(true)}}
  catch(e){if(e.status===404&&S.ask.P===P){S.ask.P=null;ls.set(askKey(),"");renderAsk()}return}
  scheduleAsk()}
function scheduleAsk(){clearTimeout(S.ask.timer);const P=S.ask.P;if(!S.ask.open||!P||P.project.agent_status!=="working")return;S.ask.timer=setTimeout(refreshAsk,1200)}
async function sendAsk(text){const c=askCtx();let P=S.ask.P;
  if(!P){P=S.ask.P={project:{id:null,agent_status:"idle"},messages:[],threads:[],pending:text};renderAsk(true);
    try{const r=await postJSON("projects",{text,...(c?{context:{campaign_id:c.id}}:{})});P.project={id:r.id,agent_status:"working"};ls.set(askKey(),r.id);P.pending=null;await fetchInto(P).catch(()=>{});loadProjects()}
    catch(e){S.ask.P=null;toast(e.message,true);renderAsk();return false}
    renderAsk(true);scheduleAsk();return true}
  const pr=say(P,text,c?.id);renderAsk(true);const ok=await pr;renderAsk(true);scheduleAsk();return ok}
