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
const PLUS='<path d="M8 3.5v9M3.5 8h9"/>',CHEV='<path d="m4.5 6.5 3.5 3.5 3.5-3.5"/>',XMARK='<path d="m4.5 4.5 7 7m0-7-7 7"/>';
const KEY='<circle cx="5.5" cy="10.5" r="3"/><path d="m7.6 8.4 5.4-5.4M11 5l1.6 1.6M9.6 6.4l1.2 1.2"/>';
const hintText=()=>pref("send_with_mod_enter")?"⌘ Enter to send":"Enter to send · Shift Enter for a new line";
/* Home watermark: an icosahedron (one of Plato's solids) seen down a 3-fold axis, each visible face
   an inset, round-cornered hairline. Generated once; 336px like the page it mirrors. */
const WM_FACES=["M187.91 22.17Q183.63 16.64 189.69 20.14L296.83 82Q302.89 85.5 296.83 89L263.4 108.3Q257.34 111.8 253.05 106.27Z", "M148.09 22.17Q152.37 16.64 146.31 20.14L39.17 82Q33.11 85.5 39.17 89L72.6 108.3Q78.66 111.8 82.95 106.27Z", "M172.29 15.07Q168 9.53 163.71 15.07L92.13 107.48Q87.84 113.01 94.84 113.01L241.16 113.01Q248.16 113.01 243.87 107.48Z", "M51.67 258.16Q44.73 257.21 50.79 260.71L157.94 322.57Q164 326.07 164 319.07L164 280.47Q164 273.47 157.06 272.52Z", "M31.76 223.67Q29.11 230.15 29.11 223.15L29.11 99.43Q29.11 92.43 35.17 95.93L68.6 115.23Q74.66 118.73 72.01 125.21Z", "M37.7 248.18Q30.76 247.23 33.41 240.75L77.65 132.56Q80.3 126.08 83.8 132.14L156.96 258.85Q160.46 264.91 153.52 263.97Z", "M284.33 258.16Q291.27 257.21 285.21 260.71L178.06 322.57Q172 326.07 172 319.07L172 280.47Q172 273.47 178.94 272.52Z", "M304.24 223.67Q306.89 230.15 306.89 223.15L306.89 99.43Q306.89 92.43 300.83 95.93L267.4 115.23Q261.34 118.73 263.99 125.21Z", "M302.59 240.75Q305.24 247.23 298.3 248.18L182.48 263.97Q175.54 264.91 179.04 258.85L252.2 132.14Q255.7 126.08 258.35 132.56Z", "M93.61 121.01Q86.61 121.01 90.11 127.07L164.5 255.91Q168 261.98 171.5 255.91L245.89 127.07Q249.39 121.01 242.39 121.01Z"];
const WATERMARK=`<div class="ah-wm" aria-hidden="true"><svg width="336" height="336" viewBox="0 0 336 336" fill="none">${WM_FACES.map(d=>`<path d="${d}"/>`).join("")}</svg></div>`;
/* "Get started" cards: each fills the composer with a worked question, three at a time. Every one
   runs end to end on the experiment sandbox with public data and no GPU, and the set covers the
   domains Plato is built for. scripts/e2b_example_checks.py runs each card's core pipeline
   (same keys) against a known answer; keep the two in step. */
