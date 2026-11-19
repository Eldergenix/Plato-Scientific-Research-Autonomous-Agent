/* Manuscript tab extras: the automated peer review as a resizable right panel, its claims
   marked in the paper, and the paper typeset as a PDF. Loaded after app.js; defines
   functions and module state only (app.js calls them from manuscriptView and renderTab). */
"use strict";

const RV_MIN=320,RV_MAX=760,RV_DEFAULT=420;
const RV={open:ls.get("plato_review_open","")?ls.get("plato_review_open")==="1":innerWidth>1100,
  w:Math.max(RV_MIN,Math.min(RV_MAX,+ls.get("plato_review_w",String(RV_DEFAULT))||RV_DEFAULT)),filter:"all",focus:null,ranges:new Map()};
const PDFV={cid:null,url:null,state:null,err:"",split:ls.get("plato_ms_split","0")==="1"};

const VERDICT={approved:["Approved","var(--green)"],needs_revision:["Needs revision","var(--orange)"],rejected:["Rejected","var(--red)"],removed:["Removed","var(--gray)"]};
const OUTCOME={resolved:["Resolved in the revision","var(--green)"],partially_resolved:["Partly resolved in the revision","var(--yellow)"],
  unresolved:["Not resolved by the revision","var(--red)"],removed:["Removed from the paper in the revision","var(--gray)"]};
const DECISION={accept:["Accept","var(--green)"],minor_revision:["Minor revision","var(--yellow)"],major_revision:["Major revision","var(--orange)"],reject:["Reject","var(--red)"]};
const SECTION={title:"Title",abstract:"Abstract",introduction:"Introduction",methods:"Methods",results:"Results",discussion:"Discussion",limitations:"Limitations"};
const cap=s=>{s=String(s||"").replace(/_/g," ");return s.charAt(0).toUpperCase()+s.slice(1)};
const decision=d=>DECISION[d]||[cap(d||"No decision"),"var(--gray)"];

/* ---------- data ---------- */
function reviewData(m){if(!m||typeof m!=="object")return null;
  const r=pj(m.peer_review),panel=pj(m.review_panel),mx=pj(m.evidence_matrix),cr=pj(m.citation_report);
  return r||panel||mx||cr?{r,panel,mx,cr,claims:Array.isArray(r?.assessments)?r.assessments:[]}:null}
// Where a claim stands in the paper as published: the revision check decides when it ran.
function finalState(a){const o=a.outcome?.status;
  if(!o)return VERDICT[a.verdict]?a.verdict:"needs_revision";
  return o==="resolved"?"approved":o==="partially_resolved"?"needs_revision":o==="removed"?"removed":a.verdict==="approved"?"approved":a.verdict}
// The words to find in the final paper: the revision's quote, else the reviewed one.
const finalQuote=a=>a.outcome?(a.outcome.status==="removed"?"":a.outcome.final_quote||""):a.quote||"";
// What the reviewer said of each claim (the cards and filters); finalState is the paper as published.
function reviewStats(d){const n={approved:0,needs_revision:0,rejected:0};d.claims.forEach(a=>{if(n[a.verdict]!=null)n[a.verdict]++});return n}

