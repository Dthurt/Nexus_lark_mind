<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import Sidebar from "@/components/Sidebar.vue";
import Topbar from "@/components/Topbar.vue";
import ChatMessages from "@/components/ChatMessages.vue";
import Composer from "@/components/Composer.vue";
import TrajectoryView from "@/components/TrajectoryView.vue";
import RightDock from "@/components/RightDock.vue";
import { useProviders } from "@/composables/useProviders";
import { usePlugins } from "@/composables/usePlugins";
import { useSessions } from "@/composables/useSessions";
import { useWorkspaces } from "@/composables/useWorkspaces";
import { useChatTimeline } from "@/composables/useChatTimeline";
import { useTrajectory } from "@/composables/useTrajectory";
import { useRightDock } from "@/composables/useRightDock";

const props = defineProps({
  catalogTick: { type: Number, default: 0 },
});
const emit = defineEmits(["open-settings"]);

const status = ref("ready");
const busy = ref(false);
const input = ref("");
const gitBranch = ref("");
const gitInsertions = ref(0);
const gitDeletions = ref(0);
const toolsEnabled = ref(true);
const agentMode = ref(
  typeof localStorage !== "undefined" && localStorage.getItem("nlm_agent_mode") === "plan"
    ? "plan"
    : "agent"
);
const autoAccept = ref(
  typeof localStorage !== "undefined" && localStorage.getItem("nlm_auto_accept") === "1"
);
const multitask = ref(
  typeof localStorage === "undefined" || localStorage.getItem("nlm_multitask") !== "0"
);
const centerView = ref("chat");
const currentTaskId = ref(null);
const layout = ref({
  sidebarCollapsed: false,
  sidebarOpen: false,
  railOpen: false,
});
const narrowUi = ref(
  typeof window !== "undefined" ? window.matchMedia("(max-width: 1100px)").matches : false
);

const {
  providerId,
  modelName,
  providerOptions,
  modelOptions,
  providersDisabled,
  modelsDisabled,
  load: loadProviders,
  onProviderChange,
  onModelChange,
} = useProviders();

const {
  plugins,
  tools,
  error: pluginError,
  reloading,
  load: loadPlugins,
  toggle: togglePlugin,
  reload: reloadPlugins,
  saveConfig: savePluginConfig,
} = usePlugins();

const {
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
  startNew,
  switchTo,
  deleteConversation: deleteConv,
} = useSessions();

const { workspaces, load: loadWorkspaces } = useWorkspaces();

const {
  items,
  activityLog,
  highlightActivityId,
  clear: clearTimeline,
  clearActivity,
  pushActivity,
  inspectActivity,
  appendMessage,
  appendDelta,
  finalizeBot,
  beginAssistantTurn,
  setBotActivity,
  dismissLiveAssistant,
  showRetry,
  clearRetry,
  renderToolCall,
  renderToolResult,
  renderSubagentEvent,
  renderApproval,
  resolveApprovalLocal,
  renderAskUser,
  resolveAskLocal,
  renderTodos,
  renderPlanReview,
  resolvePlanReviewLocal,
  markPlanReady,
  clearPlanReadyFlags,
  loadFromHistory,
} = useChatTimeline();

const trajectory = useTrajectory();
const dock = useRightDock();

let es = null;
let turnOpen = false;

const appClass = computed(() => ({
  app: true,
  "sidebar-collapsed": layout.value.sidebarCollapsed,
  "rail-collapsed": dock.state.collapsed,
  "sidebar-open": layout.value.sidebarOpen,
  "rail-open": layout.value.railOpen,
}));

const showMask = computed(
  () => narrowUi.value && (layout.value.sidebarOpen || layout.value.railOpen)
);

function setStatus(text) {
  status.value = text;
}
function setBusy(v) {
  busy.value = v;
}