const EXAMPLES=[
  {key:"variants",icon:'<path d="M4.5 1.5c0 6.5 7 6.5 7 13M11.5 1.5c0 6.5-7 6.5-7 13"/><path d="M5.4 4h5.2M5.4 12h5.2"/>',
    t:"Benchmark variant callers",d:"Align reads with BWA-MEM2, call variants with GATK and bcftools",
    q:"Simulate 20× paired-end Illumina reads with known SNPs and indels from the E. coli K-12 MG1655 genome (NC_000913.3) using wgsim, align them with BWA-MEM2, and call variants with GATK HaplotypeCaller and bcftools. Which caller has higher precision and recall against the simulated truth, for SNPs and indels separately?"},
  {key:"hemoglobin",icon:'<path d="M3 11c2-6 3 2 5-3s3 3 5-2"/><path d="M3 5.5c2 2 3-1 5 1"/>',
    t:"Map a protein's shape change",d:"Superimpose 3D structures and find where they move",
    q:"How does human hemoglobin rearrange between the deoxy T state (PDB 4HHB) and the oxy R state (PDB 1HHO)? Superimpose the structures on the α1β1 dimer, measure the α2β2 rotation and per-residue Cα displacement, and test whether α1 residues at the α1β2 interface move more than the rest."},
  {key:"expression",icon:'<path d="M2 13.5h12"/><circle cx="4" cy="5" r=".9"/><circle cx="5.5" cy="8.5" r=".9"/><circle cx="8" cy="11" r=".9"/><circle cx="10.5" cy="7.5" r=".9"/><circle cx="12" cy="3.5" r=".9"/>',
    t:"Find drug-response genes",d:"RNA-seq with DESeq2, FDR control and GO enrichment",
    q:"In the airway RNA-seq dataset (Himes et al. 2014, GEO GSE52778), which genes change expression when airway smooth muscle cells are treated with dexamethasone, at a 5% false discovery rate with DESeq2 adjusting for donor, and which GO biological processes are enriched among them?"},
  {key:"solubility",icon:'<path d="m8 2.5 4.5 2.6v5.3L8 13l-4.5-2.6V5.1z"/><path d="M8 5.5v5"/>',
    t:"Predict solubility from structure",d:"RDKit descriptors, scored on held-out molecules",
    q:"On the Delaney (ESOL) aqueous solubility dataset, does adding molecular weight, rotatable bonds and aromatic proportion to logP improve the prediction of log solubility on held-out molecules, and by how much?"},
  {key:"supernovae",icon:'<circle cx="8" cy="8" r="1.4"/><path d="M8 1.5v3M8 11.5v3M1.5 8h3M11.5 8h3M3.6 3.6l1.8 1.8M10.6 10.6l1.8 1.8M3.6 12.4l1.8-1.8M10.6 5.4l1.8-1.8"/>',
    t:"Test dark energy",d:"Fit cosmologies to Pantheon+ supernova distances",
    q:"Using the Pantheon+ Type Ia supernova distances, is the dark energy equation of state w consistent with −1 (a cosmological constant) in a flat wCDM fit, and does the answer hold when the low- and high-redshift halves are fitted separately?"},
  {key:"statistics",icon:'<path d="M6 2h4M6.6 2v4.4L2.9 12.7A1.2 1.2 0 0 0 3.9 14.5h8.2a1.2 1.2 0 0 0 1-1.8L9.4 6.4V2"/><path d="M4.6 10h6.8"/>',
    t:"Stress-test a statistical method",d:"Simulate where a textbook interval breaks down",
    q:"Does the classical 95% OLS confidence interval for a slope keep its coverage when the error variance grows with x, and do HC3 robust intervals restore it at sample sizes from 20 to 500?"}];
const EX_PAGE=3,REFRESH='<path d="M13 8a5 5 0 1 1-1.5-3.6"/><path d="M13 2.5v3h-3"/>';
const exCards=page=>EXAMPLES.slice(page*EX_PAGE,page*EX_PAGE+EX_PAGE).map((x,i)=>`<button class="ah-card" type="button" data-ex="${page*EX_PAGE+i}">${ico(x.icon,14)}<span class="ah-ct">${esc(x.t)}</span><span class="ah-cd">${esc(x.d)}</span></button>`).join("");

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
/* Linear's Agent composer: the editor, then a row with "+" (add a research thread as context) and
   a blue send button. The status line only shows while Plato is working. */
function composerHtml(id,{placeholder="Ask Plato…"}={}){
  return `<form class="composer" id="${id}" autocomplete="off"><div class="ctxrow" hidden></div>
    <textarea name="text" rows="1" maxlength="8000" placeholder="${esc(placeholder)}" aria-label="Message"></textarea>
    <div class="composer-f"><span class="hint trunc" aria-live="polite"></span>
      <div class="menu-w"><button class="cbtn" type="button" data-add aria-label="Add a research thread as context" title="Add a research thread as context" aria-haspopup="menu" aria-expanded="false">${ico(PLUS,16)}</button><div class="menu lm up" role="menu" hidden></div></div>
      <button class="send" type="submit" aria-label="Send" title="${esc(hintText())}">${ARROW_UP}</button></div></form>`}
const campById=id=>(S.campaigns||[]).find(c=>c.id===id)||{id,research_question:"",status:""};
/** The research thread a message carries as context, shown as a removable chip above the editor. */
function ctxRow(form,c){const row=form.querySelector(".ctxrow"),key=c?c.id:"";if(row.dataset.cid===key)return;row.dataset.cid=key;row.hidden=!c;
  row.innerHTML=c?`<span class="ctx" title="${esc(c.research_question)}">${ico(EYE,12)}<span class="trunc">${cid(c.id)}${c.research_question?" · "+esc(c.research_question):""}</span><button type="button" data-ctx-x aria-label="Remove this thread">${ico(XMARK,11)}</button></span>`:""}
