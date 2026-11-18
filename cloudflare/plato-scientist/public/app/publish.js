/* Publishing and connected services: the campaign Publish tab (journal-formatted packages,
   send to a drive, email), the Files library and Connected services settings, and the
   library picker in the new-campaign dialog. Loaded between app.js and account.js (whose
   settings table names these views); defines functions and module state only. */
"use strict";

const PUB={cid:null,journals:null,exports:null,err:"",journal:ls.get("plato_journal","nature"),building:false,open:new Set()};
const INT={data:null,err:"",loading:false};
let LIB=null;
const bytes=n=>{n=Number(n||0);return n>=2**20?(n/2**20).toFixed(1)+" MB":n>=1024?Math.round(n/1024)+" KB":n+" B"};
const ICO_DL='<path d="M8 2.5v8M4.5 7.5 8 11l3.5-3.5M3 13.5h10"/>';
const ICO_UP='<path d="M8 11.5v-8M4.5 6.5 8 3l3.5 3.5M3 13.5h10"/>';

/* ---------- campaign: Publish tab ---------- */
function publishView(){const c=S.summary.campaign;
  if(c.status!=="completed")return emptyPane("Publish once the paper is finished","Submission packages for Nature, Science, Cell, NEJM, arXiv and other venues are built from the finished paper, its figures and its data.");
  if(PUB.cid!==c.id)Object.assign(PUB,{cid:c.id,exports:null,err:"",building:false,open:new Set()});
  if(!PUB.journals||!PUB.exports){loadPublish();return `<div class="pub">${pubSkeleton()}</div>`}
  const j=PUB.journals.find(x=>x.key===PUB.journal)||PUB.journals[0];
  const lim=j.limits||{},facts=[lim.title_chars&&`Title ≤ ${lim.title_chars} characters`,lim.abstract_words&&`Abstract ≤ ${fmt(lim.abstract_words)} words`,
    lim.main_text_words&&`Main text ≤ ${fmt(lim.main_text_words)} words`,lim.references&&`≤ ${lim.references} references`,lim.display_items&&`≤ ${lim.display_items} display items`].filter(Boolean);
  return `<div class="pub">
  <section class="pub-build">
    <div class="pub-row"><label class="t2" for="pubJournal">Format for</label>
      <select class="sel" id="pubJournal">${PUB.journals.map(x=>`<option value="${esc(x.key)}"${x.key===j.key?" selected":""}>${esc(x.name)}</option>`).join("")}</select>
      <button class="btn primary" type="button" id="pubBuild"${PUB.building?" disabled":""}><span data-lbl>${PUB.building?"Building…":"Build package"}</span></button></div>
    <p class="t2 pub-note">${esc(j.publisher)} · ${esc(j.article_type)}. ${esc(j.template_note||"")} <a href="${esc(j.source)}" target="_blank" rel="noopener noreferrer">Author guidelines</a></p>
    ${facts.length?`<div class="gchips">${facts.map(f=>`<span class="chip">${esc(f)}</span>`).join("")}</div>`:""}
    <p class="t3 pub-note">Each package has the manuscript as PDF, LaTeX, Word and JATS XML, the references (BibTeX, RIS, CSL JSON), figures, the supplementary information, data as CSV and Excel, experiment code and logs, and a submission checklist.</p>
    ${PUB.err?`<p class="err">${esc(PUB.err)}</p>`:""}
  </section>
  <h3 class="pub-h">Packages</h3>
  ${PUB.exports.length?PUB.exports.map(exportCard).join(""):`<p class="t2">No packages yet. Pick a venue and build one; it takes about a minute.</p>`}
  </div>`}

function pubSkeleton(){return `<section class="pub-build"><div class="pub-row"><span data-sk-line style="width:70px"></span><span data-sk-line style="width:180px"></span><span data-sk-line style="width:110px"></span></div>
  <p><span data-sk-line style="width:80%"></span></p></section>`+Array.from({length:2},()=>`<div class="pub-card"><span data-sk-line style="width:50%"></span></div>`).join("")}