/* A claim's LaTeX shown as text: maths through KaTeX, citations and commands dropped. */
function inlineTex(src){const parts=String(src||"").replace(/\\cite[pt]?\{[^}]*\}/g,"").split(/(\$[^$]+\$)/g);
  return parts.map(p=>/^\$[^$]+\$$/.test(p)?renderMath(p.slice(1,-1),false)
    :esc(p.replace(/\\(textbf|emph|textit|texttt|text|mathrm)\{([^}]*)\}/g,"$2").replace(/\\([%_#$&])/g,"$1").replace(/\\[a-zA-Z]+\*?/g,"").replace(/[{}~]/g,m=>m==="~"?" ":"")))
    .join("").replace(/\s+([.,;:])/g,"$1").replace(/\s{2,}/g," ").trim()}

/* ---------- panel ---------- */
const pipsOf=v=>{v=Number(v);v=Number.isFinite(v)?Math.max(0,Math.min(4,v)):0;return `<span class="pips" aria-label="${v} of 4">${[1,2,3,4].map(i=>`<i class="${i<=v?"on":""}"></i>`).join("")}</span>`};
const decChip=(d,big)=>{const [l,c]=decision(d);return `<span class="dec${big?" big":""}" style="--c:${c}"><i></i>${esc(l)}</span>`};
const xIco=ico('<path d="M4 4l8 8M12 4l-8 8"/>');

function reviewPanel(d){const r=d.r;
  return `<aside class="rv" id="review" aria-label="Automated peer review"${RV.open?"":" hidden"}>
    <div class="rv-grip" role="separator" aria-orientation="vertical" aria-controls="review" aria-label="Resize the review panel" tabindex="0"
      aria-valuemin="${RV_MIN}" aria-valuemax="${RV_MAX}" aria-valuenow="${RV.w}" title="Drag to resize · double-click to reset"></div>
    <div class="rv-head"><b>Automated peer review</b>
      <button class="icon-btn" type="button" data-rv-close aria-label="Close the review panel" title="Close">${xIco}</button></div>
    <div class="rv-body" id="rvBody">${r?verdictHtml(r):""}${d.claims.length?claimsHtml(d):""}${r?listsHtml(r,d):""}${panelHtml(d.panel,!d.claims.length)}${citationsHtml(d.mx,d.cr)}</div>
  </aside>`}

function verdictHtml(r){const rev=r.revision;
  const first=rev&&rev.decision!==r.decision?`<span class="t3">First review: ${esc(decision(r.decision)[0])}</span>`:"";
  return `<section class="rv-sec rv-verdict">
    <div class="rv-dec">${decChip(rev?.decision||r.decision,true)}<span class="t2">${rev?"On the revised paper":"On the paper as written"}</span>${first}</div>
    <div class="scores"><span class="score">Soundness ${pipsOf(r.soundness)}</span><span class="score">Presentation ${pipsOf(r.presentation)}</span><span class="score">Contribution ${pipsOf(r.contribution)}</span></div>
    <p class="rv-sum">${esc(rev?.summary||r.summary)}</p>
    ${rev&&r.summary?`<details class="rv-more"><summary>First-round summary</summary><p>${esc(r.summary)}</p></details>`:""}</section>`}

function claimsHtml(d){const n=reviewStats(d),total=d.claims.length,shown=d.claims.filter(a=>RV.filter==="all"||a.verdict===RV.filter);
  const keys=["rejected","needs_revision","approved"].filter(k=>n[k]),rc=d.r.revision?.counts;
  const after=rc?["resolved","partially_resolved","unresolved","removed"].filter(k=>rc[k]).map(k=>`${rc[k]} ${{resolved:"resolved",partially_resolved:"partly resolved",unresolved:"unresolved",removed:"removed"}[k]}`):[];
  return `<section class="rv-sec"><h4>Claims checked <span class="c">${total}</span></h4>
    <div class="rv-tally" role="img" aria-label="${keys.map(k=>`${n[k]} ${VERDICT[k][0].toLowerCase()}`).join(", ")}">${keys.map(k=>`<i style="flex:${n[k]};background:${VERDICT[k][1]}"></i>`).join("")}</div>
    <p class="rv-note t2">${keys.map(k=>`<span><i style="background:${VERDICT[k][1]}"></i>${n[k]} ${esc(VERDICT[k][0].toLowerCase())}</span>`).join("")}</p>
    ${after.length?`<p class="rv-note t3">After the revision: ${esc(after.join(" · "))}</p>`:""}
    <div class="seg rv-filter" role="group" aria-label="Show claims">${[["all","All",total],...keys.map(k=>[k,VERDICT[k][0],n[k]])].map(([k,l,c])=>
      `<button type="button" data-rv-filter="${k}" aria-pressed="${RV.filter===k}" class="${RV.filter===k?"on":""}">${esc(l)} <span class="c">${c}</span></button>`).join("")}</div>
    <ol class="rv-list" id="rvList">${shown.map(claimHtml).join("")||`<li class="t3 rv-none">No claims in this group.</li>`}</ol></section>`}

function claimHtml(a){const st=finalState(a),[vl,vc]=VERDICT[a.verdict]||VERDICT.needs_revision,o=a.outcome,q=finalQuote(a);
  const meta=[a.severity&&a.verdict!=="approved"?cap(a.severity):"",a.category&&a.category!=="result"?cap(a.category):"",SECTION[a.section]||cap(a.section)].filter(Boolean);
  return `<li class="rv-claim" data-a="${Number(a.id)}" style="--c:${VERDICT[st][1]}">
    <div class="rv-top"><span class="chip"><i style="background:${vc}"></i>${esc(vl)}</span><span class="t3">${esc(meta.join(" · "))}</span></div>
    ${q?`<button type="button" class="rv-quote" data-rv-jump="${Number(a.id)}" title="Show in the paper">${inlineTex(q)}</button>`:`<blockquote class="rv-quote gone">${inlineTex(a.quote)}</blockquote>`}
    <dl class="rv-dl">${a.evidence?`<dt>Evidence</dt><dd>${esc(a.evidence)}</dd>`:""}${a.critique?`<dt>Critique</dt><dd>${esc(a.critique)}</dd>`:""}${a.fix?`<dt>Fix</dt><dd>${esc(a.fix)}</dd>`:""}</dl>
    ${o?`<div class="rv-out" style="--c:${(OUTCOME[o.status]||OUTCOME.unresolved)[1]}"><i></i><span><b>${esc((OUTCOME[o.status]||[cap(o.status)])[0])}.</b> ${esc(o.note||"")}</span></div>`:""}</li>`}

function listsHtml(r,d){const out=[];
  if(r.strengths?.length)out.push(`<section class="rv-sec"><h4>Strengths</h4><ul class="rv-ul">${r.strengths.map(s=>`<li>${esc(s)}</li>`).join("")}</ul></section>`);
  if(r.required_changes?.length)out.push(`<section class="rv-sec"><h4>Required changes</h4><ol class="rv-ul">${r.required_changes.map(s=>`<li>${esc(s)}</li>`).join("")}</ol>
    ${!d.claims.length?`<p class="t3 rv-note">Reviews written before claim-by-claim verdicts list required changes only.</p>`:""}</section>`);
  return out.join("")}

function panelHtml(panel,open){if(!panel)return"";const rows=Object.entries(panel.reviewers||{});
  return `<section class="rv-sec"><details class="rv-fold"${open?" open":""}><summary><h4>Reviewer panel <span class="c">${panel.completed??rows.length} of ${rows.length}</span></h4></summary>
    ${rows.map(([angle,x])=>`<div class="rv-rev"><div class="rv-top"><b>${esc(cap(angle))}</b>${x.error?`<span class="t3">unavailable</span>`:`<span class="chip"><i style="background:${sevColor(x.severity)}"></i>Severity ${Number(x.severity)}/5</span>`}</div>
      ${x.error?"":`<p class="t2">${esc(x.summary||"")}</p>${x.issues?.length?`<ul class="rv-ul">${x.issues.map(i=>`<li><span class="t3">${esc(SECTION[String(i.section).toLowerCase()]||i.section)}</span> ${esc(i.issue)}${i.fix?` <span class="t2">Fix: ${esc(i.fix)}</span>`:""}</li>`).join("")}</ul>`:""}`}</div>`).join("")}
  </details></section>`}

function citationsHtml(mx,cr){if(!mx&&!cr)return"";const cl=mx?.claims||[],cs=cr?.cited||[],ex=cr?.excluded||[];
  const color=v=>v==="supported"?"var(--green)":v==="refuted"?"var(--red)":"var(--orange)";
  const ok=cs.filter(c=>c.status==="verified").length,sup=cl.filter(c=>c.verdict==="supported").length;
  return `<section class="rv-sec"><details class="rv-fold"><summary><h4>Citations <span class="c">${cl.length?`${sup} of ${cl.length} supported`:""}${cl.length&&cs.length?" · ":""}${cs.length?`${ok} of ${cs.length} verified`:""}</span></h4></summary>
    ${cl.length?`<ul class="rv-cites">${cl.map(c=>`<li><div class="rv-top"><span class="chip"><i style="background:${color(c.verdict)}"></i>${esc(cap(c.verdict))}</span><span class="t3">${esc(SECTION[c.section]||"")}</span></div>
      <button type="button" class="rv-quote" data-rv-text="${esc(c.text)}" title="Show in the paper">${esc(c.text)}</button>
      ${(c.citations||[]).filter(x=>x.quote).map(x=>`<blockquote>“${esc(x.quote)}” <span class="t3">${esc(x.title)}</span></blockquote>`).join("")}</li>`).join("")}</ul>`:""}
    ${cs.length||ex.length?`<ul class="rv-ul">${cs.map(c=>`<li>${esc(c.title)} <span class="t3">${esc(c.status)}${c.retracted?" · retracted":""}${c.issues?.length?" · "+esc(c.issues.join(", ")):""}</span></li>`).join("")}${ex.map(x=>`<li>Excluded: ${esc(x.title)} <span class="t3">${esc(x.reason)}</span></li>`).join("")}</ul>`:""}
    ${cr?.sources_searched?.length?`<p class="t3 rv-note">Searched ${esc(cr.sources_searched.join(", "))}</p>`:""}
  </details></section>`}

/* The review on the live paper card (Overview): one line, the full review lives in the panel. */
function reviewStrip(m){const d=reviewData(m);if(!d?.r)return"";const r=d.r,n=reviewStats(d);
  const parts=d.claims.length?["approved","needs_revision","rejected"].filter(k=>n[k]).map(k=>`${n[k]} ${VERDICT[k][0].toLowerCase()}`):[];
  return `<div class="rv-strip"><b>Peer review</b>${decChip(r.revision?.decision||r.decision)}${parts.length?`<span class="t2">${esc(parts.join(" · "))}</span>`:""}
    <button class="btn ghost sm" type="button" data-open-ms data-rv-open>Open review</button></div>`}

/* ---------- open, close, resize ---------- */
function rvMax(){const b=$("#body");return Math.max(RV_MIN,Math.min(RV_MAX,(b?.clientWidth||1200)-360))}
function setRvW(w,save){RV.w=Math.round(Math.max(RV_MIN,Math.min(rvMax(),w)));const b=$("#body");if(b)b.style.setProperty("--rv-w",RV.w+"px");
  $(".rv-grip")?.setAttribute("aria-valuenow",String(RV.w));if(save)ls.set("plato_review_w",String(RV.w))}
function setRvOpen(open,focus=true){if(RV.open===open)return;RV.open=open;ls.set("plato_review_open",open?"1":"0");
  const body=$("#body"),aside=$("#review");if(!aside)return;
  Kit.transition(()=>{aside.hidden=!open;body.classList.toggle("rv-open",open);
    document.querySelectorAll("[data-rv-toggle]").forEach(b=>{b.setAttribute("aria-expanded",String(open));b.classList.toggle("on",open)})});
  if(open){markClaims();if(focus)aside.querySelector("[data-rv-close]")?.focus({preventScroll:true})}
  else{clearMarks();if(focus)$("[data-rv-toggle]")?.focus({preventScroll:true})}}

function bindReview(){const body=$("#body"),aside=$("#review"),pane=$("#pane");if(!body)return;
  body.style.setProperty("--rv-w",RV.w+"px");
  if(pane)pane.addEventListener("click",onPaperClick);
  if(!aside)return;
  if(RV.w>rvMax())setRvW(RV.w,false);
  const grip=aside.querySelector(".rv-grip");
  grip.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();grip.setPointerCapture(e.pointerId);body.classList.add("rv-drag");
    const right=body.getBoundingClientRect().right;
    grip.onpointermove=ev=>setRvW(right-ev.clientX,false);
    grip.onpointerup=grip.onpointercancel=()=>{grip.onpointermove=grip.onpointerup=grip.onpointercancel=null;body.classList.remove("rv-drag");ls.set("plato_review_w",String(RV.w))}};
  grip.onkeydown=e=>{const step=e.shiftKey?64:16,k=e.key;
    if(k==="ArrowLeft"||k==="ArrowRight"||k==="Home"||k==="End"){e.preventDefault();setRvW(k==="Home"?RV_MAX:k==="End"?RV_MIN:RV.w+(k==="ArrowLeft"?step:-step),true)}
    else if(k==="Enter"){e.preventDefault();setRvW(RV_DEFAULT,true)}};
  grip.ondblclick=()=>setRvW(RV_DEFAULT,true);
  aside.onclick=e=>{const t=e.target.closest("[data-rv-close],[data-rv-filter],[data-rv-jump],[data-rv-text]");if(!t||!aside.contains(t))return;
    if(t.dataset.rvClose!=null)setRvOpen(false);
    else if(t.dataset.rvFilter){RV.filter=t.dataset.rvFilter;const d=reviewData(S.manuscript),sec=t.closest(".rv-sec");
      if(d&&sec){sec.outerHTML=claimsHtml(d);Kit.paint($("#rvBody"))}$(`[data-rv-filter="${RV.filter}"]`)?.focus({preventScroll:true})}
    else if(t.dataset.rvJump!=null)jumpToClaim(+t.dataset.rvJump);
    else jumpToText(t.dataset.rvText)};
  aside.onkeydown=e=>{if(e.key==="Escape"&&!$("#overlay .scrim")){e.stopPropagation();setRvOpen(false)}};
  if(RV.open)markClaims()}

/* ---------- claims in the paper: located by their words, marked with the Highlight API ---------- */
const HL=typeof CSS!=="undefined"&&CSS.highlights&&typeof Highlight==="function";
const words=t=>(String(t).toLowerCase().match(/[\p{L}\p{N}]+/gu)||[]);
function quoteWords(q){return words(String(q||"").replace(/\\cite[pt]?\{[^}]*\}/g," ").replace(/\$[^$]*\$/g," ").replace(/\\\([\s\S]*?\\\)/g," ")
  .replace(/\\[a-zA-Z]+\*?\{([^}]*)\}/g," $1 ").replace(/\\[a-zA-Z]+\*?/g," "))}