/** opts.ctx: the context in effect (default: the thread picked with "+"); opts.dropCtx: remove one the
    page supplies. A picked thread rides on one message, then clears. */
function bindComposer(form,onSend,opts={}){const ta=form.text,btn=form.querySelector(".send"),add=form.querySelector("[data-add]"),menu=add.nextElementSibling;
  const ctx=opts.ctx||(()=>form.dataset.ctx?campById(form.dataset.ctx):null);
  const fit=()=>{ta.style.height="auto";ta.style.height=Math.min(ta.scrollHeight,288,innerHeight*.6)+"px";btn.disabled=!!form.dataset.busy};
  const showCtx=()=>ctxRow(form,ctx());
  form.fit=fit;form.showCtx=showCtx;ta.oninput=fit;
  ta.onkeydown=e=>{if(e.key!=="Enter"||e.isComposing)return;const mod=e.metaKey||e.ctrlKey;
    if(pref("send_with_mod_enter")?mod:(mod||!e.shiftKey)){e.preventDefault();form.requestSubmit()}};
  const fillMenu=()=>{const cs=(S.campaigns||[]).slice(0,8);
    menu.innerHTML=`<div class="mh">Add a research thread as context</div>`+(cs.length?cs.map(c=>`<button class="mi" type="button" role="menuitem" data-pick="${esc(c.id)}">${pico(campaignIcon(c.status))}<span class="trunc">${esc(c.research_question)}</span></button>`).join(""):`<div class="mi-e">No research threads yet</div>`)};
  form.onclick=e=>{if(e.target===form){ta.focus();return}   // the padding around the editor focuses it, as in Linear
    if(e.target.closest("[data-add]")){const open=menu.hidden;closeMenus();if(!open)return;fillMenu();menu.hidden=false;add.setAttribute("aria-expanded","true");loadList().then(()=>{if(!menu.hidden)fillMenu()});return}
    const pick=e.target.closest("[data-pick]");if(pick){form.dataset.ctx=pick.dataset.pick;closeMenus();showCtx();ta.focus();return}
    if(e.target.closest("[data-ctx-x]")){if(form.dataset.ctx)delete form.dataset.ctx;else opts.dropCtx?.();showCtx();ta.focus()}};
  form.onsubmit=async e=>{e.preventDefault();const text=ta.value.trim();if(!text||form.dataset.busy)return;
    const c=ctx();form.dataset.sending="1";ta.value="";fit();const ok=await onSend(text,c);delete form.dataset.sending;
    if(ok===false){if(!ta.value)ta.value=text}else{delete form.dataset.ctx;showCtx()}fit()};
  showCtx();fit()}
function setBusy(form,busy,label){if(!form)return;if(busy)form.dataset.busy="1";else delete form.dataset.busy;
  const h=form.querySelector(".hint");if(h)h.textContent=busy?label||"Plato is working…":"";form.fit?.()}

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
      h+=`<div class="msg me">${cidm?`<span class="ctxchip" title="Research thread sent as context">${ico(EYE,12)}<span class="mono">${cid(cidm[1])}</span></span>`:""}<div class="bubble">${esc(said)}</div></div>`;continue}
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
async function loadProjects(){if(!S.me?.account)return;try{S.projects=(await getJSON("projects")).projects;renderNav()}catch(e){if(S.projects==null)S.projects=[]}}

/* ---------- header: the chat title is a menu (Linear's "New chat ▾"): history, then actions ---------- */
function chatTitle(label){return `<div class="menu-w"><button class="chat-t" id="chatT" type="button" aria-haspopup="menu" aria-expanded="false"><span class="trunc">${esc(label)}</span>${ico(CHEV,12)}</button><div class="menu lm" id="chatM" role="menu" hidden></div></div>`}
function chatMenuHtml(P){const cur=P?.project.id;
  const rows=(S.projects||[]).slice(0,10).map(p=>`<a class="mi" role="menuitem" href="#/p/${eid(p.id)}"${p.id===cur?' aria-current="page"':""}>${pico(p.agent_status==="working"?SPIN:ico(CHAT))}<span class="trunc">${esc(p.title)}</span><span class="ago">${ago(p.updated_at)}</span></a>`).join("");
  return (P?`<a class="mi" role="menuitem" href="#/agent">${pico(ico(PLUS))}New chat</a><div class="msep"></div>`:"")+(rows||`<div class="mi-e">No history</div>`)+
    (P?`<div class="msep"></div><button class="mi" type="button" role="menuitem" data-pm="rename">Rename…</button><button class="mi danger" type="button" role="menuitem" data-pm="delete">Delete project…</button>`:"")}