const CHECK_ICON={pass:()=>check("var(--green)"),warn:()=>ring("var(--yellow)",.5),fail:()=>cross("var(--red)"),info:()=>ring("var(--text-3)")};
function exportCard(x){const s=obj(x.summary),checks=Array.isArray(s.checks)?s.checks:[],j=PUB.journals.find(y=>y.key===x.journal),open=PUB.open.has(x.id);
  const n=k=>checks.filter(c=>c.status===k).length,ready=x.status==="ready";
  const hasPdf=(s.files||[]).some(f=>f.path==="manuscript/manuscript.pdf");
  const file=p=>`/api/exports/${eid(x.id)}/file?path=${encodeURIComponent(p)}`;
  return `<div class="pub-card" data-export="${esc(x.id)}">
    <div class="pub-row">${ready?check("var(--green)"):cross("var(--red)")}<b class="trunc">${esc(j?.name||x.journal)}</b>
      <span class="t3">${esc(when(x.created_at))}${x.bytes?" · "+bytes(x.bytes):""}${s.pages?` · ${s.pages} page${s.pages>1?"s":""}`:""}</span>
      ${ready?`<span class="pub-checks" title="Submission checks">${n("pass")} passed${n("warn")?` · ${n("warn")} to review`:""}${n("fail")?` · ${n("fail")} to fix`:""}</span>`:""}</div>
    ${ready?`<div class="pub-row pub-acts">
      <a class="btn primary sm" href="/api/exports/${eid(x.id)}/download" download>${ico(ICO_DL,13)}Download .zip</a>
      ${hasPdf?`<a class="btn sm" href="${file("manuscript/manuscript.pdf")}" target="_blank" rel="noopener">Preview PDF</a>`:""}
      <a class="btn sm" href="${file("SUBMISSION_CHECKLIST.md")}" target="_blank" rel="noopener">Checklist</a>
      <button class="btn sm" type="button" data-pact="send">Send to…</button>
      <button class="btn sm" type="button" data-pact="email">Email…</button>
      <button class="btn sm" type="button" data-pact="library">Save to Files</button>
      <button class="btn ghost sm" type="button" data-pact="toggle" aria-expanded="${open}">${open?"Hide":"Show"} checks</button></div>
      ${open?`<ul class="pub-list">${checks.map(c=>`<li>${(CHECK_ICON[c.status]||CHECK_ICON.info)()}<span><b>${esc(c.label)}</b>${c.detail?` <span class="t2">${esc(c.detail)}</span>`:""}</span></li>`).join("")}</ul>`:""}`
      :`<p class="err">${esc(s.error||"The build failed.")}</p>`}
  </div>`}

async function loadPublish(){const id=PUB.cid;if(PUB.loading===id)return;PUB.loading=id;
  try{const [j,e]=await Promise.all([PUB.journals?{journals:PUB.journals}:getJSON("publish/journals"),getJSON(`campaigns/${eid(id)}/exports`)]);
    if(PUB.cid!==id)return;PUB.journals=j.journals;PUB.exports=e.exports;
    if(!PUB.journals.some(x=>x.key===PUB.journal))PUB.journal=PUB.journals[0].key}
  catch(err){if(PUB.cid!==id)return;PUB.journals=PUB.journals||[];PUB.exports=[];PUB.err=err.message}
  finally{if(PUB.loading===id)PUB.loading=null}
  if(S.route.view==="campaign"&&S.route.tab==="publish"&&S.route.id===id)renderTab()}

function bindPublish(){const pane=$("#pane");if(!pane||S.route.tab!=="publish")return;
  const sel=$("#pubJournal");if(sel)sel.onchange=()=>{PUB.journal=sel.value;ls.set("plato_journal",sel.value);renderTab()};
  const b=$("#pubBuild");if(b)b.onclick=buildExport;
  pane.addEventListener("click",async e=>{const t=e.target.closest("[data-pact]");if(!t)return;const id=t.closest("[data-export]").dataset.export,a=t.dataset.pact;
    if(a==="toggle"){PUB.open.has(id)?PUB.open.delete(id):PUB.open.add(id);renderTab()}
    else if(a==="send")sendModal(id);
    else if(a==="email")emailModal(id);
    else if(a==="library"){t.disabled=true;try{const r=await postJSON(`exports/${eid(id)}/library`,{});toast(r.duplicate?"Already in your files":`Saved ${r.name} to your files`);LIB=null}catch(err){toast(err.message,true)}finally{t.disabled=false}}})}