async function refreshGitBranch() {
  const path = (cwd.value || "").trim();
  if (!path || workspaceKind.value === "ssh") {
    gitBranch.value = "";
    gitInsertions.value = 0;
    gitDeletions.value = 0;
    return;
  }
  try {
    const resp = await fetch(
      `/api/workspace/git-info?cwd=${encodeURIComponent(path)}&workspace_kind=${encodeURIComponent(workspaceKind.value || "local")}`
    );
    const json = await resp.json();
    if (json?.ok) {
      gitBranch.value = json.data?.branch || "";
      gitInsertions.value = Number(json.data?.insertions || 0);
      gitDeletions.value = Number(json.data?.deletions || 0);
    } else {
      gitBranch.value = "";
      gitInsertions.value = 0;
      gitDeletions.value = 0;
    }
  } catch {
    gitBranch.value = "";
    gitInsertions.value = 0;
    gitDeletions.value = 0;
  }
}

watch([cwd, workspaceKind], () => {
  refreshGitBranch();
});

function shortToolName(name) {
  const raw = String(name || "tool");
  return raw.replace(/^builtin_workspace_/, "").replace(/^builtin_subagent_/, "").replace(/^cli_/, "").split(".").pop();
}

function setActivity(phase, label, detail = "") {
  setBotActivity(phase, label, detail);
}

function closeSSE() {
  if (es) {
    es.close();
    es = null;
  }
}

function ensureSSE() {
  if (es && es.readyState !== EventSource.CLOSED) return;
  closeSSE();
  es = new EventSource(`/api/chat/stream?session_id=${encodeURIComponent(sessionId.value)}`);
  es.onopen = () => setStatus("connected");
  es.onerror = () => setStatus("sse reconnecting…");
  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      const type = data.event_type;
      const payload = data.payload || {};
      if (data.task_id) currentTaskId.value = data.task_id;
      if (type === "task.started") {
        clearRetry();
        if (!turnOpen) {
          trajectory.startTurn();
          turnOpen = true;
        }
        setBusy(true);
        setStatus("thinking…");
        setActivity("model", "正在调用模型…", modelName.value || "");
      } else if (type === "task.status") {
        showRetry(payload.message || "处理中…");
        trajectory.addStatus(payload.message || "处理中…");
        setActivity("retry", payload.message || "模型限流，重试中…");
      } else if (type === "task.tool_call") {
        clearRetry();
        const actId = pushActivity("CALL", payload);
        renderToolCall(payload, actId);
        trajectory.addToolCall(payload, actId);
        const tname = shortToolName(payload.name);
        setStatus("tool call…");
        if (["subagent", "subagent_fork", "send_message"].includes(tname)) {
          setActivity(
            "subagent",
            "正在启动子 agent…",
            payload.arguments?.description || tname
          );
        } else {
          setActivity("tool", "正在调用工具…", tname);
        }
      } else if (type === "task.tool_result") {
        const actId = pushActivity("RESULT", payload);
        renderToolResult(payload, actId);
        trajectory.addToolResult(payload, actId);
        setStatus("tool result…");
        setActivity("model", "正在调用模型…", modelName.value || "");
      } else if (type === "task.tool_approval") {
        clearRetry();
        const actId = pushActivity("APPROVE", payload);
        renderApproval(payload, actId);
        trajectory.addStatus(`approval ${payload.name || payload.base || ""}`);
        setStatus("waiting approval…");
        setActivity("tool", "等待你批准工具…", payload.name || payload.base || "");
      } else if (type === "task.ask_user") {
        clearRetry();
        const actId = pushActivity("ASK", payload);
        renderAskUser(payload, actId);
        trajectory.addStatus("ask_user");
        setStatus("waiting ask…");
        setActivity("tool", "等待你回答…", payload.title || "");
      } else if (type === "task.plan_review") {
        clearRetry();
        const actId = pushActivity("PLAN", payload);
        renderPlanReview(payload, actId);
        trajectory.addStatus("plan_review");
        setStatus("waiting plan review…");
        setActivity("tool", "等待审阅计划…", "");
      } else if (type === "task.plan_mode") {
        if (payload.active === false) {
          agentMode.value = "agent";
          localStorage.setItem("nlm_agent_mode", "agent");
          syncInteraction({ agent_mode: "agent", plan_status: "accepted" });
          clearPlanReadyFlags();
          setActivity("model", "计划已批准，开始执行…", "");
        }
      } else if (type === "task.todos") {
        clearRetry();
        const actId = pushActivity("TODOS", payload);
        renderTodos(payload, actId);
        trajectory.addStatus("todos");
        setStatus("todos…");
      } else if (type === "task.plan_ready") {
        markPlanReady(payload.content || "");
        setActivity("model", "计划已就绪，可接受并执行", "");
      } else if (type === "task.subagent") {
        clearRetry();
        const actId = pushActivity("SUB", payload);
        renderSubagentEvent(payload, actId);
        const subLabel = payload.label || payload.subagent_id || "";
        trajectory.addStatus(
          payload.phase === "start"
            ? `subagent ${subLabel}…`
            : payload.phase === "end"
              ? `subagent done (${payload.status || "ok"})`
              : `subagent ${payload.phase}`
        );
        setStatus("subagent…");
        if (payload.phase === "start") {
          setActivity("subagent", "子 agent 运行中…", subLabel);
        } else if (payload.phase === "delta") {
          setActivity("subagent", "子 agent 输出中…", subLabel);
        } else if (payload.phase === "tool_call") {
          setActivity(
            "subagent",
            "子 agent 调用工具…",
            shortToolName(payload.tool_call?.name || payload.name) || subLabel
          );
        } else if (payload.phase === "tool_result") {
          setActivity("subagent", "子 agent 运行中…", subLabel);
        } else if (payload.phase === "end") {
          setActivity("model", "正在调用模型…", modelName.value || "");
        }
      } else if (type === "task.delta") {
        clearRetry();
        appendDelta(payload.delta || "");
        setStatus("streaming…");
        setActivity("stream", "正在生成回复…");
      } else if (type === "task.completed") {
        clearRetry();
        finalizeBot(payload.content || undefined, payload.usage);
        if (agentMode.value === "plan") markPlanReady(payload.content || "");
        trajectory.addAssistant(payload.content || "", payload.usage);
        trajectory.endTurn(payload.session_usage || payload.usage);
        turnOpen = false;
        if (payload.session_usage) sessionUsage.value = payload.session_usage;
        currentTaskId.value = null;
        setStatus("ready");
        setBusy(false);
        syncServerList();
        loadActivityFromServer();
        refreshGitBranch();
      } else if (type === "task.failed") {
        clearRetry();
        const err = payload.error || "unknown";
        if (payload.cancelled) {
          if (payload.partial) {
            finalizeBot(payload.partial);
            trajectory.addAssistant(payload.partial);
          } else {
            dismissLiveAssistant();
          }
          appendMessage("assistant", "已停止生成。", { rich: false });
          trajectory.addError("已停止生成");
          setStatus("stopped");
        } else {
          dismissLiveAssistant();
          appendMessage(
            "assistant",
            err.includes("限流") || err.includes("429") ? `⚠️ ${err}` : `错误：${err}`,
            { rich: false }
          );
          trajectory.addError(err);
          setStatus("error");
        }
        trajectory.endTurn();
        turnOpen = false;
        currentTaskId.value = null;
        setBusy(false);
      }
    } catch {
      /* ignore */
    }
  };
}

