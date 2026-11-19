/* Accounts: sign-in screens, preferences, and settings laid out like Linear's (back link,
   grouped rows, controls on the right). Loaded after app.js; defines functions only. */
"use strict";

/* ---------- session and preferences ---------- */
const PREF_DEFAULTS={home:"agent",theme:"system",reduce_motion:false,open_paper_while_writing:true,follow_live_writing:true,compact_grid:false,send_with_mod_enter:false};
const prefs=()=>S.me?.account?.preferences||{};
const pref=k=>prefs()[k]??PREF_DEFAULTS[k];
const MQ_DARK=matchMedia("(prefers-color-scheme: dark)");

function applyTheme(t=S.me?.account?pref("theme"):ls.get("plato_theme","system")){const r=t==="system"?(MQ_DARK.matches?"dark":"light"):t,changed=document.documentElement.dataset.theme!==r;
  document.documentElement.dataset.theme=r;ls.set("plato_theme",t);if(changed)themeChanged()}
function themeChanged(){$("#themeLbl")&&Kit.morph($("#themeLbl"),themeText());if(S.route.view==="campaign"&&S.summary){if(S.route.tab==="graph")renderTab();else mountCharts()}}
MQ_DARK.addEventListener("change",()=>{if(pref("theme")==="system")applyTheme()});
function applyPrefs(){if(!S.me?.account)return;applyTheme();const rm=pref("reduce_motion")?"reduce":"";document.documentElement.dataset.motion=rm;ls.set("plato_motion",rm);
  if(prefs().compact_grid!==undefined){S.res.dense=pref("compact_grid");ls.set("plato_grid_dense",S.res.dense?"1":"0")}}

async function savePref(k,v){const a=S.me?.account;if(!a)return;const before=a.preferences[k];a.preferences={...a.preferences,[k]:v};applyPrefs();
  try{await api("me",{method:"PATCH",headers:JSON_H,body:JSON.stringify({preferences:{[k]:v}})})}
  catch(e){a.preferences={...a.preferences,[k]:before};if(before===undefined)delete a.preferences[k];applyPrefs();toast(e.message,true);if(S.route.view==="settings")renderSettings()}}

const JSON_H={"content-type":"application/json"};
const postJSON=(p,body,method="POST")=>api(p,{method,headers:JSON_H,body:JSON.stringify(body)}).then(r=>r.json());

async function loadMe(){try{S.me=await getJSON("me");applyPrefs();renderAccountChip()}catch(e){S.me=null;if(e.status!==401)throw e}}
function renderAccountChip(){const a=S.me?.account,el=$("#acct");if(!el||!a)return;
  el.innerHTML=`${avatar(a,"sm")}<span class="trunc">${esc(a.name||a.email)}</span>${ico('<circle cx="8" cy="8" r="2.2"/><path d="M8 1.8v1.6M8 12.6v1.6M14.2 8h-1.6M3.4 8H1.8M12.4 3.6l-1.1 1.1M4.7 11.3l-1.1 1.1M12.4 12.4l-1.1-1.1M4.7 4.7 3.6 3.6"/>',13)}`;
  el.title=`${a.email} · Settings`}