async function buildExport(){const id=PUB.cid,journal=PUB.journal;PUB.building=true;PUB.err="";renderTab();
  try{const r=await postJSON(`campaigns/${eid(id)}/exports`,{journal});if(PUB.cid!==id)return;
    PUB.exports=[r.export,...(PUB.exports||[]).filter(x=>x.id!==r.export.id)];
    if(r.export.status==="ready"){PUB.open.add(r.export.id);toast("Package ready")}else toast("The build failed",true)}
  catch(err){if(PUB.cid===id)PUB.err=err.message}
  finally{if(PUB.cid===id){PUB.building=false;if(S.route.tab==="publish")renderTab()}}}

/* Connected services for a send or an email, loaded once per dialog. */
async function connected(kind){const d=await getJSON("integrations");INT.data=d;
  return d.services.filter(s=>s[kind]&&s.status==="connected")}
const noService=kind=>`<p class="t2" style="margin:0">Connect ${kind==="files"?"Google Drive, Dropbox or OneDrive":"Gmail or Outlook"} first in <a href="#/settings/integrations" data-x>Connected services</a>.</p>`;

async function sendModal(id){overlay(`<form class="modal" id="sendForm" style="width:min(460px,100%)" role="dialog" aria-label="Send package"><div class="m-h" style="font-size:14px;color:var(--text);font-weight:500;padding-top:16px">Send to a connected service</div>
  <div class="m-b" id="sendBody"><span data-sk-line style="width:70%"></span></div>
  <div class="m-f" style="justify-content:flex-end"><button class="btn" type="button" data-x>Cancel</button><button class="btn primary" id="sendBtn" disabled><span data-lbl>Send</span></button></div></form>`);
  let svcs;try{svcs=await connected("files")}catch(err){$("#sendBody")&&($("#sendBody").innerHTML=`<p class="err">${esc(err.message)}</p>`);return}
  const f=$("#sendForm");if(!f)return;
  if(!svcs.length){$("#sendBody").innerHTML=noService("files");$("#sendBody a").onclick=closeOverlay;return}
  $("#sendBody").innerHTML=`<div style="display:flex;flex-direction:column;gap:10px">
    <label class="t2">Service <select class="sel" name="service" style="margin-left:6px">${svcs.map(s=>`<option value="${esc(s.slug)}">${esc(s.name)}</option>`).join("")}</select></label>
    <label class="t2" id="pathRow">Folder <input class="field" name="path" value="/Plato" maxlength="200" style="margin-left:6px;width:220px" aria-label="Folder"></label>
    <p class="t3" id="sendHint" style="margin:0"></p><p class="err" id="sendErr" hidden></p></div>`;
  const hint=()=>{const v=f.service.value;$("#pathRow").hidden=v==="googledrive";
    $("#sendHint").textContent=v==="googledrive"?"Creates a folder named after the package in My Drive with the manuscript, supplement, data workbook, checklist and the full .zip.":"Uploads the full package as one .zip into this folder."};
  f.service.onchange=hint;hint();$("#sendBtn").disabled=false;
  f.onsubmit=async e=>{e.preventDefault();const b=$("#sendBtn"),l=b.querySelector("[data-lbl]"),err=$("#sendErr");b.disabled=true;Kit.morph(l,"Sending…");err.hidden=true;
    const body={service:f.service.value,...(f.service.value!=="googledrive"?{path:f.path.value.trim()||"/Plato"}:{})};
    try{const r=await postJSON(`exports/${eid(id)}/send`,body);closeOverlay();
      toast(`Sent ${r.sent.length} file${r.sent.length===1?"":"s"} to ${svcs.find(s=>s.slug===r.service)?.name||r.service}${r.skipped.length?` (${r.skipped.length} too large, skipped)`:""}`)}
    catch(e2){b.disabled=false;Kit.morph(l,"Send");err.textContent=e2.message;err.hidden=false}}}