async function loadActivityFromServer() {
  try {
    const resp = await fetch(
      `/api/sessions/${encodeURIComponent(sessionId.value)}/plugin-calls?limit=40`
    );
    const json = await resp.json();
    if (!json.ok || !Array.isArray(json.data)) return;
    const mapped = json.data.map((row) => ({
      id: row.call_id,
      kind: row.success ? "RESULT" : "ERROR",
      name: row.tool_name || row.plugin_id,
      detail: row.success ? row.result : row.error || row.arguments,
      callId: row.call_id,
      at: row.created_at ? Date.parse(row.created_at) : Date.now(),
    }));
    if (mapped.length) activityLog.value = mapped;
  } catch {
    /* ignore */
  }
}

async function refreshFromServer() {
  const data = await fetchSession();
  if (data && Array.isArray(data.messages) && data.messages.length) {
    loadFromHistory(data.messages);
    trajectory.loadFromHistory(data.messages);
    chatTitle.value = data.title || "对话";
    sessionUsage.value = data.usage || {};
    upsertLocalConv({
      id: sessionId.value,
      title: data.title || "对话",
      preview: data.messages.find((m) => m.role === "user")?.content || "",
      updatedAt: data.updated_at || new Date().toISOString(),
      workspaceId: data.workspace_id || "",
      workspaceTitle: data.workspace_title || "",
      cwd: data.cwd || "",
    });
  } else {
    clearTimeline();
    trajectory.clear();
    chatTitle.value = "新对话";
    sessionUsage.value = data?.usage || {};
  }
  turnOpen = false;
  await loadActivityFromServer();
}

