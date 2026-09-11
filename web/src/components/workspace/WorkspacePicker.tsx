import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { cn } from "@/lib/utils";
import type { BrowseEntry, SshConfigHost, SshHost, Workspace } from "@/types/api";

export type WorkspacePickerApi = ReturnType<typeof useWorkspaces>;

export type WorkspacePickerProps = {
  /** Called when user picks an existing workspace or creates/binds a new one. */
  onBound: (meta: Workspace) => void;
  compact?: boolean;
  /** Optional injection; otherwise uses internal useWorkspaces(). */
  workspaces?: WorkspacePickerApi;
  className?: string;
};

type HostForm = {
  id: string;
  label: string;
  host: string;
  port: number;
  username: string;
  auth_type: "password" | "key";
  password: string;
  private_key: string;
  default_path: string;
};

const EMPTY_HOST: HostForm = {
  id: "",
  label: "",
  host: "",
  port: 22,
  username: "",
  auth_type: "password",
  password: "",
  private_key: "",
  default_path: "~",
};

function configAlias(entry: SshConfigHost): string {
  return String(entry.alias || entry.Host || "").trim();
}

function configDisplay(entry: SshConfigHost): string {
  if (typeof entry.display === "string" && entry.display) return entry.display;
  const user = String(entry.username || entry.User || "");
  const hostname = String(entry.hostname || entry.HostName || entry.alias || "");
  const port = entry.port ?? entry.Port ?? 22;
  return user ? `${user}@${hostname}:${port}` : `${hostname}:${port}`;
}

function configIdentity(entry: SshConfigHost): string {
  return String(entry.identity_file || entry.IdentityFile || "").trim();
}

function hostBadge(host: SshHost): string {
  if (host.source === "ssh_config") return "config";
  if (host.auth_type === "key") return "key";
  if (host.auth_type === "agent") return "agent";
  return "pwd";
}