async function emailModal(id){overlay(`<form class="modal" id="mailForm" novalidate style="width:min(480px,100%)" role="dialog" aria-label="Email package"><div class="m-h" style="font-size:14px;color:var(--text);font-weight:500;padding-top:16px">Email the package</div>
  <div class="m-b" id="mailBody"><span data-sk-line style="width:70%"></span></div>
  <div class="m-f" style="justify-content:flex-end"><button class="btn" type="button" data-x>Cancel</button><button class="btn primary" id="mailBtn" disabled><span data-lbl>Send email</span></button></div></form>`);
  let svcs;try{svcs=await connected("email")}catch(err){$("#mailBody")&&($("#mailBody").innerHTML=`<p class="err">${esc(err.message)}</p>`);return}
  const f=$("#mailForm");if(!f)return;
  if(!svcs.length){$("#mailBody").innerHTML=noService("email");$("#mailBody a").onclick=closeOverlay;return}
  $("#mailBody").innerHTML=`<div style="display:flex;flex-direction:column;gap:10px">
    <label class="t2">Send from <select class="sel" name="service" style="margin-left:6px">${svcs.map(s=>`<option value="${esc(s.slug)}">${esc(s.name)}</option>`).join("")}</select></label>
    <input class="field" name="to" type="email" required maxlength="254" placeholder="Recipient email" aria-label="Recipient email" autocomplete="email">
    <input class="field" name="subject" maxlength="200" placeholder="Subject (optional)" aria-label="Subject">
    <textarea class="field" name="message" rows="4" maxlength="4000" placeholder="Message (optional)" aria-label="Message" style="height:auto;padding:8px 10px;resize:vertical"></textarea>
    <p class="t3" style="margin:0">The email has a download link valid for 7 days and the PDF attached when it is under 18 MB.</p><p class="err" id="mailErr" hidden></p></div>`;
  $("#mailBtn").disabled=false;f.to.focus();
  f.onsubmit=async e=>{e.preventDefault();const b=$("#mailBtn"),l=b.querySelector("[data-lbl]"),err=$("#mailErr"),to=f.to.value.trim();
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)){err.textContent="Enter one valid email address.";err.hidden=false;return}
    b.disabled=true;Kit.morph(l,"Sending…");err.hidden=true;
    try{const r=await postJSON(`exports/${eid(id)}/email`,{service:f.service.value,to,subject:f.subject.value.trim(),message:f.message.value});closeOverlay();toast(`Emailed to ${r.to}`)}
    catch(e2){b.disabled=false;Kit.morph(l,"Send email");err.textContent=e2.message;err.hidden=false}}}

/* ---------- settings: Connected services ---------- */
const STATUS_CHIP={connected:'<span class="chip"><i style="background:var(--green)"></i>Connected</span>',expired:'<span class="chip"><i style="background:var(--yellow)"></i>Sign-in expired</span>',
  pending:'<span class="chip"><i style="background:var(--text-3)"></i>Waiting for sign-in</span>',disconnected:""};
