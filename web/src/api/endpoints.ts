import { apiDelete, apiGet, apiPatch, apiPost, apiPut, parseError } from "@/api/client";
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

export function persistTurnError(
  sessionId: string,
  body: {
    error: string;
    user_content?: string;
    task_id?: string;
    cancelled?: boolean;
    partial?: string;
  },
): Promise<SessionDetail | null> {
  return apiPost<SessionDetail | null>(
    `/api/sessions/${encodeURIComponent(sessionId)}/turn-error`,
    body,
  );
}

export function createSession(body: CreateSessionBody): Promise<SessionDetail> {
  return apiPost<SessionDetail>("/api/sessions", body);
}

export function forkSession(
  sessionId: string,
  body: { until_index?: number; title?: string } = {},
): Promise<SessionDetail> {
  return apiPost<SessionDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}/fork`,
    body,
  );
}

export function listSkills(cwd: string): Promise<{
  skills: { name: string; description: string; path: string }[];
  cwd?: string;
}> {
  const q = new URLSearchParams({ cwd });
  return apiGet(`/api/skills?${q.toString()}`);
}

export function listPrompts(cwd = ""): Promise<{
  prompts: {
    name: string;
    description: string;
    path: string;
    variables?: string[];
    slash?: string;
  }[];
}> {
  const q = new URLSearchParams();
  if (cwd) q.set("cwd", cwd);
  const qs = q.toString();
  return apiGet(`/api/prompts${qs ? `?${qs}` : ""}`);
}

export function listPresets(cwd = ""): Promise<{
  presets: {
    name: string;
    description: string;
    path: string;
    permission_preset?: string;
    reasoning_effort?: string;
    active_tools?: string[] | null;
    model?: string;
    provider?: string;
  }[];
}> {
  const q = new URLSearchParams();
  if (cwd) q.set("cwd", cwd);
  const qs = q.toString();
  return apiGet(`/api/presets${qs ? `?${qs}` : ""}`);
}

export type SessionTreeNode = {
  session_id: string;
  title?: string;
  parent_id?: string | null;
  fork_point_index?: number | null;
  updated_at?: string;
  bookmarks?: { message_index: number; label?: string }[];
  children?: SessionTreeNode[];
};

export function getSessionTree(workspaceId = ""): Promise<{
  roots: SessionTreeNode[];
  node_count?: number;
  root_count?: number;
}> {
  const q = new URLSearchParams();
  if (workspaceId) q.set("workspace_id", workspaceId);
  const qs = q.toString();
  return apiGet(`/api/sessions/tree${qs ? `?${qs}` : ""}`);
}

export function reforkSession(
  sessionId: string,
  body: { title?: string } = {},
): Promise<SessionDetail> {
  return apiPost<SessionDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}/refork`,
    body,
  );
}

export function addSessionBookmark(
  sessionId: string,
  body: { message_index: number; label?: string },
): Promise<{ bookmarks?: { message_index: number; label?: string }[] }> {
  return apiPost(
    `/api/sessions/${encodeURIComponent(sessionId)}/bookmarks`,
    body,
  );
}

