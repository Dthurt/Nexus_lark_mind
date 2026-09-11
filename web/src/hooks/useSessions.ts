import { useCallback, useState } from "react";
import {
  createSession,
  deleteSession,
  getSession,
  listSessions,
  patchWorkspace,
} from "@/api/endpoints";
import { newId } from "@/lib/id";
import type { SessionDetail, Usage } from "@/types/api";

const LOCAL_KEY = "nlm_conversations_v2";
const ACTIVE_KEY = "nlm_session_id";

export type LocalConversation = {
  id: string;
  title: string;
  preview: string;
  updatedAt: string;
  workspaceId: string;
  workspaceTitle: string;
  cwd: string;
  workspaceKind: string;
  sshHostId: string;
};

function loadLocalConvs(): LocalConversation[] {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveLocalConvs(list: LocalConversation[]) {
  localStorage.setItem(LOCAL_KEY, JSON.stringify(list.slice(0, 80)));
}

export function useSessions() {
  const [sessionId, setSessionId] = useState(() => {
    const id = localStorage.getItem(ACTIVE_KEY) || newId();
    localStorage.setItem(ACTIVE_KEY, id);
    return id;
  });
  const [conversations, setConversations] = useState<LocalConversation[]>(loadLocalConvs);
  const [chatTitle, setChatTitle] = useState("新对话");
  const [sessionUsage, setSessionUsage] = useState<Usage>({});
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaceTitle, setWorkspaceTitle] = useState("");
  const [cwd, setCwd] = useState("");
  const [workspaceKind, setWorkspaceKind] = useState("local");
  const [sshHostId, setSshHostId] = useState("");

  const persistActive = useCallback((id: string) => {
    localStorage.setItem(ACTIVE_KEY, id);
  }, []);

  const applyWorkspaceMeta = useCallback(
    ({
      workspace_id,
      workspace_title,
      cwd: path,
      workspace_kind,
      ssh_host_id,
    }: {
      workspace_id?: string;
      workspace_title?: string;
      cwd?: string;
      workspace_kind?: string;
      ssh_host_id?: string;
    } = {}) => {
      setWorkspaceId(workspace_id || "");
      setWorkspaceTitle(workspace_title || "");
      setCwd(path || "");
      setWorkspaceKind(workspace_kind || (ssh_host_id ? "ssh" : "local"));
      setSshHostId(ssh_host_id || "");
    },
    [],
  );

  const upsertLocalConv = useCallback((partial: Partial<LocalConversation> & { id: string }) => {
    const list = loadLocalConvs();
    const i = list.findIndex((c) => c.id === partial.id);
    const next: LocalConversation = {
      id: partial.id,
      title: partial.title || "新对话",
      preview: partial.preview || "",
      updatedAt: partial.updatedAt || new Date().toISOString(),
      workspaceId: partial.workspaceId || "",
      workspaceTitle: partial.workspaceTitle || "",
      cwd: partial.cwd || "",
      workspaceKind: partial.workspaceKind || "local",
      sshHostId: partial.sshHostId || "",
    };
    if (i >= 0) list[i] = { ...list[i], ...next };
    else list.unshift(next);
    list.sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
    saveLocalConvs(list);
    setConversations(list);
  }, []);

  const syncServerList = useCallback(async () => {
    try {
      const remote = await listSessions();
      const local = loadLocalConvs();
      const map = new Map(local.map((c) => [c.id, c]));
      for (const r of remote || []) {
        map.set(r.session_id, {
          id: r.session_id,
          title: r.title || "新对话",
          preview: r.preview || "",
          updatedAt: r.updated_at || new Date().toISOString(),
          workspaceId: r.workspace_id || "",
          workspaceTitle: r.workspace_title || "",
          cwd: r.cwd || "",
          workspaceKind: r.workspace_kind || "local",
          sshHostId: r.ssh_host_id || "",
        });
      }
      if (!map.has(sessionId)) {
        map.set(sessionId, {
          id: sessionId,
          title: "新对话",
          preview: "",
          updatedAt: new Date().toISOString(),
          workspaceId,
          workspaceTitle,
          cwd,
          workspaceKind,
          sshHostId,
        });
      }
      const merged = [...map.values()].sort((a, b) =>
        String(b.updatedAt).localeCompare(String(a.updatedAt)),
      );
      saveLocalConvs(merged);
      setConversations(merged);
    } catch {
      upsertLocalConv({
        id: sessionId,
        title: chatTitle || "新对话",
        workspaceId,
        workspaceTitle,
        cwd,
      });
    }
  }, [
    chatTitle,
    cwd,
    sessionId,
    sshHostId,
    upsertLocalConv,
    workspaceId,
    workspaceKind,
    workspaceTitle,
  ]);

  const fetchSession = useCallback(async (): Promise<SessionDetail | null> => {
    try {
      const data = await getSession(sessionId);
      if (data) {
        applyWorkspaceMeta(data);
        setChatTitle(data.title || chatTitle);
        setSessionUsage(data.usage || {});
      }
      return data;
    } catch {
      return null;
    }
  }, [applyWorkspaceMeta, chatTitle, sessionId]);

  const ensureSessionOnServer = useCallback(
    async ({
      workspace_id,
      cwd: path,
      workspace_kind,
      ssh_host_id,
    }: {
      workspace_id?: string;
      cwd?: string;
      workspace_kind?: string;
      ssh_host_id?: string;
    } = {}) => {
      const body: Record<string, string> = {
        session_id: sessionId,
        channel: "web",
        user_id: "web-user",
      };
      if (workspace_id) body.workspace_id = workspace_id;
      if (path) body.cwd = path;
      if (workspace_kind) body.workspace_kind = workspace_kind;
      if (ssh_host_id) body.ssh_host_id = ssh_host_id;
      const data = await createSession(body as any);
      applyWorkspaceMeta(data || {});
      upsertLocalConv({
        id: sessionId,
        title: chatTitle || "新对话",
        workspaceId: data?.workspace_id || workspace_id || "",
        workspaceTitle: data?.workspace_title || "",
        cwd: data?.cwd || path || "",
        workspaceKind: data?.workspace_kind || workspace_kind || "local",
        sshHostId: data?.ssh_host_id || ssh_host_id || "",
      });
      return data;
    },
    [applyWorkspaceMeta, chatTitle, sessionId, upsertLocalConv],
  );

  const bindWorkspace = useCallback(
    async ({
      workspace_id,
      cwd: path,
      workspace_kind,
      ssh_host_id,
    }: {
      workspace_id?: string;
      cwd?: string;
      workspace_kind?: string;
      ssh_host_id?: string;
    } = {}) => {
      const body: Record<string, string> = {};
      if (workspace_id) body.workspace_id = workspace_id;
      if (path) body.cwd = path;
      if (workspace_kind) body.workspace_kind = workspace_kind;
      if (ssh_host_id) body.ssh_host_id = ssh_host_id;
      const data = await patchWorkspace(sessionId, body);
      applyWorkspaceMeta(data || {});
      upsertLocalConv({
        id: sessionId,
        title: chatTitle || "新对话",
        workspaceId: data?.workspace_id || "",
        workspaceTitle: data?.workspace_title || "",
        cwd: data?.cwd || "",
        workspaceKind: data?.workspace_kind || "local",
        sshHostId: data?.ssh_host_id || "",
      });
      return data;
    },
    [applyWorkspaceMeta, chatTitle, sessionId, upsertLocalConv],
  );

  const startNew = useCallback(
    ({
      workspace_id,
      workspace_title,
      cwd: path,
      workspace_kind,
      ssh_host_id,
    }: {
      workspace_id?: string;
      workspace_title?: string;
      cwd?: string;
      workspace_kind?: string;
      ssh_host_id?: string;
    } = {}) => {
      const id = newId();
      setSessionId(id);
      persistActive(id);
      setChatTitle("新对话");
      setSessionUsage({});
      const meta = {
        workspace_id: workspace_id || "",
        workspace_title: workspace_title || "",
        cwd: path || "",
        workspace_kind: workspace_kind || (ssh_host_id ? "ssh" : "local"),
        ssh_host_id: ssh_host_id || "",
      };
      applyWorkspaceMeta(meta);
      upsertLocalConv({
        id,
        title: "新对话",
        preview: "",
        workspaceId: meta.workspace_id,
        workspaceTitle: meta.workspace_title,
        cwd: meta.cwd,
        workspaceKind: meta.workspace_kind,
        sshHostId: meta.ssh_host_id,
      });
    },
    [applyWorkspaceMeta, persistActive, upsertLocalConv],
  );

  const switchTo = useCallback(
    (id: string) => {
      if (id === sessionId) return false;
      setSessionId(id);
      persistActive(id);
      const local = conversations.find((c) => c.id === id);
      if (local) {
        applyWorkspaceMeta({
          workspace_id: local.workspaceId,
          workspace_title: local.workspaceTitle,
          cwd: local.cwd,
          workspace_kind: local.workspaceKind,
          ssh_host_id: local.sshHostId,
        });
        setChatTitle(local.title || "新对话");
      }
      return true;
    },
    [applyWorkspaceMeta, conversations, persistActive, sessionId],
  );

  const deleteConversation = useCallback(
    async (id: string) => {
      const list = loadLocalConvs().filter((c) => c.id !== id);
      saveLocalConvs(list);
      setConversations(list);
      try {
        await deleteSession(id);
      } catch {
        /* ignore */
      }
      return id === sessionId;
    },
    [sessionId],
  );

  const setSessionIdPersisted = useCallback(
    (id: string) => {
      setSessionId(id);
      persistActive(id);
    },
    [persistActive],
  );

  return {
    sessionId,
    setSessionId: setSessionIdPersisted,
    conversations,
    chatTitle,
    setChatTitle,
    sessionUsage,
    setSessionUsage,
    workspaceId,
    workspaceTitle,
    cwd,
    workspaceKind,
    sshHostId,
    upsertLocalConv,
    syncServerList,
    fetchSession,
    ensureSessionOnServer,
    bindWorkspace,
    applyWorkspaceMeta,
    startNew,
    switchTo,
    deleteConversation,
  };
}