function integrationsView(){const d=INT.data;if(!d){loadIntegrations();return setGroup("",[setRow('<span data-sk-line style="width:160px"></span>',"","")])}
  if(INT.err)return `<p class="err">${esc(INT.err)}</p>`;
  if(!d.configured)return setGroup("",[setRow("Not available","Connected services aren't configured on this deployment yet.","")]);
  const svc=s=>setRow(esc(s.name),(s.files?"Import files and send packages.":"Email packages and import attachments.")+(s.trigger?` Automatic import: ${esc(s.trigger.label.toLowerCase())}.`:""),
    `${STATUS_CHIP[s.status]||""}${s.status==="connected"?`<button class="btn" type="button" data-iact="disconnect" data-svc="${esc(s.slug)}">Disconnect</button>`:
      `<button class="btn${s.status==="disconnected"?" primary":""}" type="button" data-iact="connect" data-svc="${esc(s.slug)}">${s.status==="disconnected"?"Connect":"Reconnect"}</button>`}`);
  const auto=d.services.filter(s=>s.trigger&&s.status==="connected");
  const trig=d.triggers.map(t=>setRow(esc(t.label),`${esc(d.services.find(s=>s.slug===t.toolkit)?.name||t.toolkit)} · added ${esc(ago(t.created_at))}. New files land in Files.`,
    `<button class="btn" type="button" data-iact="untrigger" data-id="${esc(t.id)}">Remove</button>`));
  return setGroup("Services",d.services.map(svc),"Sign-in happens on the service's own page. Plato never sees your password, and each connection is yours alone.")+
    setGroup("Automatic import",[...trig,...auto.map(s=>setRow(`Add: ${esc(s.trigger.label)}`,s.slug==="gmail"?"Attachments of matching emails are saved to Files.":"Files added to the folder are saved to Files.",
      `<button class="btn" type="button" data-iact="trigger" data-svc="${esc(s.slug)}">Add</button>`)),
      ...(trig.length||auto.length?[]:[setRow("Nothing set up","Connect Google Drive or Gmail to import new files automatically.","")])])}

async function loadIntegrations(){if(INT.loading)return;INT.loading=true;
  try{INT.data=await getJSON("integrations");INT.err=""}catch(err){INT.data={};INT.err=err.message}finally{INT.loading=false}
  if(S.route.view==="settings"&&S.route.section==="integrations")renderSettings()}

async function integrationAction(t){const a=t.dataset.iact,svc=t.dataset.svc;
  if(a==="connect"){t.disabled=true;try{const r=await postJSON("integrations/connect",{service:svc});location.assign(r.redirect_url)}catch(err){t.disabled=false;toast(err.message,true)}}
  else if(a==="disconnect"){const name=INT.data.services.find(s=>s.slug===svc)?.name||svc;
    if(!(await confirmModal(`Disconnect ${name}?`,"Automatic imports from it stop. Files already imported stay in Files.","Disconnect",true)))return;
    try{await postJSON("integrations/disconnect",{service:svc});toast(`${name} disconnected`)}catch(err){toast(err.message,true)}INT.data=null;renderSettings()}
  else if(a==="untrigger"){t.disabled=true;try{await api(`integrations/triggers/${eid(t.dataset.id)}`,{method:"DELETE"});toast("Automatic import removed")}catch(err){toast(err.message,true)}INT.data=null;renderSettings()}
  else if(a==="trigger"){if(svc==="gmail")gmailTriggerModal();else browseModal(svc,{folder:true})}}

function gmailTriggerModal(){overlay(`<form class="modal" id="gtForm" style="width:min(460px,100%)" role="dialog" aria-label="Import email attachments"><div class="m-h" style="font-size:14px;color:var(--text);font-weight:500;padding-top:16px">Import attachments from new emails</div>
  <div class="m-b"><p class="t2" style="margin:0 0 10px">Attachments of new emails that match this Gmail search are saved to Files.</p><input class="field" name="query" value="has:attachment" maxlength="200" aria-label="Gmail search" style="width:100%"><p class="err" id="gtErr" hidden></p></div>
  <div class="m-f" style="justify-content:flex-end"><button class="btn" type="button" data-x>Cancel</button><button class="btn primary">Add</button></div></form>`);
  const f=$("#gtForm");f.query.focus();f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector(".btn.primary");b.disabled=true;
    try{await postJSON("integrations/triggers",{service:"gmail",query:f.query.value.trim()});closeOverlay();toast("Automatic import added");INT.data=null;renderSettings()}
    catch(e2){b.disabled=false;$("#gtErr").textContent=e2.message;$("#gtErr").hidden=false}}}