export function deleteSessionBookmark(
  sessionId: string,
  messageIndex: number,
): Promise<{ bookmarks?: { message_index: number; label?: string }[] }> {
  return apiDelete(
    `/api/sessions/${encodeURIComponent(sessionId)}/bookmarks/${messageIndex}`,
  );
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

export async function uploadSessionDoc(
  sessionId: string,
  file: File,
  workspaceId = "",
): Promise<SessionUploadDoc> {
  const form = new FormData();
  form.append("file", file);
  if (workspaceId) form.append("workspace_id", workspaceId);
  const qs = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : "";
  const resp = await fetch(
    `/api/sessions/${encodeURIComponent(sessionId)}/uploads${qs}`,
    { method: "POST", body: form },
  );
  const json = await resp.json().catch(() => null);
  if (!resp.ok || !json?.ok) {
    throw new Error(parseError(json, `HTTP ${resp.status}`));
  }
  return json.data as SessionUploadDoc;
}

export function listSessionUploads(
  sessionId: string,
): Promise<{ docs: SessionUploadDoc[]; session_id?: string }> {
  return apiGet(
    `/api/sessions/${encodeURIComponent(sessionId)}/uploads`,
  );
}

export function deleteSessionUpload(
  sessionId: string,
  docId: string,
): Promise<{ ok?: boolean; doc_id?: string }> {
  return apiDelete(
    `/api/sessions/${encodeURIComponent(sessionId)}/uploads/${encodeURIComponent(docId)}`,
  );
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

export function patchWorkspaceRecord(
  id: string,
  body: { trusted?: boolean },
): Promise<Workspace> {
  return apiPatch<Workspace>(
    `/api/workspaces/${encodeURIComponent(id)}`,
    body,
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

// ----- Knowledge base -----

export type KnowledgeDoc = {
  doc_id: string;
  title?: string;
  content?: string;
  content_len?: number;
  tags?: string;
  source?: string;
  source_uri?: string;
  content_hash?: string;
  workspace_id?: string;
  updated_at?: string | null;
  snippet?: string;
  score?: number;
  chunk_id?: string;
  heading?: string;
  citation?: string;
};

export type KnowledgeHit = KnowledgeDoc & {
  chunk_id?: string;
  chunk_index?: number;
  heading?: string;
  snippet?: string;
  score?: number;
  citation?: string;
};

export type KnowledgeStats = {
  docs: number;
  chunks: number;
  chunks_with_embedding: number;
  embeddings_configured: boolean;
  embedding_model?: string;
  hybrid_ready: boolean;
  fts5?: boolean;
  fts5_tokenizer?: string;
};

export type SessionUploadDoc = KnowledgeDoc & {
  filename?: string;
  bytes?: number;
  session_id?: string;
};

export type KnowledgeSyncEntry = {
  id?: number;
  source?: string;
  source_uri?: string;
  content_hash?: string;
  status?: string;
  message?: string;
  workspace_id?: string;
  created_at?: string | null;
};

export function listKnowledgeDocs(params?: {
  workspace_id?: string;
  limit?: number;
}): Promise<{ docs: KnowledgeDoc[] }> {
  const q = new URLSearchParams();
  if (params?.workspace_id) q.set("workspace_id", params.workspace_id);
  if (params?.limit != null) q.set("limit", String(params.limit));
  const qs = q.toString();
  return apiGet(`/api/knowledge/docs${qs ? `?${qs}` : ""}`);
}

export function searchKnowledge(params: {
  query: string;
  workspace_id?: string;
  limit?: number;
}): Promise<{ query: string; results: KnowledgeHit[]; citations_md?: string }> {
  const q = new URLSearchParams();
  q.set("query", params.query);
  if (params.workspace_id) q.set("workspace_id", params.workspace_id);
  if (params.limit != null) q.set("limit", String(params.limit));
  return apiGet(`/api/knowledge/search?${q.toString()}`);
}

export function getKnowledgeStats(params?: {
  workspace_id?: string;
}): Promise<KnowledgeStats> {
  const q = new URLSearchParams();
  if (params?.workspace_id) q.set("workspace_id", params.workspace_id);
  const qs = q.toString();
  return apiGet(`/api/knowledge/stats${qs ? `?${qs}` : ""}`);
}

export function getKnowledgeDoc(
  docId: string,
  includeChunks = false,
): Promise<KnowledgeDoc> {
  const q = includeChunks ? "?include_chunks=true" : "";
  return apiGet(`/api/knowledge/docs/${encodeURIComponent(docId)}${q}`);
}

export function addKnowledgeDoc(body: {
  title?: string;
  content?: string;
  path?: string;
  tags?: string;
  doc_id?: string;
  source?: string;
  workspace_id?: string;
  cwd?: string;
}): Promise<KnowledgeDoc> {
  return apiPost("/api/knowledge/docs", body);
}

export async function uploadKnowledgeFile(
  file: File,
  workspaceId = "",
  title = "",
): Promise<KnowledgeDoc> {
  const form = new FormData();
  form.append("file", file);
  if (workspaceId) form.append("workspace_id", workspaceId);
  if (title) form.append("title", title);
  const qs = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : "";
  const resp = await fetch(`/api/knowledge/docs/file${qs}`, {
    method: "POST",
    body: form,
  });
  const json = await resp.json().catch(() => null);
  if (!resp.ok || !json?.ok) {
    throw new Error(parseError(json, `HTTP ${resp.status}`));
  }
  return json.data as KnowledgeDoc;
}

export function patchKnowledgeDoc(
  docId: string,
  body: {
    title?: string;
    content?: string;
    tags?: string;
    source?: string;
    source_uri?: string;
  },
): Promise<KnowledgeDoc> {
  return apiPatch(`/api/knowledge/docs/${encodeURIComponent(docId)}`, body);
}

export function deleteKnowledgeDoc(
  docId: string,
): Promise<{ ok: boolean; doc_id: string }> {
  return apiDelete(`/api/knowledge/docs/${encodeURIComponent(docId)}`);
}

export function reindexKnowledge(body?: {
  workspace_id?: string;
  limit?: number;
}): Promise<{
  ok?: boolean;
  updated?: number;
  scanned?: number;
  error?: string;
  errors?: string[];
}> {
  return apiPost("/api/knowledge/reindex", body || {});
}

export function syncKnowledgeDocs(body: {
  cwd: string;
  workspace_id?: string;
  max_files?: number;
}): Promise<{
  scanned?: number;
  added?: number;
  updated?: number;
  skipped?: number;
  errors?: string[];
}> {
  return apiPost("/api/knowledge/sync/docs", body);
}

export function listKnowledgeSyncLog(params?: {
  workspace_id?: string;
  limit?: number;
}): Promise<{ entries: KnowledgeSyncEntry[] }> {
  const q = new URLSearchParams();
  if (params?.workspace_id) q.set("workspace_id", params.workspace_id);
  if (params?.limit != null) q.set("limit", String(params.limit));
  const qs = q.toString();
  return apiGet(`/api/knowledge/sync/log${qs ? `?${qs}` : ""}`);
}

export type WeknoraHealth = {
  ok?: boolean;
  online?: boolean;
  skipped?: boolean;
  latency_ms?: number | null;
  kb_count?: number | null;
  configured?: boolean;
  default_kb_id?: string;
  ingest_enabled?: boolean;
  error?: string;
  reason?: string;
};

export type WeknoraKb = {
  id: string;
  name: string;
  description?: string;
  doc_count?: number | null;
  updated_at?: string;
};

export function getWeknoraHealth(): Promise<WeknoraHealth> {
  return apiGet("/api/knowledge/weknora/health");
}

export function listWeknoraKbs(limit = 50): Promise<{
  knowledge_bases?: WeknoraKb[];
  default_kb_id?: string;
  count?: number;
  skipped?: boolean;
  reason?: string;
  error?: string;
}> {
  return apiGet(`/api/knowledge/weknora/kbs?limit=${limit}`);
}

export type WeknoraHit = {
  title?: string;
  snippet?: string;
  source_uri?: string;
  score?: number | null;
  doc_id?: string;
  citation?: string;
  source?: string;
  kb_id?: string;
};

export function searchWeknora(body: {
  query: string;
  limit?: number;
  kb_id?: string;
  kb_ids?: string[];
  workspace_id?: string;
  weknora_kb_id?: string;
}): Promise<{
  query?: string;
  results?: WeknoraHit[];
  citations_md?: string;
  skipped?: boolean;
  error?: string;
  ok?: boolean;
  endpoint?: string;
}> {
  return apiPost("/api/knowledge/weknora/search", body);
}

export type WeknoraKnowledgeItem = {
  id: string;
  title?: string;
  content?: string;
  nlm_doc_id?: string;
  content_hash?: string;
  updated_at?: string;
  source_type?: string;
};

export function listWeknoraKnowledge(params?: {
  kb_id?: string;
  page?: number;
  page_size?: number;
}): Promise<{
  items?: WeknoraKnowledgeItem[];
  count?: number;
  kb_id?: string;
  skipped?: boolean;
  error?: string;
  ok?: boolean;
}> {
  const q = new URLSearchParams();
  if (params?.kb_id) q.set("kb_id", params.kb_id);
  if (params?.page != null) q.set("page", String(params.page));
  if (params?.page_size != null) q.set("page_size", String(params.page_size));
  const qs = q.toString();
  return apiGet(`/api/knowledge/weknora/knowledge${qs ? `?${qs}` : ""}`);
}

export function getWeknoraKnowledge(knowledgeId: string): Promise<{
  ok?: boolean;
  id?: string;
  title?: string;
  content?: string;
  skipped?: boolean;
  error?: string;
}> {
  const q = new URLSearchParams({ knowledge_id: knowledgeId });
  return apiGet(`/api/knowledge/weknora/item?${q.toString()}`);
}

export function importWeknoraKnowledge(body: {
  knowledge_id: string;
  kb_id?: string;
  workspace_id?: string;
}): Promise<{
  ok?: boolean;
  imported?: boolean;
  unchanged?: boolean;
  conflict?: boolean;
  doc_id?: string;
  title?: string;
  knowledge_id?: string;
  error?: string;
  reason?: string;
}> {
  return apiPost("/api/knowledge/weknora/import", body);
}

export function syncWeknora(body: {
  workspace_id?: string;
  kb_id?: string;
  direction?: string;
  limit?: number;
  doc_ids?: string[];
}): Promise<Record<string, unknown>> {
  return apiPost("/api/knowledge/weknora/sync", body);
}

export function pushWeknora(body: {
  title?: string;
  content?: string;
  doc_id?: string;
  kb_id?: string;
  workspace_id?: string;
}): Promise<Record<string, unknown>> {
  return apiPost("/api/knowledge/weknora/push", body);
}

