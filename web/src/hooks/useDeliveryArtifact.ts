import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { getPluginCalls, postSessionDelivery } from "@/api/endpoints";
import {
  buildDeliveryMarkdown,
  deliveryFileName,
  planTitleFromMarkdown,
  summarizeMutationCalls,
  type DeliverySeed,
} from "@/lib/deliveryArtifact";

export type DeliveryArtifactState = {
  id: string;
  fileName: string;
  title: string;
  plan: string;
  callId?: string;
  sessionId: string;
  acceptedAt: string;
  markdown: string;
  mutationLines: string[];
  workspacePath?: string;
};

function newId() {
  return `del_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function useDeliveryArtifact() {
  const [current, setCurrent] = useState<DeliveryArtifactState | null>(null);
  const [history, setHistory] = useState<DeliveryArtifactState[]>([]);
  const syncingRef = useRef(false);
  const cwdRef = useRef("");
  const kindRef = useRef("local");

  const setWorkspace = useCallback((cwd: string, kind = "local") => {
    cwdRef.current = (cwd || "").trim();
    kindRef.current = (kind || "local").trim() || "local";
  }, []);

  const publishDelivery = useCallback(
    async (sessionId: string, fileName: string, markdown: string) => {
      try {
        const data = await postSessionDelivery(sessionId, {
          name: fileName,
          content: markdown,
          cwd: cwdRef.current || undefined,
          workspace_kind: kindRef.current,
        });
        const ws = data?.workspace;
        if (ws?.ok && ws.path) {
          return ws.path;
        }
        if (ws && ws.ok === false && ws.error && cwdRef.current) {
          toast.message("Delivery 已写入会话", { description: `工作区落盘跳过：${ws.error}` });
        }
        return undefined;
      } catch (err: any) {
        toast.error(`Delivery 写入失败：${err?.message || err}`);
        return undefined;
      }
    },
    [],
  );

  const createFromPlan = useCallback(
    async (opts: {
      sessionId: string;
      plan: string;
      title?: string;
      callId?: string;
      cwd?: string;
      workspaceKind?: string;
    }) => {
      const sessionId = (opts.sessionId || "").trim();
      const plan = String(opts.plan || "").trim();
      if (!sessionId || !plan) return null;
      if (opts.cwd != null) setWorkspace(opts.cwd, opts.workspaceKind || "local");

      const acceptedAt = new Date().toISOString();
      const title = planTitleFromMarkdown(plan, opts.title || "Delivery");
      const fileName = deliveryFileName(title);
      const guessedWs =
        cwdRef.current && kindRef.current === "local"
          ? `.nlm/deliveries/${fileName}`
          : undefined;
      const seed: DeliverySeed = {
        title,
        plan,
        callId: opts.callId,
        sessionId,
        acceptedAt,
        workspacePath: guessedWs,
      };
      const markdown = buildDeliveryMarkdown(seed, []);
      const workspacePath = (await publishDelivery(sessionId, fileName, markdown)) || guessedWs;
      const art: DeliveryArtifactState = {
        id: newId(),
        fileName,
        title,
        plan,
        callId: opts.callId,
        sessionId,
        acceptedAt,
        markdown: workspacePath
          ? buildDeliveryMarkdown({ ...seed, workspacePath }, [])
          : markdown,
        mutationLines: [],
        workspacePath,
      };
      if (workspacePath && workspacePath !== guessedWs) {
        art.markdown = buildDeliveryMarkdown({ ...seed, workspacePath }, []);
        await publishDelivery(sessionId, fileName, art.markdown);
      }
      setCurrent(art);
      setHistory((h) => [art, ...h].slice(0, 12));
      toast.success(
        workspacePath ? `Delivery 已落盘 ${workspacePath}` : "已创建 Delivery 审计文档",
      );
      return art;
    },
    [publishDelivery, setWorkspace],
  );

  const syncMutations = useCallback(
    async (sessionId?: string) => {
      const art = current;
      const sid = (sessionId || art?.sessionId || "").trim();
      if (!art || !sid || syncingRef.current) return art;
      syncingRef.current = true;
      try {
        const rows = await getPluginCalls(sid, 80);
        const lines = summarizeMutationCalls(rows || []);
        const seed: DeliverySeed = {
          title: art.title,
          plan: art.plan,
          callId: art.callId,
          sessionId: art.sessionId,
          acceptedAt: art.acceptedAt,
          workspacePath: art.workspacePath,
        };
        const markdown = buildDeliveryMarkdown(seed, lines);
        const workspacePath =
          (await publishDelivery(sid, art.fileName, markdown)) || art.workspacePath;
        const nextMd = workspacePath
          ? buildDeliveryMarkdown({ ...seed, workspacePath }, lines)
          : markdown;
        if (workspacePath && workspacePath !== art.workspacePath) {
          await publishDelivery(sid, art.fileName, nextMd);
        }
        const next = {
          ...art,
          mutationLines: lines,
          markdown: nextMd,
          workspacePath,
        };
        setCurrent(next);
        setHistory((h) => h.map((x) => (x.id === next.id ? next : x)));
        return next;
      } catch (err: any) {
        toast.error(`同步变更失败：${err?.message || err}`);
        return art;
      } finally {
        syncingRef.current = false;
      }
    },
    [current, publishDelivery],
  );

  const clear = useCallback(() => setCurrent(null), []);

  return {
    current,
    history,
    createFromPlan,
    syncMutations,
    clear,
    setCurrent,
    setWorkspace,
  };
}

export type DeliveryArtifactApi = ReturnType<typeof useDeliveryArtifact>;