/* Browse a connected service: pick files to import, or (folder mode) a Drive folder to watch. */
function browseModal(svc,opt={}){const name=INT.data?.services?.find(s=>s.slug===svc)?.name||svc,st={stack:[{id:"",name}],q:"",items:null,next:null,picked:new Map(),err:""};
  overlay(`<div class="modal wide" role="dialog" aria-label="Browse ${esc(name)}"><div class="m-h"><span id="brCrumb"></span>
    ${svc==="dropbox"?"":`<input class="field" id="brQ" placeholder="Search" aria-label="Search" style="margin-left:auto;width:200px">`}
    <button class="icon-btn" type="button" ${svc==="dropbox"?'style="margin-left:auto"':""} data-x aria-label="Close">✕</button></div>
    <div class="m-b" id="brBody" style="min-height:240px"></div>
    <div class="m-f"><span class="t3" id="brMsg" style="font-size:12px" aria-live="polite"></span><span style="margin-left:auto"></span><button class="btn" type="button" data-x>Cancel</button>
    <button class="btn primary" type="button" id="brGo" disabled>${opt.folder?"Watch this folder":"Import"}</button></div></div>`);
  const body=$("#brBody"),msg=$("#brMsg"),go_=$("#brGo");
  const crumb=()=>{$("#brCrumb").innerHTML=st.q?`Search: <b>${esc(st.q)}</b>`:st.stack.map((s,i)=>i<st.stack.length-1?`<a href="#" data-up="${i}">${esc(s.name)}</a>`:`<b>${esc(s.name)}</b>`).join(' <span class="t3">›</span> ')};
  const draw=()=>{if(!$("#brBody"))return;crumb();
    if(st.err){body.innerHTML=`<p class="err">${esc(st.err)}</p>`;return}
    if(!st.items){body.innerHTML=Array.from({length:6},()=>`<div class="br-row"><span data-sk-line style="width:${40+Math.random()*40|0}%"></span></div>`).join("");return}
    const rows=st.items.filter(i=>!opt.folder||i.folder);
    body.innerHTML=rows.length?rows.map(i=>{const nav=i.folder&&(svc!=="one_drive");const can=!i.folder&&!opt.folder;
      return `<label class="br-row${nav?" nav":""}" data-i="${esc(i.id)}">${can?`<input type="checkbox"${st.picked.has(i.id)?" checked":""} aria-label="${esc(i.name)}">`:`<span style="width:13px"></span>`}
        ${i.folder?ico('<path d="M1.8 4.2c0-.7.5-1.2 1.2-1.2h3l1.4 1.6H13c.7 0 1.2.5 1.2 1.2v6.2c0 .7-.5 1.2-1.2 1.2H3c-.7 0-1.2-.5-1.2-1.2z"/>'):evIcon("file")}
        <span class="trunc">${esc(i.name)}</span><span class="t3 br-meta">${i.folder?"":esc(i.kind)}${i.size!=null?" · "+bytes(i.size):""}</span></label>`}).join("")+
      (st.next?`<button class="btn ghost sm" type="button" id="brMore" style="margin-top:8px">Load more</button>`:""):`<p class="t2">${opt.folder?"No folders here.":"Nothing here."}</p>`;
    if(opt.folder){go_.disabled=st.stack.length<2&&!st.q;msg.textContent=st.stack.length>1?`New files in “${st.stack.at(-1).name}” will be imported.`:"Open the folder to watch."}
    else{go_.disabled=!st.picked.size;msg.textContent=st.picked.size?`${st.picked.size} selected`:"Pick up to 20 files."}};
  const load=async more=>{const cur=st.stack.at(-1),p=new URLSearchParams({service:svc});
    if(st.q)p.set("q",st.q);else if(cur.id)p.set("folder",cur.id);if(more&&st.next)p.set("cursor",st.next);
    if(!more)st.items=null;st.err="";draw();
    try{const r=await getJSON("integrations/files?"+p);st.items=more?[...st.items,...r.items]:r.items;st.next=r.next}catch(err){st.err=err.message}draw()};
  body.onclick=e=>{if(e.target.id==="brMore"){load(true);return}const row=e.target.closest("[data-i]");if(!row)return;const it=st.items.find(i=>i.id===row.dataset.i);if(!it)return;
    if(it.folder){e.preventDefault();if(svc==="one_drive")return;st.q="";if($("#brQ"))$("#brQ").value="";st.stack.push({id:svc==="dropbox"?it.path:it.id,name:it.name});load()}
    else if(e.target.type==="checkbox"){if(e.target.checked){if(st.picked.size>=20){e.target.checked=false;toast("Pick at most 20 files at a time",true);return}st.picked.set(it.id,it)}else st.picked.delete(it.id);draw()}};
  $("#brCrumb").onclick=e=>{const a=e.target.closest("[data-up]");if(!a)return;e.preventDefault();st.stack.length=+a.dataset.up+1;st.q="";load()};
  const q=$("#brQ");if(q){let tm;q.oninput=()=>{clearTimeout(tm);tm=setTimeout(()=>{st.q=q.value.trim();load()},350)}}
  go_.onclick=async()=>{go_.disabled=true;
    if(opt.folder){const cur=st.stack.at(-1);try{await postJSON("integrations/triggers",{service:svc,folder_id:cur.id,folder_name:cur.name});closeOverlay();toast("Automatic import added");INT.data=null;renderSettings()}
      catch(err){go_.disabled=false;toast(err.message,true)}return}
    msg.textContent=`Importing ${st.picked.size} file${st.picked.size>1?"s":""}…`;
    try{const r=await postJSON("integrations/import",{service:svc,files:[...st.picked.values()]});const bad=r.results.filter(x=>x.error),ok=r.results.length-bad.length;
      closeOverlay();LIB=null;if(S.route.section==="files")renderSettings();
      toast(bad.length?`Imported ${ok}; ${bad.length} failed: ${bad.map(x=>`${x.name} (${x.error})`).join("; ")}`.slice(0,300):`Imported ${ok} file${ok===1?"":"s"}`,!!bad.length&&!ok)}
    catch(err){go_.disabled=false;msg.textContent="";toast(err.message,true)}};
  load()}