function bindChatTitle(P){const b=$("#chatT"),m=$("#chatM");if(!b)return;
  b.onclick=()=>{const open=m.hidden;closeMenus();if(!open)return;m.innerHTML=chatMenuHtml(P);m.hidden=false;b.setAttribute("aria-expanded","true")};
  m.onclick=e=>{if(e.target.closest("a.mi")){closeMenus();return}const a=e.target.closest("[data-pm]")?.dataset.pm;if(!a)return;closeMenus();if(a==="rename")renameProject(P);else if(a==="delete")deleteProject(P)}}

/* ---------- agent home ---------- */
/* Linear's Agent empty state: a faded watermark the composer overlaps, an optional chip, then
   dismissible example cards, in a 712px column placed by the same grid rows. */
function renderAgentHome(){$("#crumb").innerHTML=chatTitle("New chat");bindChatTitle(null);$("#tabs").innerHTML="";$("#tabs").className="";$("#topActions").innerHTML="";S.lastView="";
  if($("#pane")?.dataset.view==="agent")return;   // keep a half-typed prompt
  const body=$("#body");body.className="body full";const ownKey=!!S.me.allowance?.own_key,exOff=ls.get("plato_examples_off")==="1";
  body.innerHTML=`<div class="pane" id="pane" data-view="agent"><div class="ah"><div class="ah-c">${WATERMARK}
    ${composerHtml("homeC")}
    ${ownKey?"":`<a class="ah-chip" href="#/settings/api-key">${ico(KEY,14)}Use your own API key</a>`}
    ${exOff?"":`<div class="ah-ex" id="ahEx"><div class="ah-exh"><span>Get started with some examples</span><span class="ah-exb"><button class="cbtn" type="button" data-ex-more aria-label="Show other examples" title="Show other examples">${ico(REFRESH,14)}</button><button class="cbtn" type="button" data-ex-x aria-label="Dismiss examples" title="Dismiss">${ico(XMARK,14)}</button></span></div>
      <div class="ah-cards" data-page="0">${exCards(0)}</div></div>`}
    </div></div></div>`;
  const f=$("#homeC");bindComposer(f,async(text,c)=>{setBusy(f,true,"Starting…");
    try{const r=await postJSON("projects",{text,...(c?{context:{campaign_id:c.id}}:{})});S.proj=null;location.hash=`#/p/${eid(r.id)}`;loadProjects();return true}
    catch(e){toast(e.message,true);return false}finally{setBusy(f,false)}});
  const ex=$("#ahEx");if(ex)ex.onclick=e=>{if(e.target.closest("[data-ex-x]")){ls.set("plato_examples_off","1");ex.remove();f.text.focus();return}
    if(e.target.closest("[data-ex-more]")){const c=ex.querySelector(".ah-cards"),n=(+c.dataset.page+1)%Math.ceil(EXAMPLES.length/EX_PAGE);c.dataset.page=n;c.innerHTML=exCards(n);return}
    const b=e.target.closest("[data-ex]");if(!b)return;f.text.value=EXAMPLES[+b.dataset.ex].q;f.fit();f.text.focus()};
  if(matchMedia("(pointer:fine)").matches)f.text.focus()}

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
    bindComposer($("#projC"),async(text,c)=>{const ok=await say(P,text,c?.id);renderProject(true);scheduleProject();return ok});
    $("#chatIn").onclick=async e=>{if(e.target.closest("[data-retry]")&&await retry(P)){renderProject(true);scheduleProject()}};
    if(P.loading){Kit.skeleton($("#chatIn"),chatHtml(SAMPLE_CHAT),"chat");Kit.skeleton($("#crumb"),chatTitle("Sample project title"),"crumb")}}
  if(!P.loading)renderProject(true);
  refreshProject()}
