import { ref } from "vue";
import { newId } from "@/utils/id";

const LOCAL_KEY = "nlm_conversations_v2";
const ACTIVE_KEY = "nlm_session_id";

function loadLocalConvs() {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveLocalConvs(list) {
  localStorage.setItem(LOCAL_KEY, JSON.stringify(list.slice(0, 80)));
}

export function useSessions() {
  const sessionId = ref(localStorage.getItem(ACTIVE_KEY) || newId());
  localStorage.setItem(ACTIVE_KEY, sessionId.value);

  const conversations = ref(loadLocalConvs());
  const chatTitle = ref("新对话");
  const sessionUsage = ref({});
  const workspaceId = ref("");
  const workspaceTitle = ref("");
  const cwd = ref("");
  const workspaceKind = ref("local");
  const sshHostId = ref("");

  function persistActive() {
    localStorage.setItem(ACTIVE_KEY, sessionId.value);
  }

  function upsertLocalConv(partial) {
    const list = loadLocalConvs();
    const i = list.findIndex((c) => c.id === partial.id);
    const next = {
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
    conversations.value = list;
  }

  function applyWorkspaceMeta({
    workspace_id,
    workspace_title,
    cwd: path,
    workspace_kind,
    ssh_host_id,
  } = {}) {
    workspaceId.value = workspace_id || "";
    workspaceTitle.value = workspace_title || "";
    cwd.value = path || "";
    workspaceKind.value = workspace_kind || (ssh_host_id ? "ssh" : "local");
    sshHostId.value = ssh_host_id || "";
  }

  async function syncServerList() {
    try {
      const resp = await fetch("/api/sessions");
      const json = await resp.json();
      const remote = json.data || [];
      const local = loadLocalConvs();
      const map = new Map(local.map((c) => [c.id, c]));
      for (const r of remote) {
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
      if (!map.has(sessionId.value)) {
        map.set(sessionId.value, {
          id: sessionId.value,
          title: "新对话",
          preview: "",
          updatedAt: new Date().toISOString(),
          workspaceId: workspaceId.value,
          workspaceTitle: workspaceTitle.value,
          cwd: cwd.value,
          workspaceKind: workspaceKind.value,
          sshHostId: sshHostId.value,
        });
      }
      const merged = [...map.values()].sort((a, b) =>
        String(b.updatedAt).localeCompare(String(a.updatedAt))
      );
      saveLocalConvs(merged);
      conversations.value = merged;
    } catch {
      upsertLocalConv({
        id: sessionId.value,
        title: chatTitle.value || "新对话",
        workspaceId: workspaceId.value,
        workspaceTitle: workspaceTitle.value,
        cwd: cwd.value,
      });
    }
  }

  async function fetchSession() {
    try {
      const resp = await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}`);
      const json = await resp.json();
      const data = json.data || null;
      if (data) {
        applyWorkspaceMeta(data);
        chatTitle.value = data.title || chatTitle.value;
        sessionUsage.value = data.usage || {};
      }
      return data;
    } catch {
      return null;
    }
  }

  async function ensureSessionOnServer({ workspace_id, cwd: path, workspace_kind, ssh_host_id } = {}) {
    const body = {
      session_id: sessionId.value,
      channel: "web",
      user_id: "web-user",
    };
    if (workspace_id) body.workspace_id = workspace_id;
    if (path) body.cwd = path;
    if (workspace_kind) body.workspace_kind = workspace_kind;
    if (ssh_host_id) body.ssh_host_id = ssh_host_id;
    const resp = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const json = await resp.json();
    if (!json.ok) throw new Error(json.error?.message || "create session failed");
    const data = json.data || {};
    applyWorkspaceMeta(data);
    upsertLocalConv({
      id: sessionId.value,
      title: chatTitle.value || "新对话",
      workspaceId: workspaceId.value,
      workspaceTitle: workspaceTitle.value,
      cwd: cwd.value,
      workspaceKind: workspaceKind.value,
      sshHostId: sshHostId.value,
    });
    return data;
  }

  async function bindWorkspace({ workspace_id, cwd: path, workspace_kind, ssh_host_id } = {}) {
    const body = {};
    if (workspace_id) body.workspace_id = workspace_id;
    if (path) body.cwd = path;
    if (workspace_kind) body.workspace_kind = workspace_kind;
    if (ssh_host_id) body.ssh_host_id = ssh_host_id;
    const resp = await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}/workspace`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const json = await resp.json();
    if (!json.ok) throw new Error(json.error?.message || "bind workspace failed");
    applyWorkspaceMeta(json.data || {});
    upsertLocalConv({
      id: sessionId.value,
      title: chatTitle.value || "新对话",
      workspaceId: workspaceId.value,
      workspaceTitle: workspaceTitle.value,
      cwd: cwd.value,
      workspaceKind: workspaceKind.value,
      sshHostId: sshHostId.value,
    });
    return json.data;
  }

  function startNew({ workspace_id, workspace_title, cwd: path, workspace_kind, ssh_host_id } = {}) {
    sessionId.value = newId();
    persistActive();
    chatTitle.value = "新对话";
    sessionUsage.value = {};
    applyWorkspaceMeta({
      workspace_id: workspace_id || "",
      workspace_title: workspace_title || "",
      cwd: path || "",
      workspace_kind: workspace_kind || (ssh_host_id ? "ssh" : "local"),
      ssh_host_id: ssh_host_id || "",
    });
    upsertLocalConv({
      id: sessionId.value,
      title: "新对话",
      preview: "",
      workspaceId: workspaceId.value,
      workspaceTitle: workspaceTitle.value,
      cwd: cwd.value,
      workspaceKind: workspaceKind.value,
      sshHostId: sshHostId.value,
    });
  }

  function switchTo(id) {
    if (id === sessionId.value) return false;
    sessionId.value = id;
    persistActive();
    const local = conversations.value.find((c) => c.id === id);
    if (local) {
      applyWorkspaceMeta({
        workspace_id: local.workspaceId,
        workspace_title: local.workspaceTitle,
        cwd: local.cwd,
        workspace_kind: local.workspaceKind,
        ssh_host_id: local.sshHostId,
      });
      chatTitle.value = local.title || "新对话";
    }
    return true;
  }

  async function deleteConversation(id) {
    const list = loadLocalConvs().filter((c) => c.id !== id);
    saveLocalConvs(list);
    conversations.value = list;
    try {
      await fetch(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
    } catch {
      /* ignore */
    }
    return id === sessionId.value;
  }

  return {
    sessionId,
    conversations,
    chatTitle,
    sessionUsage,
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
