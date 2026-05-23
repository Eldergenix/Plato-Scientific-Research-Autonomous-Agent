import { RunReviewsClient } from "./reviews-client";

interface RunReviewsParams {
  runId: string;
}

export function generateStaticParams(): RunReviewsParams[] {
  return [];
}

export default async function RunReviewsPage({
  params,
}: {
  params: Promise<RunReviewsParams>;
}) {
  const { runId } = await params;
  return <RunReviewsClient runId={runId} />;
}