function renderProject(stick){const P=S.proj;if(!P||S.route.pid!==P.project.id||P.loading)return;const sc=$("#chatS"),near=stick||nearBottom(sc);
  if($("#chatM")?.hidden!==false){$("#crumb").innerHTML=chatTitle(P.project.title);bindChatTitle(P)}   // leave an open menu alone
  $("#topActions").innerHTML=`<button class="btn sm threads-btn" type="button" id="thBtn" aria-controls="props" aria-expanded="${$("#body").classList.contains("show-threads")}">Threads${P.threads.length?`<span class="t3">${P.threads.length}</span>`:""}</button>`;
  $("#thBtn").onclick=()=>{const on=$("#body").classList.toggle("show-threads");$("#thBtn").setAttribute("aria-expanded",String(on))};
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
/** A thread picked with "+" wins; otherwise the thread being viewed, unless the person removed it. */
function askCtx(){const f=S.ask.open&&$("#askC");if(f?.dataset.ctx)return campById(f.dataset.ctx);const c=S.route.view==="campaign"&&S.summary?.campaign;return c&&S.ask.ctxOff!==c.id?c:null}
function updateAskBtn(){const f=$("#askFab");if(f)f.hidden=!S.me?.account||S.ask.open||["agent","project"].includes(S.route.view)}
function openAsk(){if(!S.me?.account)return;S.ask.open=true;const el=$("#ask");el.hidden=false;document.body.classList.add("ask-open");
  el.innerHTML=`<div class="ask-h"><b>${ico(SPARK)}Ask Plato</b><button class="icon-btn" type="button" data-ask="open" title="Open as a project" aria-label="Open as a project">${ico('<path d="M9.5 2.5h4v4M13.5 2.5 8.5 7.5M7 3.5H4A1.5 1.5 0 0 0 2.5 5v7A1.5 1.5 0 0 0 4 13.5h7a1.5 1.5 0 0 0 1.5-1.5V9"/>')}</button>
    <button class="icon-btn" type="button" data-ask="new" title="New conversation" aria-label="New conversation">${ico('<path d="M8 3v10M3 8h10"/>')}</button><button class="icon-btn" type="button" data-ask="close" title="Close (Esc)" aria-label="Close">${ico('<path d="m4 4 8 8M12 4l-8 8"/>')}</button></div>
    <div class="chat"><div class="chat-s" id="askS"><div class="chat-in" id="askIn"></div></div><div class="chat-c">${composerHtml("askC",{placeholder:"Ask about your research…"})}</div></div>`;
  bindComposer($("#askC"),sendAsk,{ctx:askCtx,dropCtx:()=>{S.ask.ctxOff=askCtx()?.id}});
  el.onclick=e=>{const a=e.target.closest("[data-ask]")?.dataset.ask,P=S.ask.P;
    if(a==="close")closeAsk();
    else if(a==="new"){S.ask.P=null;ls.set(askKey(),"");renderAsk();$("#askC").text.focus()}
    else if(a==="open"){if(P?.project.id){location.hash=`#/p/${eid(P.project.id)}`}else toast("Ask something first")}
    else if(e.target.closest("[data-q]")){const f=$("#askC");f.text.value=e.target.closest("[data-q]").dataset.q;f.fit();f.requestSubmit()}
    else if(e.target.closest("[data-retry]")&&P)retry(P).then(ok=>{if(ok){renderAsk(true);scheduleAsk()}})};
  const pid=ls.get(askKey());
  if(pid&&S.ask.P?.project.id!==pid){S.ask.P={project:{id:pid,agent_status:"idle"},messages:[],threads:[],loading:true};refreshAsk()}
  renderAsk(true);updateAskBtn();$("#askC").text.focus()}
function closeAsk(silent){if(!S.ask)return;const was=S.ask.open;S.ask.open=false;clearTimeout(S.ask.timer);document.body.classList.remove("ask-open");const el=$("#ask");if(el){el.hidden=true;el.innerHTML=""}updateAskBtn();if(was&&!silent)$("#askBtn")?.focus()}
const toggleAsk=()=>S.ask.open?closeAsk():openAsk();
/** The thread being viewed rides along as context; follows navigation while the panel is open. */
function renderAskCtx(){const f=S.ask.open&&$("#askC");if(!f)return null;f.showCtx?.();return askCtx()}
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
async function sendAsk(text,c=askCtx()){let P=S.ask.P;
  if(!P){P=S.ask.P={project:{id:null,agent_status:"idle"},messages:[],threads:[],pending:text};renderAsk(true);
    try{const r=await postJSON("projects",{text,...(c?{context:{campaign_id:c.id}}:{})});P.project={id:r.id,agent_status:"working"};ls.set(askKey(),r.id);P.pending=null;await fetchInto(P).catch(()=>{});loadProjects()}
    catch(e){S.ask.P=null;toast(e.message,true);renderAsk();return false}
    renderAsk(true);scheduleAsk();return true}
  const pr=say(P,text,c?.id);renderAsk(true);const ok=await pr;renderAsk(true);scheduleAsk();return ok}