// Every word of the rendered paper with its text node and offsets (maths and citation
// markers are skipped, as they are stripped from the quotes).
function paperIndex(root){const out=[];
  const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest(".katex,cite,.ms-bar,pre")?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
  for(let n;(n=walk.nextNode());){const re=/[\p{L}\p{N}]+/gu;let m;while((m=re.exec(n.data)))out.push({w:m[0].toLowerCase(),n,s:m.index,e:m.index+m[0].length})}
  return out}
// Longest run of the quote's words found in order in the paper; accepted when it covers
// most of the quote, so a revised word or two still lands on the right sentence.
function locate(idx,q){if(!q.length||!idx.length)return null;let best=0,end=-1,prev=new Uint16Array(q.length+1),cur=new Uint16Array(q.length+1);
  for(let i=1;i<=idx.length;i++){const w=idx[i-1].w;for(let j=1;j<=q.length;j++){cur[j]=w===q[j-1]?prev[j-1]+1:0;if(cur[j]>best){best=cur[j];end=i-1}}[prev,cur]=[cur,prev];cur.fill(0)}
  if(best<Math.min(4,q.length)||best<q.length*.6)return null;
  const a=idx[end-best+1],b=idx[end],r=document.createRange();r.setStart(a.n,a.s);r.setEnd(b.n,b.e);return r}