function startNewConversation() {
  closeSSE();
  startNew();
  clearTimeline();
  clearActivity();
  trajectory.clear();
  turnOpen = false;
  currentTaskId.value = null;
  ensureSSE();
  setStatus("ready");
  setBusy(false);
}

async function startConversationWithWorkspace(ws) {
  closeSSE();
  startNew({
    workspace_id: ws.id,
    workspace_title: ws.title,
    cwd: ws.path,
    workspace_kind: ws.kind || "local",
    ssh_host_id: ws.ssh_host_id || "",
  });
  clearTimeline();
  clearActivity();
  trajectory.clear();
  turnOpen = false;
  currentTaskId.value = null;
  try {
    await ensureSessionOnServer({ workspace_id: ws.id });
  } catch (err) {
    setStatus(String(err.message || err));
  }
  ensureSSE();
  setStatus("ready");
  setBusy(false);
  await loadWorkspaces();
}

async function onPickWorkspace(ws) {
  if (items.value.length) {
    await startConversationWithWorkspace(ws);
    return;
  }
  if (cwd.value) {
    // already bound empty session — replace via bind
    try {
      await bindWorkspace({ workspace_id: ws.id });
      setStatus("workspace ready");
    } catch (err) {
      await startConversationWithWorkspace(ws);
    }
  } else {
    try {
      await ensureSessionOnServer({ workspace_id: ws.id });
      setStatus("workspace ready");
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }
  await loadWorkspaces();
}

async function switchConversation(id) {
  if (!switchTo(id)) return;
  closeSSE();
  currentTaskId.value = null;
  setBusy(false);
  ensureSSE();
  await refreshFromServer();
}

async function onDeleteConversation(id) {
  const wasActive = await deleteConv(id);
  if (wasActive) startNewConversation();
}

async function clearSession() {
  clearTimeline();
  trajectory.clear();
  try {
    await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}`, { method: "DELETE" });
  } catch {
    /* ignore */
  }
  chatTitle.value = "新对话";
  upsertLocalConv({
    id: sessionId.value,
    title: "新对话",
    preview: "",
    workspaceId: workspaceId.value,
    workspaceTitle: workspaceTitle.value,
    cwd: cwd.value,
  });
  sessionUsage.value = {};
  clearActivity();
  setStatus("cleared");
}

function toggleSidebar() {
  if (window.matchMedia("(max-width: 820px)").matches) {
    layout.value.railOpen = false;
    layout.value.sidebarOpen = !layout.value.sidebarOpen;
  } else {
    layout.value.sidebarCollapsed = !layout.value.sidebarCollapsed;
  }
}

function toggleRail() {
  if (narrowUi.value || window.matchMedia("(max-width: 1100px)").matches) {
    layout.value.sidebarOpen = false;
    layout.value.railOpen = !layout.value.railOpen;
    if (layout.value.railOpen) dock.expand();
  } else {
    // Desktop: side dock only — never dim the workbench with the overlay mask.
    dock.toggleCollapsed();
    layout.value.railOpen = false;
  }
}

function closeOverlays() {
  layout.value.sidebarOpen = false;
  layout.value.railOpen = false;
}

function onInspectTool(activityId) {
  inspectActivity(activityId);
  dock.openActivity(activityId);
  if (window.matchMedia("(max-width: 1100px)").matches) layout.value.railOpen = true;
}

function onTrajectoryInspect(row) {
  trajectory.select(row.id);
  dock.openInspector(row);
  if (row.activityId) {
    inspectActivity(row.activityId);
    dock.highlightActivityId.value = row.activityId;
  }
  // Details live in the right Dock inspector — surface it if hidden.
  if (narrowUi.value || window.matchMedia("(max-width: 1100px)").matches) {
    layout.value.railOpen = true;
    dock.expand();
  } else if (dock.state.collapsed) {
    dock.expand();
    layout.value.railOpen = false;
  }
}

async function stopGeneration() {
  const tid = currentTaskId.value;
  try {
    if (tid) {
      await fetch(`/api/chat/${encodeURIComponent(tid)}/cancel`, { method: "POST" });
    } else {
      await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}/cancel`, {
        method: "POST",
      });
    }
    setStatus("stopping…");
    setActivity("stop", "正在停止…");
  } catch (err) {
    setStatus(String(err));
    setBusy(false);
  }
}