export function WorkspacePicker({
  onBound,
  compact = false,
  workspaces: injected,
  className,
}: WorkspacePickerProps) {
  const internal = useWorkspaces();
  const api = injected || internal;

  const {
    workspaces,
    loading,
    error,
    browse,
    sshHosts,
    sshConfigHosts,
    sshConfigPath,
    sshBrowse,
    load,
    loadSshHosts,
    loadSshConfigHosts,
    importSshConfig,
    create,
    createSsh,
    upsertSshHost,
    testSshHost,
    browsePath,
    browseSsh,
  } = api;

  const [tab, setTab] = useState<"local" | "ssh">("local");
  const [sshMode, setSshMode] = useState<"config" | "saved" | "manual">("config");
  const [pathInput, setPathInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [hint, setHintMsg] = useState("");
  const [hintOk, setHintOk] = useState(false);
  const [showBrowser, setShowBrowser] = useState(false);
  const [selectedHostId, setSelectedHostId] = useState("");
  const [hostForm, setHostForm] = useState<HostForm>(EMPTY_HOST);

  function setHint(msg: string, ok = false) {
    setHintMsg(msg);
    setHintOk(ok);
  }

  useEffect(() => {
    void load();
  }, [load]);

  const filteredWorkspaces = useMemo(
    () => workspaces.filter((w) => (tab === "ssh" ? w.kind === "ssh" : w.kind !== "ssh")),
    [workspaces, tab],
  );

  const selectedHost = useMemo(
    () => sshHosts.find((h) => h.id === selectedHostId) || null,
    [sshHosts, selectedHostId],
  );

  const importedAliases = useMemo(
    () =>
      new Set(
        sshHosts
          .filter((h) => h.source === "ssh_config")
          .map((h) => h.ssh_config_alias)
          .filter(Boolean) as string[],
      ),
    [sshHosts],
  );

  async function pickExisting(ws: Workspace) {
    onBound(ws);
  }

  async function addFromInput() {
    const path = pathInput.trim();
    if (!path) {
      setHint("请输入本机目录绝对路径");
      return;
    }
    setBusy(true);
    setHint("正在加入…");
    try {
      const ws = await create(path);
      setPathInput("");
      setHint(`已加入 ${ws.title}`, true);
      onBound(ws);
    } catch (err: any) {
      setHint(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function openBrowser() {
    setShowBrowser(true);
    setHint("");
    try {
      await browsePath(pathInput.trim() || "");
    } catch (err: any) {
      setHint(String(err?.message || err));
    }
  }

  async function goParent() {
    if (!browse?.parent) return;
    await browsePath(browse.parent);
  }

  async function enterDir(entry: BrowseEntry) {
    if (!entry.is_dir) return;
    await browsePath(entry.path);
  }

  async function useBrowsePath() {
    if (!browse?.path) return;
    setPathInput(browse.path);
    setBusy(true);
    setHint("正在加入…");
    try {
      const ws = await create(browse.path);
      setPathInput("");
      setHint(`已加入 ${ws.title}`, true);
      setShowBrowser(false);
      onBound(ws);
    } catch (err: any) {
      setHint(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function loadSshData() {
    try {
      await Promise.all([loadSshHosts(), loadSshConfigHosts()]);
    } catch (err: any) {
      setHint(String(err?.message || err));
    }
  }

  async function switchTab(next: "local" | "ssh") {
    setTab(next);
    setHint("");
    if (next === "ssh") await loadSshData();
  }

  async function saveHost() {
    setBusy(true);
    setHint("保存 SSH 主机…");
    try {
      const host = await upsertSshHost({
        ...hostForm,
        port: Number(hostForm.port) || 22,
        source: "direct",
      });
      setSelectedHostId(host.id);
      setSshMode("saved");
      setHint(`已保存 ${host.display}`, true);
      setHostForm((f) => ({ ...f, password: "", private_key: "" }));
    } catch (err: any) {
      setHint(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function importConfigEntry(entry: SshConfigHost) {
    const alias = configAlias(entry);
    if (!alias) return;
    setBusy(true);
    setHint(`导入 ${alias}…`);
    try {
      const host = await importSshConfig(alias);
      setSelectedHostId(host.id);
      setSshMode("saved");
      setHint(`已导入 ${alias}`, true);
    } catch (err: any) {
      setHint(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  function selectSavedHost(host: SshHost) {
    if (!host?.id) return;
    setSelectedHostId(host.id);
    setSshMode("saved");
    setHint("");
  }

  function useImportedAlias(alias: string) {
    const host = sshHosts.find((h) => h.ssh_config_alias === alias);
    if (host) selectSavedHost(host);
  }

  async function onTestHost() {
    if (!selectedHostId) {
      setHint("请先选择一台主机");
      return;
    }
    setBusy(true);
    setHint("测试 SSH 连通性…");
    try {
      const data = await testSshHost(selectedHostId);
      const message =
        typeof data?.message === "string" ? data.message : "连通成功";
      setHint(message, true);
    } catch (err: any) {
      setHint(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function openSshBrowser() {
    if (!selectedHostId) {
      setHint("请先选择 SSH 主机");
      return;
    }
    setShowBrowser(true);
    setHint("浏览远程目录…");
    try {
      const host = sshHosts.find((h) => h.id === selectedHostId);
      await browseSsh(selectedHostId, host?.default_path || "~");
      setHint("");
    } catch (err: any) {
      setHint(String(err?.message || err));
    }
  }

  async function goSshParent() {
    if (!sshBrowse?.parent || !selectedHostId) return;
    await browseSsh(selectedHostId, sshBrowse.parent);
  }

  async function enterSshDir(entry: BrowseEntry) {
    if (!entry.is_dir || !selectedHostId) return;
    await browseSsh(selectedHostId, entry.path);
  }

  async function useSshBrowsePath() {
    if (!sshBrowse?.path || !selectedHostId) return;
    setBusy(true);
    setHint("正在把远程目录加入 Workspace…");
    try {
      const ws = await createSsh({
        ssh_host_id: selectedHostId,
        path: sshBrowse.path,
      });
      setHint(`已接入远程 ${ws.title}`, true);
      setShowBrowser(false);
      onBound(ws);
    } catch (err: any) {
      setHint(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  const browserEntries =
    tab === "local" ? browse?.entries || [] : sshBrowse?.entries || [];
  const browserPath = tab === "local" ? browse?.path : sshBrowse?.path;
  const browserParent = tab === "local" ? browse?.parent : sshBrowse?.parent;
  const browserReady =
    tab === "local" ? !!browse : tab === "ssh" ? !!sshBrowse : false;

  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[720px] text-left",
        compact && "compact",
        className,
      )}
    >
      <header className="mb-4 flex items-start gap-3.5 rounded-[14px] border border-teal/20 bg-gradient-to-br from-teal/10 to-primary/5 px-4 py-3.5">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-teal/15 text-teal"
          aria-hidden
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-5 w-5">
            <path d="M4 7h16M4 12h10M4 17h14" strokeLinecap="round" />
            <rect x="3" y="4" width="18" height="16" rx="2" />
          </svg>
        </div>
        <div>
          <h3 className="mb-1 text-base font-semibold">选择工作目录</h3>
          <p className="text-xs leading-relaxed text-muted-foreground">
            本机文件夹，或通过 SSH 连接远程机器上的目录，作为 Coding Agent 的工作区。
          </p>
        </div>
      </header>

      <div className="mb-4 grid grid-cols-2 gap-2 rounded-xl border border-border bg-black/25 p-1">
        <button
          type="button"
          className={cn(
            "flex items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors",
            tab === "local" && "bg-white/8 text-foreground shadow-sm",
          )}
          onClick={() => void switchTab("local")}
        >
          <span className="h-2 w-2 rounded-full bg-[#6ea8fe]" />
          本机目录
        </button>
        <button
          type="button"
          className={cn(
            "flex items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors",
            tab === "ssh" && "bg-white/8 text-foreground shadow-sm",
          )}
          onClick={() => void switchTab("ssh")}
        >
          <span className="h-2 w-2 rounded-full bg-teal" />
          远程 SSH
        </button>
      </div>

      {error ? (
        <div className="mb-2.5 rounded-lg border border-destructive/20 bg-destructive/10 px-2.5 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      {loading ? (
        <p className="mb-2.5 text-xs text-muted-foreground">加载中…</p>
      ) : null}

      {filteredWorkspaces.length ? (
        <section className="mb-4">
          <h4 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {tab === "ssh" ? "已接入的远程工作区" : "最近使用"}
          </h4>
          <div
            className={cn(
              "grid max-h-[200px] grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-2 overflow-auto pr-0.5",
              compact && "max-h-[120px]",
            )}
          >
            {filteredWorkspaces.map((ws) => (
              <button
                key={ws.id}
                type="button"
                className="rounded-xl border border-border bg-white/[0.03] p-3 text-left transition-colors hover:-translate-y-px hover:border-teal/45"
                onClick={() => void pickExisting(ws)}
              >
                <div className="mb-1.5 flex items-center justify-between">
                  <Badge
                    variant="outline"
                    className={cn(
                      "px-1.5 py-0 text-[10px] font-semibold uppercase",
                      ws.kind === "ssh"
                        ? "border-teal/20 bg-teal/10 text-teal"
                        : "border-[#6ea8fe]/20 bg-[#6ea8fe]/10 text-[#6ea8fe]",
                    )}
                  >
                    {ws.kind === "ssh" ? "SSH" : "本地"}
                  </Badge>
                  <span
                    className={cn(
                      "text-[10px] text-muted-foreground",
                      (ws.exists || ws.kind === "ssh") && "text-teal",
                    )}
                  >
                    {ws.kind === "ssh" ? "远程" : ws.exists ? "可用" : "缺失"}
                  </span>
                </div>
                <strong className="mb-1 block text-sm font-semibold">{ws.title}</strong>
                <span className="block break-all font-mono text-[10px] leading-snug text-muted-foreground">
                  {ws.path}
                </span>
              </button>
            ))}
          </div>
        </section>
      ) : !loading ? (
        <section className="mb-3.5 rounded-xl border border-dashed border-border px-3 py-5 text-center text-muted-foreground">
          <p className="mb-1 text-sm text-foreground">
            {tab === "ssh" ? "还没有远程工作区" : "还没有本机工作区"}
          </p>
          <span className="text-xs">
            {tab === "ssh"
              ? "从下方连接 SSH 并选择远程目录"
              : "在下方输入或浏览本机目录"}
          </span>
        </section>
      ) : null}

      {tab === "local" ? (
        <section className="rounded-[14px] border border-border bg-black/15 p-3.5">
          <div className="flex flex-col gap-2.5">
            <Input
              className="font-mono text-sm"
              value={pathInput}
              placeholder="例如 E:\projects\my-app 或 /home/user/proj"
              onChange={(e) => setPathInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void addFromInput();
              }}
            />
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => void openBrowser()}
              >
                浏览
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={busy}
                onClick={() => void addFromInput()}
              >
                加入并选用
              </Button>
            </div>
          </div>
        </section>
      ) : (
        <section className="rounded-[14px] border border-border bg-black/15 p-3.5">
          <div className="mb-3.5 flex flex-wrap gap-1.5">
            {(
              [
                ["config", "本机 SSH 配置"],
                ["saved", "已保存主机"],
                ["manual", "手动添加"],
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                className={cn(
                  "rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground",
                  sshMode === mode && "border-teal/45 bg-teal/10 text-foreground",
                )}
                onClick={() => setSshMode(mode)}
              >
                {label}
              </button>
            ))}
          </div>

          {sshMode === "config" ? (
            <div>
              <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
                读取{" "}
                <code className="text-[10px] text-teal">
                  {sshConfigPath || "~/.ssh/config"}
                </code>{" "}
                中的 Host 别名，一键导入后连接。
              </p>
              {!sshConfigHosts.length ? (
                <div className="rounded-xl border border-dashed border-border px-4 py-4 text-center text-muted-foreground">
                  <p className="mb-1 text-sm text-foreground">未找到 Host 条目</p>
                  <span className="text-xs">
                    请确认本机已安装 OpenSSH 并配置了 ~/.ssh/config
                  </span>
                </div>
              ) : (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-2.5">
                  {sshConfigHosts.map((entry) => {
                    const alias = configAlias(entry);
                    const imported = importedAliases.has(alias);
                    return (
                      <article
                        key={alias}
                        className={cn(
                          "rounded-xl border border-border bg-white/[0.02] p-3",
                          imported && "border-teal/25",
                        )}
                      >
                        <div className="mb-1.5 flex items-center justify-between gap-2">
                          <strong className="text-sm">{alias}</strong>
                          {imported ? (
                            <Badge
                              variant="outline"
                              className="border-teal/35 px-1.5 py-0 text-[9px] uppercase text-teal"
                            >
                              已导入
                            </Badge>
                          ) : null}
                        </div>
                        <p className="mb-1 font-mono text-[11px] text-muted-foreground">
                          {configDisplay(entry)}
                        </p>
                        {configIdentity(entry) ? (
                          <p className="mb-2 break-all text-[10px] text-muted-foreground/85">
                            密钥 {configIdentity(entry)}
                          </p>
                        ) : null}
                        <div className="mt-2">
                          {!imported ? (
                            <Button
                              type="button"
                              size="sm"
                              disabled={busy}
                              onClick={() => void importConfigEntry(entry)}
                            >
                              导入
                            </Button>
                          ) : (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              disabled={busy}
                              onClick={() => useImportedAlias(alias)}
                            >
                              选用
                            </Button>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          ) : null}

          {sshMode === "saved" ? (
            <div>
              {!sshHosts.length ? (
                <div className="rounded-xl border border-dashed border-border px-4 py-4 text-center text-muted-foreground">
                  <p className="mb-1 text-sm text-foreground">还没有保存的主机</p>
                  <span className="text-xs">
                    从「本机 SSH 配置」导入，或在「手动添加」里填写连接信息
                  </span>
                </div>
              ) : (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-2.5">
                  {sshHosts.map((host) => (
                    <article
                      key={host.id}
                      className={cn(
                        "cursor-pointer rounded-xl border border-border bg-white/[0.02] p-3 transition-colors hover:border-primary/35",
                        selectedHostId === host.id &&
                          "border-teal/55 bg-teal/10",
                      )}
                      onClick={() => selectSavedHost(host)}
                    >
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <strong className="text-sm">{host.label}</strong>
                        <Badge
                          variant="outline"
                          className={cn(
                            "px-1.5 py-0 text-[9px] uppercase",
                            hostBadge(host) === "config" &&
                              "border-violet-400/35 text-violet-300",
                            (hostBadge(host) === "key" ||
                              hostBadge(host) === "agent") &&
                              "border-[#6ea8fe]/35 text-[#6ea8fe]",
                          )}
                        >
                          {hostBadge(host)}
                        </Badge>
                      </div>
                      <p className="mb-1 font-mono text-[11px] text-muted-foreground">
                        {host.display}
                      </p>
                      {host.source === "ssh_config" ? (
                        <p className="text-[10px] text-muted-foreground/85">
                          来自 ~/.ssh/config · {host.ssh_config_alias}
                        </p>
                      ) : null}
                    </article>
                  ))}
                </div>
              )}
              {selectedHost ? (
                <div className="mt-3.5 flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-teal/20 bg-teal/[0.06] p-3 text-sm">
                  <span>
                    已选 <strong>{selectedHost.label}</strong>
                  </span>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      onClick={() => void onTestHost()}
                    >
                      测试连接
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy}
                      onClick={() => void openSshBrowser()}
                    >
                      浏览远程目录
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {sshMode === "manual" ? (
            <div>
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">显示名</Label>
                  <Input
                    value={hostForm.label}
                    placeholder="prod-box"
                    onChange={(e) =>
                      setHostForm((f) => ({ ...f, label: e.target.value }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Host</Label>
                  <Input
                    value={hostForm.host}
                    placeholder="192.168.1.10"
                    onChange={(e) =>
                      setHostForm((f) => ({ ...f, host: e.target.value }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Port</Label>
                  <Input
                    type="number"
                    value={hostForm.port}
                    onChange={(e) =>
                      setHostForm((f) => ({
                        ...f,
                        port: Number(e.target.value) || 22,
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Username</Label>
                  <Input
                    value={hostForm.username}
                    placeholder="ubuntu"
                    onChange={(e) =>
                      setHostForm((f) => ({ ...f, username: e.target.value }))
                    }
                  />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <Label className="text-xs text-muted-foreground">认证方式</Label>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      className={cn(
                        "flex-1 rounded-lg border border-border px-2 py-2 text-sm text-muted-foreground",
                        hostForm.auth_type === "password" &&
                          "border-teal/45 bg-teal/10 text-foreground",
                      )}
                      onClick={() =>
                        setHostForm((f) => ({ ...f, auth_type: "password" }))
                      }
                    >
                      密码
                    </button>
                    <button
                      type="button"
                      className={cn(
                        "flex-1 rounded-lg border border-border px-2 py-2 text-sm text-muted-foreground",
                        hostForm.auth_type === "key" &&
                          "border-teal/45 bg-teal/10 text-foreground",
                      )}
                      onClick={() =>
                        setHostForm((f) => ({ ...f, auth_type: "key" }))
                      }
                    >
                      私钥
                    </button>
                  </div>
                </div>
                {hostForm.auth_type === "password" ? (
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-xs text-muted-foreground">Password</Label>
                    <Input
                      type="password"
                      autoComplete="off"
                      value={hostForm.password}
                      onChange={(e) =>
                        setHostForm((f) => ({ ...f, password: e.target.value }))
                      }
                    />
                  </div>
                ) : (
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-xs text-muted-foreground">
                      Private Key（PEM 或本机路径）
                    </Label>
                    <Textarea
                      rows={3}
                      placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                      value={hostForm.private_key}
                      onChange={(e) =>
                        setHostForm((f) => ({
                          ...f,
                          private_key: e.target.value,
                        }))
                      }
                    />
                  </div>
                )}
                <div className="space-y-1 sm:col-span-2">
                  <Label className="text-xs text-muted-foreground">默认远程路径</Label>
                  <Input
                    value={hostForm.default_path}
                    placeholder="~ 或 /home/ubuntu/proj"
                    onChange={(e) =>
                      setHostForm((f) => ({
                        ...f,
                        default_path: e.target.value,
                      }))
                    }
                  />
                </div>
              </div>
              <div className="mt-3">
                <Button
                  type="button"
                  size="sm"
                  disabled={busy}
                  onClick={() => void saveHost()}
                >
                  保存并选用
                </Button>
              </div>
            </div>
          ) : null}
        </section>
      )}

      {hint ? (
        <p
          className={cn(
            "mt-3 text-xs text-muted-foreground",
            hintOk && "text-teal",
          )}
        >
          {hint}
        </p>
      ) : null}

      <Dialog open={showBrowser} onOpenChange={setShowBrowser}>
        <DialogContent className="flex max-h-[70vh] max-w-lg flex-col gap-0 overflow-hidden p-0 sm:max-w-[560px]">
          <DialogHeader className="border-b border-border px-3.5 py-3">
            <DialogTitle className="text-sm">
              {tab === "ssh" ? "选择远程目录" : "选择本机目录"}
            </DialogTitle>
            <DialogDescription className="sr-only">
              浏览文件系统并选用目录
            </DialogDescription>
          </DialogHeader>

          {browserReady ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex items-center gap-2 border-b border-border bg-black/20 px-3 py-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={!browserParent}
                  onClick={() =>
                    void (tab === "ssh" ? goSshParent() : goParent())
                  }
                >
                  上级
                </Button>
                <code className="flex-1 break-all text-[11px] text-muted-foreground">
                  {browserPath}
                </code>
              </div>
              <div className="min-h-[180px] max-h-[320px] flex-1 overflow-auto">
                {browserEntries.map((e) => (
                  <button
                    key={e.path}
                    type="button"
                    className="flex w-full gap-2.5 border-b border-white/[0.04] px-3 py-2.5 text-left text-sm hover:bg-teal/10"
                    onClick={() =>
                      void (tab === "ssh" ? enterSshDir(e) : enterDir(e))
                    }
                  >
                    <span
                      className={cn(
                        "w-[2.4em] shrink-0 text-[10px] text-muted-foreground",
                        e.is_dir && "text-teal",
                      )}
                    >
                      {e.is_dir ? "目录" : "文件"}
                    </span>
                    <span>{e.name}</span>
                  </button>
                ))}
              </div>
              <DialogFooter className="border-t border-border px-3 py-2.5 sm:justify-end">
                <Button
                  type="button"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    void (tab === "ssh" ? useSshBrowsePath() : useBrowsePath())
                  }
                >
                  {tab === "ssh" ? "选用远程目录" : "选用此目录"}
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="px-6 py-6 text-center text-sm text-muted-foreground">
              加载目录…
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default WorkspacePicker;