function paperRoot(){return S.msView==="paper"?$("#pane .ms-paper"):null}
function markClaims(){clearMarks();const root=paperRoot(),d=reviewData(S.manuscript);if(!root||!d||!RV.open)return;
  const idx=paperIndex(root),groups={approved:[],needs_revision:[],rejected:[]};
  for(const a of d.claims){const st=finalState(a);if(st==="removed")continue;const r=locate(idx,quoteWords(finalQuote(a)));
    if(r){RV.ranges.set(a.id,r);groups[st]?.push(r)}}
  if(HL)for(const [k,rs] of Object.entries(groups))if(rs.length)CSS.highlights.set("rv-"+k,new Highlight(...rs))}
function clearMarks(){RV.ranges.clear();if(HL)["approved","needs_revision","rejected","focus"].forEach(k=>CSS.highlights.delete("rv-"+k));
  document.querySelectorAll(".rv-hit").forEach(e=>e.classList.remove("rv-hit"))}
function showRange(r){const pane=$("#pane");if(!pane||!r)return;
  document.querySelectorAll(".rv-hit").forEach(e=>e.classList.remove("rv-hit"));
  if(HL)CSS.highlights.set("rv-focus",new Highlight(r));
  const block=(r.startContainer.parentElement||pane).closest("p,li,td,.abs,figcaption,h1,h2,h3");if(block&&!HL)block.classList.add("rv-hit");
  const box=r.getBoundingClientRect(),top=pane.getBoundingClientRect().top;
  pane.scrollTo({top:Math.max(0,pane.scrollTop+box.top-top-pane.clientHeight/3),behavior:Kit.still()?"auto":"smooth"})}
