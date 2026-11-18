/* Boot: find out who is signed in, then route. Loaded last, after app.js, account.js and agent.js. */
"use strict";
(async()=>{
  try{localStorage.removeItem("plato_token")}catch{}   // the old bearer-token sign-in kept it here
  const mac=/Mac|iPhone|iPad/.test(navigator.platform||navigator.userAgent);
  if(!mac)document.querySelectorAll("[data-mod]").forEach(el=>{el.textContent=el.textContent.replace("⌘","Ctrl ")});
  $("#askBtn").onclick=toggleAsk;
  let bootErr="";
  try{await loadMe()}catch(e){bootErr=e.message||"Plato is unreachable."}
  route();
  if(bootErr&&$("#authErr")){$("#authErr").textContent=`Couldn't reach Plato: ${bootErr}`;$("#authErr").hidden=false}
  if(S.me?.account){health();loadList();loadProjects()}
  setInterval(()=>{if(!document.hidden&&S.me?.account){loadList();loadProjects()}},20000);
})();
