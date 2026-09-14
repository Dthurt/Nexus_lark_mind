import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
} from "@/api/client";
import type {
  AcceptPlanBody,
  AskAnswersBody,
  BrowseResult,
  ChannelDoc,
  ChatQueued,
  ChatSendBody,
  CreateSessionBody,
  GitInfo,
  InteractionPatchBody,
  MermaidRepairBody,
  MermaidRepairResult,
  EchartsRepairBody,
  EchartsRepairResult,
  DrawioRepairBody,
  DrawioRepairResult,
  Plugin,
  PluginCallRow,
  PluginConfigSchema,
  ProviderCatalog,
  ProviderDoc,
  ProviderEntry,
  SessionDetail,
  SessionSummary,
  SshConfigHostsData,
  SshHost,
  SshHostsListData,
  Tool,
  Workspace,
  WorkspacePatchBody,
  WorkspacesListData,
} from "@/types/api";

// ----- chat -----

export function postChat(body: ChatSendBody): Promise<ChatQueued> {
  return apiPost<ChatQueued>("/api/chat", body);
}

export function cancelChatTask(
  taskId: string,
  body?: { keep_inbox?: boolean },
): Promise<unknown> {
  return apiPost(`/api/chat/${encodeURIComponent(taskId)}/cancel`, body || {});
}

export function cancelSession(
  sessionId: string,
  body?: { keep_inbox?: boolean },
): Promise<unknown> {
  return apiPost(
    `/api/sessions/${encodeURIComponent(sessionId)}/cancel`,
    body || {},
  );
}

export function getSessionInbox(sessionId: string): Promise<{
  session_id: string;
  items: InboxItem[];
}> {
  return apiGet(`/api/sessions/${encodeURIComponent(sessionId)}/inbox`);
}

export function postSessionInbox(
  sessionId: string,
  body: { kind: "steer" | "queue"; content: string; source?: string },
): Promise<{ item: InboxItem; items: InboxItem[] }> {
  return apiPost(`/api/sessions/${encodeURIComponent(sessionId)}/inbox`, body);
}

export function deleteSessionInboxItem(
  sessionId: string,
  itemId: string,
): Promise<{ removed: InboxItem | null; items: InboxItem[] }> {
  return apiDelete(
    `/api/sessions/${encodeURIComponent(sessionId)}/inbox/${encodeURIComponent(itemId)}`,
  );
}

export type InboxItem = {
  id: string;
  kind: "steer" | "queue" | string;
  content: string;
  source?: string;
  created_at?: string;
};

export function repairMermaid(body: MermaidRepairBody): Promise<MermaidRepairResult> {
  return apiPost<MermaidRepairResult>("/api/mermaid/repair", body);
}

export function repairEcharts(body: EchartsRepairBody): Promise<EchartsRepairResult> {
  return apiPost<EchartsRepairResult>("/api/echarts/repair", body);
}

export function repairDrawio(body: DrawioRepairBody): Promise<DrawioRepairResult> {
  return apiPost<DrawioRepairResult>("/api/drawio/repair", body);
}

export function openChatStream(sessionId: string, afterEventId?: string): EventSource {
  const q = new URLSearchParams({ session_id: sessionId });
  if (afterEventId) q.set("after", afterEventId);
  return new EventSource(`/api/chat/stream?${q.toString()}`);
}

// ----- sessions -----

export function listSessions(): Promise<SessionSummary[]> {
  return apiGet<SessionSummary[]>("/api/sessions");
}