/* ---------- settings: Files (the library) ---------- */
const KIND_LABEL={data:"Data",reference:"References",document:"Document",image:"Image",archive:"Archive",other:"Other"};
const SOURCE_LABEL={upload:"Uploaded",googledrive:"Google Drive",dropbox:"Dropbox",one_drive:"OneDrive",gmail:"Gmail",outlook:"Outlook",export:"Plato package"};
function filesView(){if(!LIB){loadLibrary();return setGroup("",[setRow('<span data-sk-line style="width:200px"></span>',"","")])}
  if(LIB.err)return `<p class="err">${esc(LIB.err)}</p>`;
  const svcs=(INT.data?.services||[]).filter(s=>s.files&&s.status==="connected");
  const head=setGroup("Add files",[setRow("Upload","Data (CSV, Excel, VCF, FASTA, Parquet, HDF5 and more), references (.bib, .ris, .nbib) and documents (PDF, Word). Up to 25 MB each.",
      `<label class="btn primary" style="cursor:pointer">${ico(ICO_UP,13)}<span>Upload files</span><input type="file" id="libUp" multiple hidden></label>`),
    ...svcs.map(s=>setRow(`Import from ${esc(s.name)}`,"Pick files from your account.",`<button class="btn" type="button" data-iact="browse" data-svc="${esc(s.slug)}">Browse</button>`)),
    ...(svcs.length?[]:[setRow("Import from a service",'Connect Google Drive, Dropbox or OneDrive in <a href="#/settings/integrations">Connected services</a>.',"")])]);
  const rows=LIB.files.map(f=>`<tr><td class="who"><div class="trunc" title="${esc(f.name)}">${esc(f.name)}</div></td><td>${esc(KIND_LABEL[f.kind]||f.kind)}</td><td class="mono" style="font-size:12px">${bytes(f.bytes)}</td>
    <td class="t2">${esc(SOURCE_LABEL[f.source]||f.source)}</td><td class="t2">${esc(ago(f.created_at))}</td>
    <td style="text-align:right;white-space:nowrap"><a class="btn ghost sm" href="/api/library/${eid(f.id)}" download aria-label="Download ${esc(f.name)}">${ico(ICO_DL,13)}</a><button class="btn ghost sm" type="button" data-lact="delete" data-id="${esc(f.id)}" aria-label="Delete ${esc(f.name)}">Delete</button></td></tr>`).join("");
  return head+`<section class="set-s"><h2>Your files</h2><p class="set-sd">Pick these when you start a research thread. Data files become datasets, references become citable papers, documents become background the agents read.</p>
    ${LIB.files.length?`<div class="mwrap"><table class="members"><thead><tr><th>Name</th><th>Kind</th><th>Size</th><th>From</th><th>Added</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`:setGroup("",[setRow("No files yet","Upload or import files to use them in research threads.","")])}</section>`}