async function syncInteraction(patch = {}) {
  try {
    await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}/interaction`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
  } catch {
    /* ignore */
  }
}

watch(agentMode, (v) => {
  try {
    localStorage.setItem("nlm_agent_mode", v);
  } catch {
    /* ignore */
  }
  syncInteraction({ agent_mode: v, plan_status: v === "plan" ? "drafting" : "idle" });
  if (v !== "plan") clearPlanReadyFlags();
});

watch(autoAccept, (v) => {
  try {
    localStorage.setItem("nlm_auto_accept", v ? "1" : "0");
  } catch {
    /* ignore */
  }
  syncInteraction({ auto_accept: !!v });
});

watch(multitask, (v) => {
  try {
    localStorage.setItem("nlm_multitask", v ? "1" : "0");
  } catch {
    /* ignore */
  }
});

async function onResolveApproval({ item, action }) {
  if (!item?.callId) return;
  const act = action || "allow";
  try {
    await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}/approvals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ call_id: item.callId, action: act }),
    });
    if (act === "allow_session" || act === "always") {
      autoAccept.value = true;
    }
    resolveApprovalLocal(item.callId, act === "deny" ? "denied" : "allowed");
    setActivity("model", "正在调用模型…", modelName.value || "");
  } catch (err) {
    appendMessage("assistant", `审批失败：${err}`, { rich: false });
  }
}

async function onResolveAsk({ item, action, answers }) {
  if (!item?.callId) return;
  try {
    await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}/ask-answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        call_id: item.callId,
        action: action || "submit",
        answers: answers || {},
      }),
    });
    resolveAskLocal(
      item.callId,
      action === "deny" ? "dismissed" : "answered",
      answers || null
    );
    setActivity("model", "正在调用模型…", modelName.value || "");
  } catch (err) {
    appendMessage("assistant", `提交回答失败：${err}`, { rich: false });
  }
}

async function onResolvePlanReview({ item, action, feedback }) {
  if (!item?.callId) return;
  const act = (action || "deny").toLowerCase();
  try {
    await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}/ask-answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        call_id: item.callId,
        action: act === "approve" ? "approve" : act === "keep_planning" ? "keep_planning" : "deny",
        feedback: feedback || "",
        reason: feedback || "",
      }),
    });
    const status =
      act === "approve" ? "approved" : act === "keep_planning" ? "keep_planning" : "dismissed";
    resolvePlanReviewLocal(item.callId, status);
    if (act === "approve") {
      agentMode.value = "agent";
      localStorage.setItem("nlm_agent_mode", "agent");
      setActivity("model", "计划已批准，开始执行…", modelName.value || "");
    } else {
      setActivity("model", "正在调用模型…", modelName.value || "");
    }
  } catch (err) {
    appendMessage("assistant", `计划审阅提交失败：${err}`, { rich: false });
  }
}

async function onAcceptPlan() {
  if (busy.value) return;
  clearPlanReadyFlags();
  agentMode.value = "agent";
  ensureSSE();
  setBusy(true);
  setStatus("accepting plan…");
  beginAssistantTurn({
    phase: "send",
    label: "正在按计划执行…",
    detail: "",
    startedAt: Date.now(),
  });
  try {
    const resp = await fetch(`/api/sessions/${encodeURIComponent(sessionId.value)}/accept-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tools_enabled: !!toolsEnabled.value,
        model_provider: providerId.value || undefined,
        model_name: modelName.value || undefined,
        workspace_id: workspaceId.value || undefined,
        cwd: cwd.value || undefined,
        workspace_kind: workspaceKind.value || undefined,
        ssh_host_id: sshHostId.value || undefined,
        auto_accept: !!autoAccept.value,
      }),
    });
    const json = await resp.json();
    if (!json.ok) {
      dismissLiveAssistant();
      appendMessage("assistant", json.error?.message || "接受计划失败", { rich: false });
      setBusy(false);
      setStatus("error");
      return;
    }
    if (json.data?.task_id) currentTaskId.value = json.data.task_id;
    setStatus("queued");
    setActivity("model", "正在调用模型…", modelName.value || "");
  } catch (err) {
    dismissLiveAssistant();
    appendMessage("assistant", String(err), { rich: false });
    setBusy(false);
    setStatus("error");
  }
}