export function getSession(sessionId: string): Promise<SessionDetail | null> {
  return apiGet<SessionDetail | null>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export function createSession(body: CreateSessionBody): Promise<SessionDetail> {
  return apiPost<SessionDetail>("/api/sessions", body);
}

export function deleteSession(sessionId: string): Promise<unknown> {
  return apiDelete(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export function patchWorkspace(
  sessionId: string,
  body: WorkspacePatchBody,
): Promise<SessionDetail> {
  return apiPatch<SessionDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}/workspace`,
    body,
  );
}

export function patchInteraction(
  sessionId: string,
  body: InteractionPatchBody,
): Promise<SessionDetail> {
  return apiPatch<SessionDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}/interaction`,
    body,
  );
}

export function postSessionFile(
  sessionId: string,
  body: {
    name: string;
    path?: string;
    content?: string;
    mime?: string;
    url?: string;
    size?: number;
  },
): Promise<{ session_id?: string; file?: any }> {
  return apiPost(`/api/sessions/${encodeURIComponent(sessionId)}/files`, body);
}

/** Chat file card + optional ``.nlm/deliveries/`` write on local cwd. */
export function postSessionDelivery(
  sessionId: string,
  body: {
    name: string;
    content: string;
    cwd?: string;
    workspace_kind?: string;
    path?: string;
  },
): Promise<{
  session_id?: string;
  file?: any;
  workspace?: { ok?: boolean; path?: string; abs_path?: string; error?: string };
}> {
  return apiPost(`/api/sessions/${encodeURIComponent(sessionId)}/delivery`, body);
}

/** Persist Canvas doc under ``.nlm/canvases/`` (+ optional chat file card). */
export function postSessionCanvas(
  sessionId: string,
  body: {
    name: string;
    content: string;
    kind?: string;
    title?: string;
    cwd?: string;
    workspace_kind?: string;
  },
): Promise<{
  session_id?: string;
  file?: any;
  workspace?: { ok?: boolean; path?: string; abs_path?: string; error?: string };
  canvas?: { kind?: string; title?: string; body?: string };
}> {
  return apiPost(`/api/sessions/${encodeURIComponent(sessionId)}/canvas`, body);
}

/** Undo an applied write_file / edit_file (DiffDock reject). */
export function postDiffRevert(
  sessionId: string,
  body: {
    cwd: string;
    path: string;
    tool: string;
    workspace_kind?: string;
    created?: boolean;
    previous?: string;
    old_string?: string;
    new_string?: string;
    replace_all?: boolean;
  },
): Promise<{ ok?: boolean; path?: string; action?: string }> {
  return apiPost(`/api/sessions/${encodeURIComponent(sessionId || "_")}/diff-revert`, body);
}

export function getPluginCalls(
  sessionId: string,
  limit = 40,
): Promise<PluginCallRow[]> {
  return apiGet<PluginCallRow[]>(
    `/api/sessions/${encodeURIComponent(sessionId)}/plugin-calls?limit=${limit}`,
  );
}

export function postApprovals(
  sessionId: string,
  body: { call_id: string; action: string; reason?: string },
): Promise<unknown> {
  return apiPost(
    `/api/sessions/${encodeURIComponent(sessionId)}/approvals`,
    body,
  );
}

export function postAskAnswers(
  sessionId: string,
  body: AskAnswersBody,
): Promise<unknown> {
  return apiPost(
    `/api/sessions/${encodeURIComponent(sessionId)}/ask-answers`,
    body,
  );
}

export function acceptPlan(
  sessionId: string,
  body: AcceptPlanBody,
): Promise<ChatQueued> {
  return apiPost<ChatQueued>(
    `/api/sessions/${encodeURIComponent(sessionId)}/accept-plan`,
    body,
  );
}

// ----- workspaces -----

export function listWorkspaces(): Promise<WorkspacesListData> {
  return apiGet<WorkspacesListData>("/api/workspaces");
}

export function createWorkspace(body: {
  path: string;
  title?: string;
  kind?: "local" | "ssh" | string;
  ssh_host_id?: string;
}): Promise<Workspace> {
  return apiPost<Workspace>("/api/workspaces", body);
}

export function deleteWorkspace(id: string): Promise<{ deleted: string }> {
  return apiDelete<{ deleted: string }>(
    `/api/workspaces/${encodeURIComponent(id)}`,
  );
}

export function browseWorkspace(path = ""): Promise<BrowseResult> {
  const q = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiGet<BrowseResult>(`/api/workspaces/browse${q}`);
}

// ----- git -----

export function gitInfo(
  cwd: string,
  workspaceKind = "local",
): Promise<GitInfo> {
  return apiGet<GitInfo>(
    `/api/workspace/git-info?cwd=${encodeURIComponent(cwd)}&workspace_kind=${encodeURIComponent(workspaceKind)}`,
  );
}

// ----- ssh -----

export function listHosts(): Promise<SshHostsListData> {
  return apiGet<SshHostsListData>("/api/ssh/hosts");
}

export function upsertHost(form: Partial<SshHost> & {
  host?: string;
  username?: string;
  password?: string;
  private_key?: string;
  private_key_passphrase?: string;
}): Promise<SshHost> {
  return apiPost<SshHost>("/api/ssh/hosts", form);
}

export function testHost(hostId: string): Promise<Record<string, unknown>> {
  return apiPost<Record<string, unknown>>(
    `/api/ssh/hosts/${encodeURIComponent(hostId)}/test`,
  );
}

export function browseSsh(hostId: string, path = ""): Promise<BrowseResult> {
  const q = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiGet<BrowseResult>(
    `/api/ssh/hosts/${encodeURIComponent(hostId)}/browse${q}`,
  );
}

export function listSshConfigHosts(): Promise<SshConfigHostsData> {
  return apiGet<SshConfigHostsData>("/api/ssh/config/hosts");
}

export function importSshHost(body: {
  alias: string;
  label?: string;
  default_path?: string;
}): Promise<SshHost> {
  return apiPost<SshHost>("/api/ssh/hosts/import", body);
}

// ----- plugins -----

export function listPlugins(): Promise<Plugin[]> {
  return apiGet<Plugin[]>("/api/plugins");
}

export function listTools(): Promise<Tool[]> {
  return apiGet<Tool[]>("/api/tools");
}

export function enablePlugin(pluginId: string): Promise<unknown> {
  return apiPost(`/api/plugins/${encodeURIComponent(pluginId)}/enable`);
}

export function disablePlugin(pluginId: string): Promise<unknown> {
  return apiPost(`/api/plugins/${encodeURIComponent(pluginId)}/disable`);
}

export function reloadPlugins(): Promise<Plugin[]> {
  return apiPost<Plugin[]>("/api/plugins/reload");
}

export function reloadPlugin(pluginId: string): Promise<Plugin[]> {
  return apiPost<Plugin[]>(
    `/api/plugins/${encodeURIComponent(pluginId)}/reload`,
  );
}

export function getPluginConfig(pluginId: string): Promise<PluginConfigSchema> {
  return apiGet<PluginConfigSchema>(
    `/api/plugins/${encodeURIComponent(pluginId)}/config`,
  );
}

export function putPluginConfig(
  pluginId: string,
  values: Record<string, unknown>,
): Promise<PluginConfigSchema> {
  return apiPut<PluginConfigSchema>(
    `/api/plugins/${encodeURIComponent(pluginId)}/config`,
    { values },
  );
}

// ----- providers -----

/** Unwrap RpcEnvelope nesting when catalog is double-wrapped in `data`. */
export function normalizeProviderCatalog(raw: unknown): ProviderCatalog {
  const empty: ProviderCatalog = { default_provider: "", default_model: "", providers: [] };
  if (!raw || typeof raw !== "object") return empty;
  const rec = raw as Record<string, unknown>;
  if (rec.ok === true && rec.data != null) {
    return normalizeProviderCatalog(rec.data);
  }
  if (Array.isArray(rec.providers)) {
    return raw as ProviderCatalog;
  }
  const nested = rec.data;
  if (
    nested &&
    typeof nested === "object" &&
    Array.isArray((nested as ProviderCatalog).providers)
  ) {
    return nested as ProviderCatalog;
  }
  return empty;
}

export async function listProviders(configuredOnly = true): Promise<ProviderCatalog> {
  const raw = await apiGet<unknown>(
    `/api/providers?configured_only=${configuredOnly ? "true" : "false"}`,
  );
  return normalizeProviderCatalog(raw);
}

// ----- settings: models -----

export function getModelSettings(): Promise<ProviderDoc> {
  return apiGet<ProviderDoc>("/api/settings/models");
}

export function saveProvider(form: Partial<ProviderEntry> & { id: string }): Promise<ProviderEntry> {
  return apiPost<ProviderEntry>("/api/settings/models/providers", form);
}

export function removeProvider(id: string): Promise<unknown> {
  return apiDelete(`/api/settings/models/providers/${encodeURIComponent(id)}`);
}

export function setDefaultProvider(providerId: string): Promise<ProviderCatalog> {
  return apiPut("/api/settings/models/default", { provider_id: providerId });
}

export function discoverModels(body: {
  base_url?: string;
  api_key?: string;
  provider_id?: string;
}): Promise<{ models?: string[]; default_model?: string; [key: string]: unknown }> {
  return apiPost("/api/settings/models/discover", body);
}

export function testModel(body: {
  base_url?: string;
  api_key?: string;
  model?: string;
  provider_id?: string;
  api?: string;
}): Promise<{
  models_count?: number;
  chat_ok?: boolean;
  chat_error?: string;
  [key: string]: unknown;
}> {
  return apiPost("/api/settings/models/test", body);
}

// ----- settings: channels -----

export function getChannels(): Promise<ChannelDoc> {
  return apiGet<ChannelDoc>("/api/settings/channels");
}

export function saveFeishu(form: Record<string, unknown>): Promise<ChannelDoc> {
  return apiPut<ChannelDoc>("/api/settings/channels/feishu", form);
}

export function testFeishu(body: {
  app_id?: string;
  app_secret?: string;
} = {}): Promise<{ message?: string; [key: string]: unknown }> {
  return apiPost("/api/settings/channels/feishu/test", body);
}

export function reloadFeishu(): Promise<ChannelDoc> {
  return apiPost<ChannelDoc>("/api/settings/channels/feishu/reload");
}

export function saveDingTalk(form: Record<string, unknown>): Promise<ChannelDoc> {
  return apiPut<ChannelDoc>("/api/settings/channels/dingtalk", form);
}

export function testDingTalk(body: {
  client_id?: string;
  client_secret?: string;
} = {}): Promise<{ message?: string; [key: string]: unknown }> {
  return apiPost("/api/settings/channels/dingtalk/test", body);
}

export function reloadDingTalk(): Promise<ChannelDoc> {
  return apiPost<ChannelDoc>("/api/settings/channels/dingtalk/reload");
}

export function saveWeCom(form: Record<string, unknown>): Promise<ChannelDoc> {
  return apiPut<ChannelDoc>("/api/settings/channels/wecom", form);
}

export function testWeCom(body: {
  corp_id?: string;
  secret?: string;
  agent_id?: string;
} = {}): Promise<{ message?: string; [key: string]: unknown }> {
  return apiPost("/api/settings/channels/wecom/test", body);
}

export function reloadWeCom(): Promise<ChannelDoc> {
  return apiPost<ChannelDoc>("/api/settings/channels/wecom/reload");
}

// ----- teams / acp / plugin packages -----

export function getTeamSnapshot(teamId: string): Promise<any> {
  return apiGet(`/api/teams/${encodeURIComponent(teamId)}`);
}

export function postTeamDagNode(
  teamId: string,
  body: { label?: string; depends_on?: string[]; node_id?: string; meta?: Record<string, unknown> },
): Promise<any> {
  return apiPost(`/api/teams/${encodeURIComponent(teamId)}/dag`, body);
}

export function markTeamDagNode(
  teamId: string,
  nodeId: string,
  status: string,
): Promise<any> {
  return apiPost(
    `/api/teams/${encodeURIComponent(teamId)}/dag/${encodeURIComponent(nodeId)}/mark`,
    { status },
  );
}

export function installPluginPackage(body: { path: string }): Promise<any> {
  return apiPost("/api/plugins/install", body);
}

export type MarketplaceItem = {
  id: string;
  pack_id?: string;
  name?: string;
  kind?: string;
  version?: string;
  description?: string;
  source?: string;
  path?: string;
  installable?: boolean;
  installed?: boolean;
  action?: string;
  error?: string;
  has_sha256?: boolean;
  has_signature?: boolean;
};

export type MarketplaceCatalog = {
  items?: MarketplaceItem[];
  catalog_dir?: string;
  plugins_dir?: string;
  hints?: string[];
};

export function getPluginMarketplace(): Promise<MarketplaceCatalog> {
  return apiGet<MarketplaceCatalog>("/api/plugins/marketplace");
}

export async function installPluginZip(file: File): Promise<any> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/plugins/install", {
    method: "POST",
    body: form,
    credentials: "include",
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok || payload?.ok === false) {
    const { parseError } = await import("@/api/client");
    throw new Error(parseError(payload, `install failed (${res.status})`));
  }
  return payload?.data ?? payload;
}

export function listAcpBackends(): Promise<{ backends: string[] }> {
  return apiGet("/api/acp/backends");
}