/** The session ended (or never existed): drop everything account-scoped and show sign-in. */
function signedOut(){if(!S.me&&document.body.classList.contains("signed-out"))return;
  S.me=null;S.campaigns=null;S.projects=null;S.summary=null;S.proj=null;closeAsk(true);closeOverlay();
  clearTimeout(S.timer);clearTimeout(S.draftTimer);clearTimeout(S.projTimer);
  const h=location.hash;if(!/^#\/(login|signup)/.test(h)){S.next=h&&h!=="#/"?h:"";location.hash="#/login"}else route()}

async function logout(){try{await api("auth/logout",{method:"POST"})}catch{}signedOut()}

/* ---------- sign-in and sign-up ---------- */
function renderAuth(mode){document.body.classList.add("signed-out");const login=mode!=="signup";
  $("#auth").innerHTML=`<main class="auth"><div class="auth-c">
    <div class="logo lg" aria-hidden="true">P</div>
    <h1>${login?"Log in to Plato":"Create your account"}</h1>
    <p class="t2">${login?"Your autonomous research workspace.":"Ask the agent a question. It starts research threads that run on their own."}</p>
    <form id="authForm" novalidate>
      ${login?"":'<input class="field lg" name="name" autocomplete="name" placeholder="Full name" maxlength="80" aria-label="Full name">'}
      <input class="field lg" name="email" type="email" autocomplete="email" placeholder="Email address" required aria-label="Email address">
      <input class="field lg" name="password" type="password" autocomplete="${login?"current-password":"new-password"}" placeholder="${login?"Password":"Password (at least 10 characters)"}" required aria-label="Password">
      <p class="err" id="authErr" role="alert" hidden></p>
      <button class="btn primary lg" id="authBtn"><span data-lbl>${login?"Continue":"Create account"}</span></button>
    </form>
    <p class="auth-alt t2">${login?'No account yet? <a href="#/signup">Sign up</a>':'Already have an account? <a href="#/login">Log in</a>'}</p></div></main>`;
  const f=$("#authForm"),err=$("#authErr");(f.name||f.email).focus();
  f.onsubmit=async e=>{e.preventDefault();const b=$("#authBtn"),email=f.email.value.trim(),pw=f.password.value;
    const bad=!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)?"Enter a valid email address.":!login&&pw.length<10?"Use a password of at least 10 characters.":!pw?"Enter your password.":"";
    if(bad){err.textContent=bad;err.hidden=false;return}
    b.disabled=true;Kit.morph(b.querySelector("[data-lbl]"),login?"Logging in…":"Creating account…");err.hidden=true;
    try{await postJSON(login?"auth/login":"auth/signup",{email,password:pw,...(login?{}:{name:f.name.value.trim()})});
      await loadMe();document.body.classList.remove("signed-out");$("#auth").innerHTML="";const next=S.next||"#/";S.next="";
      if(location.hash===next)route();else location.hash=next;health();loadList();loadProjects()}
    catch(e2){b.disabled=false;Kit.morph(b.querySelector("[data-lbl]"),login?"Continue":"Create account");err.textContent=e2.message;err.hidden=false}}}

/* ---------- settings ---------- */
const SET_ACCOUNT=[["preferences","Preferences"],["profile","Profile"],["security","Security & access"],["api-key","API key"]];
const SET_ADMIN=[["members","Members"]];
const isAdmin=()=>!!S.me?.account?.is_admin;
const setRow=(label,desc,control,attrs="")=>`<div class="set-row"${attrs}><div class="set-l"><div class="set-t">${label}</div>${desc?`<div class="set-d">${desc}</div>`:""}</div><div class="set-c">${control}</div></div>`;
const setGroup=(title,rows,desc="")=>`<section class="set-s">${title?`<h2>${title}</h2>`:""}${desc?`<p class="set-sd">${desc}</p>`:""}<div class="set-g">${rows.join("")}</div></section>`;
const prefSwitch=k=>`<input type="checkbox" class="switch" role="switch" data-pref="${k}"${pref(k)?" checked":""} aria-label="${esc(k.replace(/_/g," "))}">`;
const prefSelect=(k,opts)=>`<select class="sel" data-pref="${k}" aria-label="${esc(k)}">${opts.map(([v,l])=>`<option value="${v}"${pref(k)===v?" selected":""}>${l}</option>`).join("")}</select>`;
const initials=a=>esc(((a?.name||a?.email||"?").trim()[0]||"?").toUpperCase());
const avatar=(a,cls="")=>`<span class="avatar ${cls}" aria-hidden="true">${initials(a)}</span>`;

function renderSettingsNav(){const cur=S.route.section,item=([k,l])=>`<a class="item${cur===k?" on":""}" href="#/settings/${k}"${cur===k?' aria-current="page"':""}>${l}</a>`;
  $("#nav").innerHTML=`<a class="item back" href="#/">${ico('<path d="M9.5 3.5 5 8l4.5 4.5"/>')}Back to app</a><div class="nav-l">Account</div>${SET_ACCOUNT.map(item).join("")}`+
    (isAdmin()?`<div class="nav-l">Administration</div>${SET_ADMIN.map(item).join("")}`:"")}

const SECTIONS={preferences:prefsView,profile:profileView,security:securityView,"api-key":keyView,members:membersView};
function renderSettings(){let sec=S.route.section;if(!SECTIONS[sec]||(sec==="members"&&!isAdmin())){location.replace("#/settings/preferences");return}
  const label=[...SET_ACCOUNT,...SET_ADMIN].find(x=>x[0]===sec)[1];
  $("#crumb").innerHTML=`<span>Settings</span><span class="t3">›</span><b>${esc(label)}</b>`;$("#tabs").innerHTML="";$("#tabs").className="";$("#topActions").innerHTML="";
  const body=$("#body");body.className="body full";S.lastView="";
  const sc=$("#pane")?.dataset.sec===sec?$("#pane").scrollTop:0;
  body.innerHTML=`<div class="pane" id="pane" data-sec="${sec}"><div class="set${sec==="members"?" wide":""}"><h1>${esc(label)}</h1>${SECTIONS[sec]()}</div></div>`;$("#pane").scrollTop=sc;
  bindSettings();if(sec==="security")loadSessions();if(sec==="members")loadMembers()}

function prefsView(){return setGroup("General",[
    setRow("Default home view","What you see when you open Plato.",prefSelect("home",[["agent","Agent"],["campaigns","Campaigns"]]))])+
  setGroup("Interface and theme",[
    setRow("Interface theme","Follow your system, or pick light or dark.",prefSelect("theme",[["system","System preference"],["light","Light"],["dark","Dark"]])),
    setRow("Reduce motion","Turn off animations, morphs and transitions.",prefSwitch("reduce_motion"))])+
  setGroup("Research",[
    setRow("Open the paper while it's written","Show the live paper beside a campaign once it starts writing.",prefSwitch("open_paper_while_writing")),
    setRow("Follow live writing","Keep the newest sentence in view while the paper streams in.",prefSwitch("follow_live_writing")),
    setRow("Compact results grid","Use denser rows in the results table.",prefSwitch("compact_grid"))])+
  setGroup("Agent",[
    setRow("Send with ⌘ Enter","When on, Enter adds a new line and ⌘ Enter (Ctrl Enter) sends.",prefSwitch("send_with_mod_enter"))])}

function profileView(){const a=S.me.account;return setGroup("",[
    setRow("Profile picture","Made from your name.",avatar(a,"xl")),
    setRow("Full name","",`<input class="field" id="nameIn" value="${esc(a.name)}" maxlength="80" placeholder="Your name" aria-label="Full name">`),
    setRow("Email","Used to log in. It can't be changed yet.",`<span class="t2">${esc(a.email)}</span>`),
    setRow("Member since","",`<span class="t2">${new Date(a.created_at).toLocaleDateString(undefined,{year:"numeric",month:"long",day:"numeric"})}</span>`)])}

function securityView(){return setGroup("Password",[setRow("Password","Changing it logs you out everywhere else.",'<button class="btn" type="button" data-act="password">Change password</button>')])+
  `<section class="set-s"><h2>Sessions</h2><p class="set-sd">Devices and browsers logged in to your account.</p><div class="set-g" id="sessions">${setRow('<span data-sk-line style="width:180px"></span>',"",'')}</div></section>`+
  setGroup("Workspace access",[isAdmin()?setRow("Role","Admins can manage members and see every campaign.",'<span class="chip">Admin</span>'):
    setRow("Admin token","Paste the admin token from the deploy to manage members and see every campaign.",
      '<form id="adminForm" style="display:flex;gap:8px"><input class="field" type="password" name="token" autocomplete="off" placeholder="Admin token" aria-label="Admin token" style="width:180px"><button class="btn">Verify</button></form>')])+
  setGroup("Account",[setRow("Log out","End this session on this device.",'<button class="btn" type="button" data-act="logout">Log out</button>'),
    setRow("Delete account","Deletes your account, projects and agent history. Research threads you started keep running.",'<button class="btn danger" type="button" data-act="delete">Delete account…</button>')])}

function uaLabel(ua){ua=ua||"";const b=/Edg\//.test(ua)?"Edge":/Firefox\//.test(ua)?"Firefox":/Chrome\//.test(ua)?"Chrome":/Safari\//.test(ua)?"Safari":/curl|node|python/i.test(ua)?"Script":"Browser";
  const o=/iPhone|iPad/.test(ua)?"iOS":/Android/.test(ua)?"Android":/Mac OS X/.test(ua)?"macOS":/Windows/.test(ua)?"Windows":/Linux/.test(ua)?"Linux":"";return o?`${b} on ${o}`:b}
async function loadSessions(){const el=$("#sessions");if(!el)return;try{const {sessions}=await getJSON("me/sessions");if(!$("#sessions"))return;
    const others=sessions.filter(s=>!s.current).length;
    $("#sessions").innerHTML=sessions.map(s=>setRow(esc(uaLabel(s.user_agent)),`Signed in ${ago(s.created_at)}`,s.current?'<span class="chip"><i style="background:var(--green)"></i>This device</span>':"")).join("")+
      (others?setRow("",`${others} other session${others>1?"s":""}`,'<button class="btn" type="button" data-act="revoke">Log out other sessions</button>'):"")}
  catch(e){if($("#sessions"))$("#sessions").innerHTML=setRow("Couldn't load sessions",esc(e.message),"")}}

// Tokens are counted at Claude Haiku 5.5 prices; say so when the project agent's model costs more.
function orchestratorNote(){const m=S.me.models,w=m?.weights?.[m?.orchestrator];
  return w>1?` Tokens are counted at ${esc(m.workers)} prices, so each ${esc(m.orchestrator)} token the project agent uses counts as ${w}.`:""}
function keyView(){const k=S.me.key,al=S.me.allowance||{};
  const keyRow=k?setRow("Your key",`sk-ant-…${esc(k.last4)} · added ${esc(when(k.created_at))}`,'<button class="btn" type="button" data-act="key-replace">Replace</button><button class="btn danger" type="button" data-act="key-remove">Remove</button>'):
    setRow("Add your key","Starts with sk-ant-. Create one in the Anthropic Console.",'<form id="keyForm" style="display:flex;gap:8px"><input class="field" type="password" name="key" autocomplete="off" spellcheck="false" placeholder="sk-ant-…" aria-label="Anthropic API key" style="width:200px"><button class="btn primary">Save key</button></form>');
  let usage;
  if(al.own_key)usage=setRow("Billing","Everything runs on your own key, so no allowance applies.",'<span class="chip"><i style="background:var(--green)"></i>Own key</span>');
  else if(al.cap==null)usage=setRow("Allowance","Admins aren't limited on the shared key.",'<span class="chip">Unlimited</span>');
  else{const f=al.cap?al.committed/al.cap:1,next=new Date();next.setUTCMonth(next.getUTCMonth()+1,1);
    usage=`<div class="set-row" style="display:block"><div style="display:flex;align-items:baseline;gap:8px"><span class="set-t">${short(al.committed)} of ${short(al.cap)} tokens</span><span class="t3" style="margin-left:auto;font-size:12px">Resets ${next.toLocaleDateString(undefined,{month:"short",day:"numeric"})}</span></div>
      <div class="meter${f>=1?" over":f>.8?" warn":""}"><span style="width:${Math.min(100,f*100).toFixed(1)}%"></span></div>
      <div class="set-d" style="margin-top:8px">Spent this month plus what running research threads have reserved. New threads must fit in what's left.${orchestratorNote()}</div></div>`}
  return setGroup("Anthropic API key",[keyRow],"Plato uses the workspace's shared Anthropic key by default, up to a monthly allowance. Add your own key to run the agent and your research threads on your Anthropic account instead. It's encrypted at rest and never shown again.")+
    setGroup("Usage this month",[usage])}

let MEMBERS=null;
function membersView(){return `<p class="set-sd" style="margin-top:-18px">Everyone with an account. The allowance caps what each person can spend on the shared key per month.</p><div class="mwrap" id="members">${membersTable(MEMBERS)}</div>`}
const CAP_OPTS=[[0,"Blocked"],[1e6,"1M"],[2e6,"2M"],[5e6,"5M"],[1e7,"10M"],[2.5e7,"25M"],[5e7,"50M"],[1e8,"100M"]];
function membersTable(m){if(!m)return `<table class="members"><tbody>${Array.from({length:3},()=>`<tr><td class="who"><span data-sk-line style="width:160px"></span></td><td><span data-sk-line style="width:60px"></span></td></tr>`).join("")}</tbody></table>`;
  const me=S.me.account.id;
  return `<table class="members"><thead><tr><th>Member</th><th>Role</th><th>Allowance</th><th>This month</th><th>Own key</th><th>Joined</th></tr></thead><tbody>${m.accounts.map(a=>{
    const capSel=`<select class="sel" data-cap="${a.id}" aria-label="Allowance for ${esc(a.email)}"><option value=""${a.monthly_token_cap==null?" selected":""}>Default (${short(m.default_cap)})</option>${CAP_OPTS.map(([v,l])=>`<option value="${v}"${a.monthly_token_cap!=null&&+a.monthly_token_cap===v?" selected":""}>${l}</option>`).join("")}${a.monthly_token_cap!=null&&!CAP_OPTS.some(([v])=>v===+a.monthly_token_cap)?`<option selected value="${a.monthly_token_cap}">${short(a.monthly_token_cap)}</option>`:""}</select>`;
    return `<tr><td class="who"><div style="display:flex;align-items:center;gap:10px">${avatar(a)}<div style="min-width:0"><div class="trunc">${esc(a.name||a.email.split("@")[0])}</div><div class="t3 trunc" style="font-size:12px">${esc(a.email)}</div></div></div></td>
      <td><select class="sel" data-role="${a.id}"${a.id===me?" disabled title=\"You can't change your own role\"":""} aria-label="Role for ${esc(a.email)}"><option value="member"${a.is_admin?"":" selected"}>Member</option><option value="admin"${a.is_admin?" selected":""}>Admin</option></select></td>
      <td>${a.is_admin?'<span class="t3">Unlimited</span>':capSel}</td><td class="mono" style="font-size:12px">${short(a.committed)}</td><td>${a.own_key?check("var(--green)"):'<span class="t3">–</span>'}</td><td class="t2">${ago(a.created_at)}</td></tr>`}).join("")}</tbody></table>`}
async function loadMembers(){try{MEMBERS=await getJSON("admin/accounts");const el=$("#members");if(el)el.innerHTML=membersTable(MEMBERS)}catch(e){const el=$("#members");if(el)el.innerHTML=`<p class="err" style="padding:12px">${esc(e.message)}</p>`}}

function bindSettings(){const pane=$("#pane");
  pane.onchange=async e=>{const t=e.target,d=t.dataset;
    if(d.pref){const v=t.type==="checkbox"?t.checked:t.value;if(d.pref==="compact_grid"){S.res.dense=v}await savePref(d.pref,v);if(d.pref==="home")toast(`Home is now ${v==="agent"?"the agent":"your campaigns"}`)}
    else if(d.role||d.cap!==undefined){const id=d.role||d.cap,body=d.role?{is_admin:t.value==="admin"}:{monthly_token_cap:t.value===""?null:+t.value};t.disabled=true;
      try{await postJSON("admin/accounts/"+id,body,"PATCH");toast("Member updated");await loadMembers()}catch(err){toast(err.message,true);await loadMembers()}}};
  const name=$("#nameIn");if(name){const save=async()=>{const v=name.value.trim();if(v===S.me.account.name)return;
      try{const r=await postJSON("me",{name:v},"PATCH");S.me.account.name=r.name;toast("Name updated");renderAccountChip()}catch(err){toast(err.message,true)}};
    name.onchange=save;name.onkeydown=e=>{if(e.key==="Enter")name.blur()}}
  const af=$("#adminForm");if(af)af.onsubmit=async e=>{e.preventDefault();const b=af.querySelector("button");b.disabled=true;
    try{await postJSON("me/admin",{token:af.token.value.trim()});await loadMe();toast("You're now a workspace admin");renderSettingsNav();renderSettings();loadList()}catch(err){b.disabled=false;toast(err.message,true)}};
  const kf=$("#keyForm");if(kf)kf.onsubmit=async e=>{e.preventDefault();const b=kf.querySelector("button"),key=kf.key.value.trim();if(!key)return;b.disabled=true;b.textContent="Checking…";
    try{const r=await postJSON("me/key",{key},"PUT");S.me.key=r.key;kf.key.value="";await loadMe();toast("Key saved. Plato now runs on your key.");renderSettings()}
    catch(err){b.disabled=false;b.textContent="Save key";toast(err.message,true)}};
  pane.onclick=async e=>{const t=e.target.closest("[data-act]");if(!t)return;const a=t.dataset.act;
    if(a==="logout")logout();
    else if(a==="password")passwordModal();
    else if(a==="delete")deleteModal();
    else if(a==="revoke"){t.disabled=true;try{const r=await api("me/sessions",{method:"DELETE"}).then(r=>r.json());toast(`Logged out ${r.revoked} other session${r.revoked===1?"":"s"}`);loadSessions()}catch(err){t.disabled=false;toast(err.message,true)}}
    else if(a==="key-remove"){if(!(await confirmModal("Remove your API key?","Plato goes back to the shared key and your monthly allowance. Research threads that run on your key pause until you add a key again.","Remove key",true)))return;
      try{await api("me/key",{method:"DELETE"});await loadMe();toast("Key removed");renderSettings()}catch(err){toast(err.message,true)}}
    else if(a==="key-replace"){S.me.key=null;renderSettings();$("#keyForm input")?.focus()}}}

/* ---------- modals ---------- */
function confirmModal(title,text,action,danger){return new Promise(res=>{let done=false;const fin=v=>{if(done)return;done=true;closeOverlay();res(v)};
  overlay(`<div class="modal" style="width:min(420px,100%)" role="alertdialog" aria-label="${esc(title)}"><div class="m-b" style="padding:18px 18px 6px"><div style="font-weight:500;font-size:14px;margin-bottom:6px">${esc(title)}</div><p class="t2" style="margin:0">${esc(text)}</p></div>
    <div class="m-f" style="border:0;justify-content:flex-end"><button class="btn" type="button" id="cfNo">Cancel</button><button class="btn ${danger?"danger":"primary"}" type="button" id="cfYes">${esc(action)}</button></div></div>`);
  $("#cfNo").onclick=()=>fin(false);$("#cfYes").onclick=()=>fin(true);$("#cfYes").focus();
  new MutationObserver((_,o)=>{if(!$("#cfYes")){o.disconnect();fin(false)}}).observe($("#overlay"),{childList:true})})}

function passwordModal(){overlay(`<form class="modal" id="pwForm" style="width:min(420px,100%)" role="dialog" aria-label="Change password"><div class="m-h" style="font-size:14px;color:var(--text);font-weight:500;padding-top:16px">Change password</div>
  <div class="m-b" style="display:flex;flex-direction:column;gap:10px"><input class="field" type="password" name="current" autocomplete="current-password" placeholder="Current password" aria-label="Current password" required>
  <input class="field" type="password" name="password" autocomplete="new-password" placeholder="New password (at least 10 characters)" aria-label="New password" required minlength="10"><p class="err" id="pwErr" hidden></p></div>
  <div class="m-f" style="justify-content:flex-end"><button class="btn" type="button" data-x>Cancel</button><button class="btn primary">Change password</button></div></form>`);
  const f=$("#pwForm");f.current.focus();f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector(".btn.primary"),err=$("#pwErr");
    if(f.password.value.length<10){err.textContent="Use a password of at least 10 characters.";err.hidden=false;return}b.disabled=true;
    try{await postJSON("me/password",{current:f.current.value,password:f.password.value});closeOverlay();toast("Password changed. Other sessions were logged out.");loadSessions()}
    catch(e2){b.disabled=false;err.textContent=e2.message;err.hidden=false}}}

function deleteModal(){overlay(`<form class="modal" id="delForm" style="width:min(440px,100%)" role="dialog" aria-label="Delete account"><div class="m-h" style="font-size:14px;color:var(--text);font-weight:500;padding-top:16px">Delete your account?</div>
  <div class="m-b"><p class="t2" style="margin:0 0 12px">This permanently deletes your account, your projects and the agent's history. Research threads you started keep running. This can't be undone.</p>
  <input class="field" type="password" name="password" autocomplete="current-password" placeholder="Enter your password to confirm" aria-label="Password" required><p class="err" id="delErr" hidden style="margin-top:8px"></p></div>
  <div class="m-f" style="justify-content:flex-end"><button class="btn" type="button" data-x>Cancel</button><button class="btn danger">Delete account</button></div></form>`);
  const f=$("#delForm");f.password.focus();f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector(".btn.danger"),err=$("#delErr");b.disabled=true;
    try{await api("me",{method:"DELETE",headers:JSON_H,body:JSON.stringify({password:f.password.value})});closeOverlay();ls.set(askKey(),"");signedOut()}
    catch(e2){b.disabled=false;err.textContent=e2.message;err.hidden=false}}}
