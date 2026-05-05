import RunDetailClient from "./client";

// Static export needs every dynamic segment to declare its params at build
// time. Run IDs are coined at runtime, so we emit a single ``_`` placeholder
// — that produces ``out/runs/_/index.html`` whose React tree is the right
// shape for any /runs/<id>/ deep link. ``_SPAStaticFiles`` in the FastAPI
// server rewrites unknown ids to ``_`` before serving, and the client's
// ``useParams()`` reads the live id from the URL on hydration.
export async function generateStaticParams() {
  return [{ runId: "_" }];
}

export default function Page() {
  return <RunDetailClient />;
}
