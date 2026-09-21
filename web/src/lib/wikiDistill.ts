import { distillWiki, listKnowledgeJobs, type KnowledgeIngestJob } from "@/api/endpoints";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function waitForKnowledgeJob(opts: {
  jobId: string;
  kbId: string;
  timeoutMs?: number;
  onTick?: () => void;
}): Promise<KnowledgeIngestJob | undefined> {
  const timeoutMs = opts.timeoutMs ?? 15 * 60 * 1000;
  const start = Date.now();
  let delay = 700;
  while (Date.now() - start < timeoutMs) {
    await sleep(delay);
    opts.onTick?.();
    const jobs = await listKnowledgeJobs({ kb_id: opts.kbId, limit: 24 });
    const hit = (jobs.jobs || []).find((job) => job.job_id === opts.jobId);
    if (!hit || hit.status === "completed" || hit.status === "failed") {
      return hit;
    }
    delay = Math.min(3000, Math.round(delay * 1.25));
  }
  throw new Error("任务仍在运行，请稍后刷新");
}

export async function runWikiDistill(opts: {
  kbId: string;
  workspaceId?: string;
  onTick?: () => void;
}): Promise<KnowledgeIngestJob | undefined> {
  const data = await distillWiki({
    kb_id: opts.kbId,
    workspace_id: opts.workspaceId || undefined,
  });
  const jobId = data.job?.job_id;
  if (!jobId) return data.job;
  return waitForKnowledgeJob({
    jobId,
    kbId: opts.kbId,
    onTick: opts.onTick,
  });
}
