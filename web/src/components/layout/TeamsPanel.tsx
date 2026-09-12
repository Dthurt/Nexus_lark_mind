import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getTeamSnapshot, postTeamDagNode } from "@/api/endpoints";
import { cn } from "@/lib/utils";

export type TeamsPanelProps = {
  teamId?: string;
  className?: string;
};

export function TeamsPanel({ teamId = "", className }: TeamsPanelProps) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const id = (teamId || "").trim();
    if (!id) {
      setData(null);
      setError("需要会话 ID（team_id 默认等于 session_id）");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const snap = await getTeamSnapshot(id);
      setData(snap);
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [teamId]);

  useEffect(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const addNode = async () => {
    const id = (teamId || "").trim();
    if (!id) return;
    const label = window.prompt("DAG 节点标签", `step-${Date.now() % 1000}`);
    if (!label) return;
    setBusy(true);
    try {
      await postTeamDagNode(id, { label });
      await refresh();
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const mailbox = data?.mailbox;
  const dag = data?.dag;
  const agents = mailbox?.agents || [];
  const messages = mailbox?.messages || [];
  const nodes = dag?.nodes || [];

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col gap-2 overflow-auto p-2 text-[12px]", className)}>
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Teams</div>
          <div className="font-medium text-foreground truncate max-w-[180px]" title={teamId}>
            {teamId || "—"}
          </div>
        </div>
        <div className="flex gap-1">
          <Button type="button" size="sm" variant="outline" className="h-7 px-2" disabled={busy} onClick={() => void refresh()}>
            刷新
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-7 px-2" disabled={busy || !teamId} onClick={() => void addNode()}>
            +DAG
          </Button>
        </div>
      </div>

      {data && !data.enabled ? (
        <p className="m-0 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-100">
          设置 <code>NLM_EXPERIMENTAL_TEAMS=true</code> 后，模型可用 team_send / team_recv；邮箱与 DAG 仍可在此查看。
        </p>
      ) : null}

      {error ? <p className="m-0 text-destructive">{error}</p> : null}

      <section>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">拓扑 · Agents</div>
        {agents.length ? (
          <ul className="m-0 list-none space-y-1 p-0">
            {agents.map((a: any) => (
              <li key={a.id} className="rounded-md border border-border/60 bg-muted/30 px-2 py-1">
                <span className="font-medium">{a.id}</span>
                <span className="ml-2 text-muted-foreground">posts {a.posts}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-muted-foreground">暂无 agent 投递</p>
        )}
      </section>

      <section>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
          邮箱 · {mailbox?.pending ?? 0} pending / {mailbox?.message_count ?? 0} total
        </div>
        <ul className="m-0 max-h-40 list-none space-y-1 overflow-auto p-0">
          {messages.length ? (
            [...messages].reverse().map((m: any) => (
              <li key={m.id} className="rounded-md border border-border/50 px-2 py-1">
                <div className="text-muted-foreground">
                  {m.from_id} → {m.to_id}
                  {m.claimed_by ? ` · claimed ${m.claimed_by}` : " · open"}
                </div>
                <pre className="m-0 mt-0.5 max-h-16 overflow-auto whitespace-pre-wrap break-words text-[11px]">
                  {typeof m.payload === "string" ? m.payload : JSON.stringify(m.payload)}
                </pre>
              </li>
            ))
          ) : (
            <li className="text-muted-foreground">空邮箱</li>
          )}
        </ul>
      </section>

      <section>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">DAG</div>
        <ul className="m-0 list-none space-y-1 p-0">
          {nodes.length ? (
            nodes.map((n: any) => (
              <li
                key={n.id}
                className={cn(
                  "rounded-md border px-2 py-1",
                  n.status === "ready" && "border-emerald-500/40 bg-emerald-500/10",
                  n.status === "done" && "border-border/40 opacity-70",
                  n.status === "pending" && "border-border/60",
                )}
              >
                <span className="font-medium">{n.label || n.id}</span>
                <span className="ml-2 text-muted-foreground">{n.status}</span>
                {n.depends_on?.length ? (
                  <div className="text-[10px] text-muted-foreground">depends: {n.depends_on.join(", ")}</div>
                ) : null}
              </li>
            ))
          ) : (
            <li className="text-muted-foreground">无节点 — 点 +DAG 添加</li>
          )}
        </ul>
      </section>
    </div>
  );
}