async function loadLibrary(){if(LIB?.loading)return;LIB={loading:true,files:[]};
  try{const [l,i]=await Promise.all([getJSON("library"),INT.data?Promise.resolve(INT.data):getJSON("integrations").catch(()=>null)]);LIB={files:l.files,limits:l.limits};if(i)INT.data=i}
  catch(err){LIB={files:[],err:err.message}}
  if(S.route.view==="settings"&&S.route.section==="files")renderSettings()}

async function uploadLibrary(files){const max=25*2**20;let ok=0;
  for(const file of files){if(file.size>max){toast(`${file.name} is larger than 25 MB`,true);continue}
    try{await api("library",{method:"POST",headers:{"x-file-name":encodeURIComponent(file.name),"content-type":file.type||"application/octet-stream"},body:file});ok++}
    catch(err){toast(`${file.name}: ${err.message}`,true)}}
  if(ok)toast(`Uploaded ${ok} file${ok>1?"s":""}`);LIB=null;renderSettings()}

/* Hooked from bindSettings for the two new sections. */
function bindServiceSettings(){const pane=$("#pane"),sec=S.route.section;if(sec!=="integrations"&&sec!=="files")return;
  pane.addEventListener("click",async e=>{const t=e.target.closest("[data-iact],[data-lact]");if(!t)return;
    if(t.dataset.iact==="browse")browseModal(t.dataset.svc);
    else if(t.dataset.iact)integrationAction(t);
    else if(t.dataset.lact==="delete"){const f=LIB.files.find(x=>x.id===t.dataset.id);
      if(!(await confirmModal(`Delete ${f?.name||"this file"}?`,"It's removed from Files. Research threads that already used it keep their copy.","Delete",true)))return;
      try{await api(`library/${eid(t.dataset.id)}`,{method:"DELETE"});toast("File deleted")}catch(err){toast(err.message,true)}LIB=null;renderSettings()}});
  const up=$("#libUp");if(up)up.onchange=()=>{const fs=[...up.files];up.value="";if(fs.length)uploadLibrary(fs)}}

/* ---------- new campaign: pick files from the library ---------- */
const PICKABLE=new Set(["data","reference","document","image"]);
async function libraryPicker(el,picked){el.hidden=false;el.innerHTML=`<span data-sk-line style="width:60%"></span>`;
  try{const {files}=await getJSON("library");const ok=files.filter(f=>PICKABLE.has(f.kind));
    el.innerHTML=ok.length?ok.map(f=>`<label class="br-row"><input type="checkbox" value="${esc(f.id)}"${picked.has(f.id)?" checked":""}><span class="trunc">${esc(f.name)}</span><span class="t3 br-meta">${esc(KIND_LABEL[f.kind])} · ${bytes(f.bytes)}</span></label>`).join("")
      :`<p class="t2" style="margin:4px 0">No usable files yet. Add some in <a href="#/settings/files" data-x>Files</a>.</p>`;
    el.onchange=e=>{const t=e.target;if(t.type!=="checkbox")return;if(t.checked){if(picked.size>=16){t.checked=false;toast("Pick at most 16 files",true);return}picked.add(t.value)}else picked.delete(t.value);
      const lbl=$("#libLbl");if(lbl)lbl.textContent=picked.size?`${picked.size} file${picked.size>1?"s":""} from Files`:"Add from Files"};
    el.querySelectorAll("[data-x]").forEach(a=>a.onclick=closeOverlay)}
  catch(err){el.innerHTML=`<p class="err">${esc(err.message)}</p>`}}
