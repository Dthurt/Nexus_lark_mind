/** Shared API contract types mirroring Vue frontend + backend envelopes. */

export type ApiErrorBody = {
  code?: string;
  message?: string;
  detail?: string | { message?: string; [key: string]: unknown };
  [key: string]: unknown;
};

export type ApiEnvelope<T> = {
  ok: boolean;
  data?: T;
  error?: ApiErrorBody | null;
  detail?: string;
};

export type Usage = {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cached_tokens?: number;
  duration_ms?: number;
  [key: string]: unknown;
};

export type HistoryMessage = {
  role: "system" | "user" | "assistant" | "tool" | string;
  content?: string;
  name?: string | null;
  tool_call_id?: string | null;
  metadata?: Record<string, unknown>;
};

export type SessionSummary = {
  session_id: string;
  title?: string;
  preview?: string;
  updated_at?: string;
  created_at?: string;
  message_count?: number;
  channel?: string;
  cwd?: string;
  workspace_id?: string;
  workspace_title?: string;
  workspace_kind?: string;
  ssh_host_id?: string;
};

export type SessionDetail = {
  session_id: string;
  user_id?: string;
  channel?: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
  messages?: HistoryMessage[];
  usage?: Usage;
  cwd?: string;
  workspace_id?: string;
  workspace_title?: string;
  workspace_kind?: string;
  ssh_host_id?: string;
  agent_mode?: "agent" | "plan" | string;
  auto_accept?: boolean;
  plan_status?: "idle" | "drafting" | "accepted" | string;
};

export type Workspace = {
  id: string;
  path: string;
  title?: string;
  kind?: "local" | "ssh" | string;
  ssh_host_id?: string;
  exists?: boolean;
  is_dir?: boolean;
  session_ids?: string[];
  session_count?: number;
  created_at?: string;
  updated_at?: string;
};

export type BrowseEntry = {
  name: string;
  path: string;
  is_dir?: boolean;
  is_file?: boolean;
};

export type BrowseResult = {
  path: string;
  parent?: string | null;
  entries?: BrowseEntry[];
  title?: string;
};

export type SshHost = {
  id: string;
  label?: string;
  host: string;
  port?: number;
  username: string;
  auth_type?: "password" | "key" | "agent" | string;
  source?: "direct" | "ssh_config" | string;
  ssh_config_alias?: string;
  secret_set?: boolean;
  secret_preview?: string;
  default_path?: string;
  display?: string;
  created_at?: string;
  updated_at?: string;
  /** Upsert-only secret fields (never returned by list). */
  password?: string;
  private_key?: string;
  private_key_passphrase?: string;
};

export type SshConfigHost = {
  alias?: string;
  hostname?: string;
  username?: string;
  port?: number | string;
  identity_file?: string;
  display?: string;
  config_path?: string;
  /** Legacy / OpenSSH-style keys (optional). */
  Host?: string;
  HostName?: string;
  User?: string;
  Port?: number | string;
  IdentityFile?: string;
  [key: string]: unknown;
};

export type PluginConfigField = {
  key: string;
  label?: string;
  type?: string;
  secret?: boolean;
  options?: string[];
  hint?: string;
  placeholder?: string;
  value?: string;
  set?: boolean;
  preview?: string;
  [key: string]: unknown;
};

export type PluginConfigSchema = {
  plugin_id?: string;
  fields?: PluginConfigField[];
  has_schema?: boolean;
  values?: Record<string, string>;
};

export type Plugin = {
  plugin_id: string;
  name?: string;
  kind?: string;
  version?: string;
  description?: string;
  state?: string;
  enabled?: boolean;
  active?: boolean;
  tools?: Tool[];
  tool_count?: number;
  last_error?: string | null;
  health?: Record<string, unknown> | null;
  config_hints?: string[];
  config_schema?: PluginConfigSchema | null;
};

export type Tool = {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
  parameters?: Record<string, unknown>;
  plugin_id?: string;
  openai_name?: string;
};

export type ProviderEntry = {
  id: string;
  label?: string;
  api?: string;
  base_url?: string;
  default_model?: string;
  models?: string[];
  enabled?: boolean;
  builtin?: boolean;
  configured?: boolean;
  api_key_set?: boolean;
  api_key_preview?: string;
  source?: string;
  editable?: boolean;
  hint?: string;
  /** Write-only when saving a custom provider. */
  api_key?: string;
};

export type ProviderCatalog = {
  default_provider?: string;
  default_model?: string;
  providers: ProviderEntry[];
};

export type ProviderDoc = {
  default_provider?: string;
  builtins: ProviderEntry[];
  customs: ProviderEntry[];
};

export type ChannelEntry = {
  id: string;
  kind?: string;
  display_name?: string;
  enabled?: boolean;
  configured?: boolean;
  editable?: boolean;
  hint?: string;
  app_id?: string;
  app_id_effective?: string;
  app_secret_set?: boolean;
  app_secret_preview?: string;
  verification_token_set?: boolean;
  encrypt_key_set?: boolean;
  use_long_connection?: boolean;
  source?: string;
  [key: string]: unknown;
};

