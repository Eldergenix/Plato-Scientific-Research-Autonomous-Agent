/* An experiment's design (intent node): the scientist stores it in hypothesis_or_spec as a JSON
   object {hypothesis, protocol, primary_metric, test_kind, success_criterion}. This is the one
   place the app reads that text, so every view shows labelled fields and never the raw JSON.

   It also reads the shapes older or malformed rows can have: the object encoded twice (a JSON
   string holding the JSON), and a model that put the whole object inside the hypothesis field.
   Plain text (goals, hints, facts, findings) stays plain text. Mirrors
   plato.scientist.schemas.decode_intent_spec. */
(function (root) {
  "use strict";
  const FIELDS = [
    ["hypothesis", "Hypothesis"],
    ["protocol", "Protocol"],
    ["success_criterion", "Success criterion"],
    ["primary_metric", "Primary metric"],
    ["test_kind", "Test"],
  ];
  const KEYS = FIELDS.map(([k]) => k);

  // JSON object from text, unwrapping a JSON string that holds one (at most twice). null otherwise.
  function objectOf(text) {
    let v = text;
    for (let i = 0; i < 3 && typeof v === "string"; i++) {
      const t = v.trim();
      if (!/^[{"]/.test(t)) return null;
      try { v = JSON.parse(t); } catch { return null; }
    }
    return v && typeof v === "object" && !Array.isArray(v) ? v : null;
  }
  const str = (v) => (typeof v === "string" ? v.trim() : typeof v === "number" || typeof v === "boolean" ? String(v) : "");

  // The design as {hypothesis, protocol, ...} (strings, empty fields left out), or null when the
  // text is not a design.
  function parse(text) {
    const o = objectOf(text);
    if (!o || !KEYS.some((k) => k in o)) return null;
    const spec = {};
    for (const k of KEYS) { const s = str(o[k]); if (s) spec[k] = s; }
    // The whole design inside "hypothesis": its hypothesis replaces the blob, the rest fills gaps.
    const inner = spec.hypothesis ? parse(spec.hypothesis) : null;
    if (inner && inner.hypothesis) {
      spec.hypothesis = inner.hypothesis;
      for (const k of KEYS) if (inner[k] && !spec[k]) spec[k] = inner[k];
    }
    return Object.keys(spec).length ? spec : null;
  }

  // An intent's design for the experiment views: plain text becomes the hypothesis.
  function of(text) {
    const s = typeof text === "string" ? text.trim() : "";
    return parse(s) || (s ? { hypothesis: s } : {});
  }

  const fields = (spec) => FIELDS.filter(([k]) => spec && spec[k]).map(([k, label]) => [label, spec[k]]);

  // HTML for a node's text: a labelled list for a design, else one paragraph. esc escapes text.
  function html(text, esc, paraClass = "para") {
    const spec = parse(text);
    if (spec) return `<dl class="xp-spec">${fields(spec).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
    return text ? `<div class="${paraClass}">${esc(text)}</div>` : "";
  }

  root.PlatoSpec = Object.freeze({ FIELDS, parse, of, fields, html });
})(typeof window !== "undefined" ? window : globalThis);
