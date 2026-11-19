// Stub of the Anthropic Messages API for local tests: records every request body and
// plays a scripted orchestrator (tool call for research asks, then a summary).
import http from "node:http";
import fs from "node:fs";
const LOG = process.argv[2] || "/tmp/stub-requests.jsonl";
let n = 0;
const send = (res, code, body) => { res.writeHead(code, { "content-type": "application/json", "request-id": "req_stub" }); res.end(JSON.stringify(body)); };
http.createServer((req, res) => {
  let data = "";
  req.on("data", (c) => (data += c));
  req.on("end", () => {
    const key = req.headers["x-api-key"] ?? String(req.headers.authorization ?? "").replace(/^Bearer /, "");
    if (req.url.startsWith("/v1/models")) {
      if (String(key).startsWith("sk-ant-bad")) return send(res, 401, { type: "error", error: { type: "authentication_error", message: "invalid x-api-key" } });
      return send(res, 200, { data: [{ id: "claude-haiku-5-5", type: "model" }], has_more: false, first_id: null, last_id: null });
    }
    if (req.url.startsWith("/v1/messages")) {
      const body = JSON.parse(data);
      fs.appendFileSync(LOG, JSON.stringify({ key: key?.slice(-4), url: req.url, beta: req.headers["anthropic-beta"] ?? null, body }) + "\n");
      const last = body.messages.at(-1);
      const blocks = Array.isArray(last.content) ? last.content : [{ type: "text", text: last.content }];
      const results = blocks.filter((b) => b.type === "tool_result");
      const text = blocks.filter((b) => b.type === "text" && !b.text.startsWith("<context>")).map((b) => b.text).join("\n");
      const id = `msg_${++n}`;
      const think = { type: "thinking", thinking: "", signature: `sig-${n}-` + "x".repeat(40) };
      const usage = { input_tokens: 1200, output_tokens: 300, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 };
      let content, stop = "end_turn";
      if (results.length) {
        const r = results[0];
        content = [think, { type: "text", text: r.is_error ? `That didn't work: ${r.content}` : `I started a research thread on that. **What it will test:** whether the claim holds.\n\n- Thread result: ${String(r.content).slice(0, 120)}` }];
      } else if (/research|investigate|study/i.test(text) && body.tool_choice?.type !== "none") {
        content = [think, { type: "text", text: "I'll start a thread for this." },
          { type: "tool_use", id: `toolu_${Date.now()}_${n}`, name: "start_research_thread", input: { question: "Does the 95% OLS slope interval keep nominal coverage when the error variance grows with x, at n = 50?", token_budget: 400000 } }];
        stop = "tool_use";
      } else if (/status|progress/i.test(text)) {
        content = [think, { type: "tool_use", id: `toolu_${Date.now()}_${n}`, name: "list_threads", input: {} }];
        stop = "tool_use";
      } else {
        content = [think, { type: "text", text: `You said: ${text.replace(/<context>[\s\S]*?<\/context>/, "").trim().slice(0, 200)}` }];
      }
      return send(res, 200, { id, type: "message", role: "assistant", model: body.model, content, stop_reason: stop, stop_sequence: null, usage });
    }
    send(res, 404, { type: "error", error: { type: "not_found_error", message: "no" } });
  });
}).listen(8790, "127.0.0.1", () => console.log("stub on 8790"));