async function sendMessage() {
  const content = input.value.trim();
  if (!content || busy.value) return;
  ensureSSE();
  const draft = content;
  input.value = "";
  appendMessage("user", draft, { rich: false });
  if (!turnOpen) {
    trajectory.startTurn();
    turnOpen = true;
  }
  trajectory.addUser(draft);
  upsertLocalConv({
    id: sessionId.value,
    title: draft.slice(0, 36) + (draft.length > 36 ? "…" : ""),
    preview: draft.slice(0, 80),
    updatedAt: new Date().toISOString(),
    workspaceId: workspaceId.value,
    workspaceTitle: workspaceTitle.value,
    cwd: cwd.value,
  });
  chatTitle.value = draft.slice(0, 36) + (draft.length > 36 ? "…" : "");
  setBusy(true);
  setStatus("sending…");
  beginAssistantTurn({
    phase: "send",
    label: "正在发送…",
    detail: "",
    startedAt: Date.now(),
  });
  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: draft,
        session_id: sessionId.value,
        stream: true,
        tools_enabled: !!toolsEnabled.value,
        agent_mode: agentMode.value || "agent",
        auto_accept: !!autoAccept.value,
        multitask: !!multitask.value,
        model_provider: providerId.value || undefined,
        model_name: modelName.value || undefined,
        workspace_id: workspaceId.value || undefined,
        cwd: cwd.value || undefined,
        workspace_kind: workspaceKind.value || undefined,
        ssh_host_id: sshHostId.value || undefined,
      }),
    });
    const json = await resp.json();
    if (!json.ok) {
      dismissLiveAssistant();
      appendMessage("assistant", json.error?.message || "请求失败", { rich: false });
      trajectory.addError(json.error?.message || "请求失败");
      if (!input.value.trim()) input.value = draft;
      setBusy(false);
      setStatus("error");
      return;
    }
    if (json.data?.task_id) currentTaskId.value = json.data.task_id;
    if (json.data?.session_id && json.data.session_id !== sessionId.value) {
      sessionId.value = json.data.session_id;
      localStorage.setItem("nlm_session_id", sessionId.value);
      closeSSE();
      ensureSSE();
    }
    setStatus("queued");
    setActivity("model", "正在调用模型…", modelName.value || "");
  } catch (err) {
    dismissLiveAssistant();
    appendMessage("assistant", String(err), { rich: false });
    trajectory.addError(String(err));
    if (!input.value.trim()) input.value = draft;
    setBusy(false);
    setStatus("error");
  }
}

async function onTogglePlugin(pluginId, enabled) {
  try {
    await togglePlugin(pluginId, enabled);
  } catch (err) {
    setStatus(String(err));
    await loadPlugins();
  }
}

async function onSavePluginConfig(pluginId, values) {
  try {
    await savePluginConfig(pluginId, values);
    setStatus(`已保存 ${pluginId} 配置`);
  } catch (err) {
    setStatus(String(err));
    throw err;
  }
}

async function onReloadAll() {
  try {
    await reloadPlugins(null);
    setStatus("plugins reloaded");
  } catch (err) {
    setStatus(String(err));
  }
}

async function onReloadOne(pluginId) {
  try {
    await reloadPlugins(pluginId);
    setStatus(`reloaded ${pluginId}`);
  } catch (err) {
    setStatus(String(err));
  }
}

async function onRetryPlugin(pluginId) {
  try {
    await togglePlugin(pluginId, true);
    setStatus(`retry enabled ${pluginId}`);
  } catch {
    try {
      await reloadPlugins(pluginId);
      await togglePlugin(pluginId, true);
    } catch (err) {
      setStatus(String(err));
    }
  }
}

