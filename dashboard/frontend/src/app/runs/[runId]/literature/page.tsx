import LiteratureClient from "./client";

export async function generateStaticParams() {
  return [{ runId: "_" }];
}

export default function Page() {
  return <LiteratureClient />;
}