function toPaperView(then){if(S.msView==="paper"){then();return}S.msView="paper";renderTab();requestAnimationFrame(then)}
function jumpToClaim(id){toPaperView(()=>{if(!RV.ranges.size)markClaims();const r=RV.ranges.get(id);
  if(r){showRange(r);selectClaim(id,false)}else toast("This claim's exact words are not in the final paper",true)})}
function jumpToText(text){toPaperView(()=>{const root=paperRoot();const r=root&&locate(paperIndex(root),words(text));
  if(r)showRange(r);else toast("This sentence's exact words are not in the final paper",true)})}
// A click on a marked claim in the paper opens its card in the panel.
function onPaperClick(e){if(!RV.open||!RV.ranges.size||e.target.closest("button,a,.ms-bar"))return;
  const pos=document.caretPositionFromPoint?.(e.clientX,e.clientY),rng=pos?null:document.caretRangeFromPoint?.(e.clientX,e.clientY);
  const node=pos?.offsetNode||rng?.startContainer,off=pos?pos.offset:rng?.startOffset;if(!node)return;
  for(const [id,r] of RV.ranges){try{if(r.isPointInRange(node,off)){if(HL)CSS.highlights.set("rv-focus",new Highlight(r));selectClaim(id,true);return}}catch{}}}