export type ChannelDoc = {
  product?: string;
  channels: ChannelEntry[];
  runtime?: Record<string, unknown>;
};

export type AskOption = {
  id: string;
  label: string;
};

export type AskQuestion = {
  id: string;
  prompt: string;
  options?: AskOption[];
  allow_multiple?: boolean;
  allow_custom?: boolean;
};

export type TodoItem = {
  id?: string;
  content: string;
  status?: "pending" | "in_progress" | "completed" | "cancelled" | string;
};

export type SseEventType =
  | "task.started"
  | "task.status"
  | "task.tool_call"
  | "task.tool_result"
  | "task.tool_approval"
  | "task.ask_user"
  | "task.plan_review"
  | "task.plan_mode"
  | "task.todos"
  | "task.canvas_open"
  | "task.plan_ready"
  | "task.subagent"
  | "task.delta"
  | "task.completed"
  | "task.failed";

export type SseMessage = {
  event_type: SseEventType | string;
  task_id?: string;
  session_id?: string;
  payload?: Record<string, unknown>;
  ts?: string;
  event_id?: string;
  channel?: string;
  [key: string]: unknown;
};

export type ChatSendBody = {
  content: string;
  session_id?: string;
  user_id?: string;
  stream?: boolean;
  tools_enabled?: boolean;
  agent_mode?: "agent" | "plan" | string;
  auto_accept?: boolean;
  multitask?: boolean;
  permission_preset?: "read-only" | "workspace-write" | "danger-full-access" | string;
  plan_enforcement?: "hard" | "soft" | string;
  experience_tier?: "fast" | "balanced" | "high" | string;
  reasoning_effort?: "low" | "medium" | "high" | string;
  model_provider?: string;
  model_name?: string;
  workspace_id?: string;
  cwd?: string;
  workspace_kind?: string;
  ssh_host_id?: string;
  /** @ file/dir chips — expanded server-side into Attached context */
  context_refs?: { path: string; kind?: "file" | "dir" | string; label?: string }[];
};

export type ApprovalAction = "allow" | "deny" | "allow_session" | "always" | string;

export type AskAnswersBody = {
  call_id: string;
  action?: string;
  answers?: Record<string, unknown>;
  reason?: string;
  feedback?: string;
  auto_accept?: boolean;
};

export type AcceptPlanBody = {
  content?: string;
  tools_enabled?: boolean;
  model_provider?: string;
  model_name?: string;
  workspace_id?: string;
  cwd?: string;
  workspace_kind?: string;
  ssh_host_id?: string;
  auto_accept?: boolean;
};

export type InteractionPatchBody = {
  agent_mode?: "agent" | "plan" | string;
  auto_accept?: boolean;
  plan_status?: "idle" | "drafting" | "accepted" | string;
  permission_preset?: "read-only" | "workspace-write" | "danger-full-access" | string;
  plan_enforcement?: "hard" | "soft" | string;
  experience_tier?: "fast" | "balanced" | "high" | string;
  reasoning_effort?: "low" | "medium" | "high" | string;
  model_provider?: string;
  model_name?: string;
  active_tools?: string[] | null;
  clear_active_tools?: boolean;
  preset_name?: string;
  system_prompt_append?: string;
  cwd?: string;
  weknora_kb_id?: string;
  clear_weknora_kb_id?: boolean;
};

export type WorkspacePatchBody = {
  workspace_id?: string;
  cwd?: string;
  workspace_title?: string;
  workspace_kind?: string;
  ssh_host_id?: string;
  force?: boolean;
};

export type CreateSessionBody = {
  session_id?: string;
  channel?: string;
  user_id?: string;
  workspace_id?: string;
  cwd?: string;
  workspace_title?: string;
  workspace_kind?: string;
  ssh_host_id?: string;
};

export type ChatQueued = {
  task_id: string;
  session_id?: string;
  status?: string;
};

export type MermaidRepairBody = {
  source: string;
  error?: string;
  model_provider?: string;
  model_name?: string;
};

export type MermaidRepairResult = {
  source: string;
  raw?: unknown;
};

export type EchartsRepairBody = MermaidRepairBody;
export type EchartsRepairResult = MermaidRepairResult;

export type DrawioRepairBody = MermaidRepairBody;
export type DrawioRepairResult = MermaidRepairResult;

export type GitInfo = {
  branch: string;
  is_repo?: boolean;
  cwd?: string;
  insertions?: number;
  deletions?: number;
};

export type PluginCallRow = {
  call_id: string;
  task_id?: string;
  plugin_id?: string;
  tool_name?: string;
  arguments?: unknown;
  success?: boolean;
  result?: unknown;
  error?: string | null;
  duration_ms?: number;
  created_at?: string | null;
};

export type WorkspacesListData = {
  workspaces: Workspace[];
};

export type SshHostsListData = {
  hosts: SshHost[];
};

export type SshConfigHostsData = {
  config_path?: string;
  exists?: boolean;
  hosts: SshConfigHost[];
};