onMounted(async () => {
  const mq = window.matchMedia("(max-width: 1100px)");
  const syncNarrow = () => {
    narrowUi.value = mq.matches;
    // Leaving overlay mode: clear mask flag so desktop never stays dimmed.
    if (!mq.matches) layout.value.railOpen = false;
  };
  syncNarrow();
  mq.addEventListener("change", syncNarrow);
  onBeforeUnmount(() => mq.removeEventListener("change", syncNarrow));

  ensureSSE();
  await Promise.all([loadProviders(), loadPlugins(), syncServerList(), loadWorkspaces()]);
  await refreshFromServer();
  await refreshGitBranch();
});

watch(
  () => props.catalogTick,
  () => {
    loadProviders();
  }
);

onBeforeUnmount(() => {
  closeSSE();
});
</script>

<template>
  <div class="atmosphere" aria-hidden="true" />
  <div v-if="showMask" class="workbench-mask" aria-hidden="true" @click="closeOverlays" />
  <div :class="appClass">
    <Sidebar
      :conversations="conversations"
      :workspaces="workspaces"
      :active-id="sessionId"
      :status="status"
      @new="startNewConversation"
      @select="switchConversation"
      @delete="onDeleteConversation"
      @open-workspace="startConversationWithWorkspace"
      @open-settings="emit('open-settings')"
    />

    <main class="workspace">
      <Topbar
        :title="chatTitle"
        :session-id="sessionId"
        :center-view="centerView"
        :workspace-title="workspaceTitle"
        :cwd="cwd"
        :workspace-kind="workspaceKind"
        @update:center-view="centerView = $event"
        @toggle-sidebar="toggleSidebar"
        @toggle-rail="toggleRail"
        @clear="clearSession"
      />

      <section class="chat-panel" aria-label="对话">
        <ChatMessages
          v-show="centerView === 'chat'"
          :items="items"
          :show-workspace-picker="!cwd"
          :model-provider="providerId"
          :model-name="modelName"
          @inspect-tool="onInspectTool"
          @pick-workspace="onPickWorkspace"
          @resolve-approval="onResolveApproval"
          @resolve-ask="onResolveAsk"
          @resolve-plan-review="onResolvePlanReview"
          @accept-plan="onAcceptPlan"
        />
        <TrajectoryView
          v-show="centerView === 'trajectory'"
          :rows="trajectory.rows.value"
          :follow-tail="trajectory.followTail.value"
          :selected-id="trajectory.selectedId.value"
          @update:follow-tail="trajectory.followTail.value = $event"
          @select="trajectory.select"
          @inspect="onTrajectoryInspect"
        />
        <Composer
          v-model="input"
          :provider-id="providerId"
          :model-name="modelName"
          :provider-options="providerOptions"
          :model-options="modelOptions"
          :providers-disabled="providersDisabled"
          :models-disabled="modelsDisabled"
          v-model:tools-enabled="toolsEnabled"
          v-model:agent-mode="agentMode"
          v-model:auto-accept="autoAccept"
          v-model:multitask="multitask"
          :session-usage="sessionUsage"
          :items="items"
          :tools="tools"
          :cwd="cwd"
          :workspace-title="workspaceTitle"
          :workspace-kind="workspaceKind"
          :git-branch="gitBranch"
          :git-insertions="gitInsertions"
          :git-deletions="gitDeletions"
          :busy="busy"
          @update:provider-id="onProviderChange"
          @update:model-name="onModelChange"
          @send="sendMessage"
          @stop="stopGeneration"
        />
      </section>
    </main>

    <RightDock
      :dock="dock"
      :plugins="plugins"
      :tools="tools"
      :activity="activityLog"
      :usage="sessionUsage"
      :plugin-error="pluginError"
      :reloading="reloading"
      :highlight-activity-id="dock.highlightActivityId.value || highlightActivityId"
      :inspector-payload="dock.inspectorPayload.value"
      @toggle-plugin="onTogglePlugin"
      @reload="onReloadAll"
      @reload-one="onReloadOne"
      @retry-plugin="onRetryPlugin"
      @save-plugin-config="onSavePluginConfig"
    />
  </div>
</template>