function selectClaim(id,scroll){let card=$(`.rv-claim[data-a="${id}"]`);
  if(!card&&RV.filter!=="all"){RV.filter="all";const d=reviewData(S.manuscript),sec=$("#rvList")?.closest(".rv-sec");if(d&&sec)sec.outerHTML=claimsHtml(d);card=$(`.rv-claim[data-a="${id}"]`)}
  if(!card)return;document.querySelectorAll(".rv-claim.on").forEach(c=>c.classList.remove("on"));card.classList.add("on");
  if(scroll)card.scrollIntoView({block:"nearest",behavior:Kit.still()?"auto":"smooth"})}

/* ---------- PDF: typeset by the campaign's container, cached in R2 ---------- */
const pdfUrl=(id,dl)=>`/api/campaigns/${eid(id)}/manuscript.pdf${dl?"?download=1":""}`;
function resetPdf(){if(PDFV.url)URL.revokeObjectURL(PDFV.url);Object.assign(PDFV,{cid:null,url:null,state:null,err:""})}
async function loadPdf(){const id=S.route.id;if(PDFV.cid===id&&PDFV.state&&PDFV.state!=="error")return;resetPdf();
  Object.assign(PDFV,{cid:id,state:"loading"});
  try{const r=await api(`campaigns/${eid(id)}/manuscript.pdf`),b=await r.blob();if(PDFV.cid!==id)return;
    PDFV.url=URL.createObjectURL(b.type==="application/pdf"?b:new Blob([b],{type:"application/pdf"}));PDFV.state="ready"}
  catch(e){if(PDFV.cid!==id)return;PDFV.state="error";PDFV.err=e.message}
  if(S.route.id===id&&S.route.tab==="manuscript"&&(S.msView==="pdf"||S.msView==="src"&&PDFV.split))renderTab()}
function pdfFrame(){const c=S.summary.campaign;
  if(c.status!=="completed")return `<div class="pdf-msg"><b>The PDF is typeset once the paper is final.</b><p class="t2">${c.status==="halted"?"This campaign halted before its paper was finished.":"It appears here when the campaign completes."}</p></div>`;
  if(PDFV.cid!==S.route.id||!PDFV.state)loadPdf();
  if(PDFV.state==="error")return `<div class="pdf-msg"><b>Could not typeset the PDF</b><p class="t2">${esc(PDFV.err)}</p><button class="btn sm" type="button" data-pdf-retry>Try again</button></div>`;
  if(PDFV.state!=="ready")return `<div class="pdf-msg pdf-wait" aria-live="polite"><span class="live" style="--c:var(--blue)"></span><b>Typesetting the paper with pdfLaTeX</b><p class="t2">The first view of a paper takes a few seconds; after that it opens instantly.</p></div>`;
  return `<iframe class="pdf-frame" src="${esc(PDFV.url)}#view=FitH" title="${esc(c.research_question)}: typeset paper (PDF)"></iframe>`}
function pdfActions(){const id=S.route.id,dl=ico('<path d="M8 2.5v8M4.5 7 8 10.5 11.5 7M3 13.5h10"/>');
  return `<a class="btn" href="${pdfUrl(id)}" target="_blank" rel="noopener">${ico('<path d="M9 3h4v4M13 3 7.5 8.5M11.5 9.5V13H3V4.5h3.5"/>')}Open</a><a class="btn" href="${pdfUrl(id,true)}" download>${dl}.pdf</a>`}
