import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChannelSettings } from "@/hooks/useChannelSettings";
import { useModelSettings } from "@/hooks/useModelSettings";
import { cn } from "@/lib/utils";
import type { ProviderEntry } from "@/types/api";

export type SettingsPageProps = {
  onBack: () => void;
  onCatalogChanged?: () => void;
};

type ProviderForm = {
  id: string;
  label: string;
  api: string;
  base_url: string;
  api_key: string;
  default_model: string;
  models: string;
  enabled: boolean;
};

type FeishuForm = {
  enabled: boolean;
  display_name: string;
  app_id: string;
  app_secret: string;
  verification_token: string;
  encrypt_key: string;
  use_long_connection: boolean;
};

const EMPTY_PROVIDER: ProviderForm = {
  id: "",
  label: "",
  api: "openai-completions",
  base_url: "",
  api_key: "",
  default_model: "",
  models: "",
  enabled: true,
};

const EMPTY_FEISHU: FeishuForm = {
  enabled: true,
  display_name: "飞书",
  app_id: "",
  app_secret: "",
  verification_token: "",
  encrypt_key: "",
  use_long_connection: true,
};

function modelChips(models: string[] | undefined, defaultModel?: string) {
  if (!models?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {models.map((m) => (
        <Badge
          key={m}
          variant="outline"
          className={cn(
            "px-1.5 py-0 text-[10px] font-normal",
            m === defaultModel && "border-teal/40 text-teal",
          )}
        >
          {m}
        </Badge>
      ))}
    </div>
  );
}

export default function SettingsPage({ onBack, onCatalogChanged }: SettingsPageProps) {
  const {
    doc,
    loading,
    saving,
    error,
    load,
    saveProvider,
    removeProvider,
    setDefault,
    discoverModels,
    testConnectivity,
  } = useModelSettings();

  const {
    doc: channelDoc,
    loading: channelLoading,
    saving: channelSaving,
    testing: channelTesting,
    error: channelError,
    testHint: feishuTestHint,
    load: loadChannels,
    saveFeishu,
    testFeishu,
    reloadFeishu,
    feishuChannel,
  } = useChannelSettings();

  const [tab, setTab] = useState<"models" | "channels">("models");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ProviderForm>(EMPTY_PROVIDER);
  const [feishuForm, setFeishuForm] = useState<FeishuForm>(EMPTY_FEISHU);
  const [formError, setFormError] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [testingModel, setTestingModel] = useState(false);
  const [discoverHint, setDiscoverHint] = useState("");
  const [modelTestHint, setModelTestHint] = useState("");
  const discoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const feishu = feishuChannel();

  const syncFeishuForm = useCallback(() => {
    const c = feishuChannel();
    if (!c) return;
    setFeishuForm({
      enabled: c.enabled !== false,
      display_name: c.display_name || "飞书",
      app_id: c.app_id || "",
      app_secret: "",
      verification_token: "",
      encrypt_key: "",
      use_long_connection: c.use_long_connection !== false,
    });
  }, [feishuChannel]);

  useEffect(() => {
    void load();
  }, [load]);

  const providerOptions = useMemo(
    () => [
      ...doc.builtins.map((p) => ({ value: p.id, label: `${p.label} (env)` })),
      ...doc.customs.map((p) => ({ value: p.id, label: p.label || p.id })),
    ],
    [doc.builtins, doc.customs],
  );

  const discoveredModelList = useMemo(
    () =>
      form.models
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
    [form.models],
  );

  function resetForm() {
    setEditingId(null);
    setDiscoverHint("");
    setModelTestHint("");
    setFormError("");
    setForm(EMPTY_PROVIDER);
  }

  function startCreate() {
    resetForm();
    setEditingId("__new__");
  }

  function startEdit(p: ProviderEntry) {
    setEditingId(p.id);
    setDiscoverHint("");
    setModelTestHint("");
    setFormError("");
    setForm({
      id: p.id,
      label: p.label || "",
      api: p.api || "openai-completions",
      base_url: p.base_url || "",
      api_key: "",
      default_model: p.default_model || "",
      models: (p.models || []).join(", "),
      enabled: p.enabled !== false,
    });
  }

  const fetchAvailableModels = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (!form.base_url.trim()) {
        if (!silent) setDiscoverHint("请先填写 Base URL");
        return;
      }
      if (editingId === "__new__" && !form.api_key.trim()) {
        if (!silent) setDiscoverHint("请先填写 API Key");
        return;
      }
      setDiscovering(true);
      setDiscoverHint(silent ? "正在拉取模型列表…" : "正在请求 /models …");
      try {
        const data = await discoverModels({
          base_url: form.base_url.trim(),
          api_key: form.api_key,
          provider_id: editingId !== "__new__" && editingId ? editingId : undefined,
        });
        const models = data.models || [];
        setForm((prev) => {
          const nextDefault =
            !prev.default_model || !models.includes(prev.default_model)
              ? data.default_model || models[0] || ""
              : prev.default_model;
          return {
            ...prev,
            models: models.join(", "),
            default_model: nextDefault,
          };
        });
        setDiscoverHint(`已拉取 ${models.length} 个模型`);
      } catch (err: any) {
        setDiscoverHint(String(err?.message || err));
        if (!silent) throw err;
      } finally {
        setDiscovering(false);
      }
    },
    [discoverModels, editingId, form.api_key, form.base_url],
  );

  function scheduleDiscover() {
    if (discoverTimer.current) clearTimeout(discoverTimer.current);
    discoverTimer.current = setTimeout(() => {
      void fetchAvailableModels({ silent: true });
    }, 600);
  }

  useEffect(() => {
    return () => {
      if (discoverTimer.current) clearTimeout(discoverTimer.current);
    };
  }, []);

  async function runModelTest(providerId?: string) {
    setTestingModel(true);
    setModelTestHint("正在测试连通性…");
    try {
      const payload = providerId
        ? { provider_id: providerId }
        : {
            base_url: form.base_url.trim(),
            api_key: form.api_key,
            model: form.default_model.trim(),
            provider_id: editingId !== "__new__" && editingId ? editingId : undefined,
          };
      const data = await testConnectivity(payload);
      const chat = data.chat_ok
        ? "对话探测成功"
        : data.chat_error
          ? `对话：${data.chat_error}`
          : "仅验证 /models";
      setModelTestHint(`连通成功 · ${data.models_count || 0} 个模型 · ${chat}`);
    } catch (err: any) {
      setModelTestHint(String(err?.message || err));
    } finally {
      setTestingModel(false);
    }
  }

  async function onSave() {
    const id = form.id.trim();
    const base_url = form.base_url.trim();
    const models = form.models
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
    const default_model = form.default_model.trim() || models[0] || "";
    if (!id) {
      setFormError("请填写 Provider ID");
      return;
    }
    if (!base_url) {
      setFormError("请填写 Base URL");
      return;
    }
    if (!default_model && !models.length) {
      setFormError("请填写默认模型，或先「拉取可用模型」");
      return;
    }
    if (editingId === "__new__" && !form.api_key.trim()) {
      setFormError("新增时必须填写 API Key");
      return;
    }
    setFormError("");
    try {
      await saveProvider({
        id,
        label: form.label.trim() || id,
        api: form.api,
        base_url,
        api_key: form.api_key,
        default_model,
        models: models.length ? models : default_model ? [default_model] : [],
        enabled: !!form.enabled,
      });
      resetForm();
      onCatalogChanged?.();
    } catch {
      /* hook.error already set */
    }
  }

  async function onDelete(id: string) {
    if (!confirm(`删除自定义 Provider「${id}」？`)) return;
    await removeProvider(id);
    if (editingId === id) resetForm();
    onCatalogChanged?.();
  }

  async function onDefault(id: string) {
    await setDefault(id);
    onCatalogChanged?.();
  }

  async function onSaveFeishu() {
    await saveFeishu({
      enabled: !!feishuForm.enabled,
      display_name: feishuForm.display_name.trim() || "飞书",
      app_id: feishuForm.app_id.trim(),
      app_secret: feishuForm.app_secret,
      verification_token: feishuForm.verification_token,
      encrypt_key: feishuForm.encrypt_key,
      use_long_connection: !!feishuForm.use_long_connection,
    });
    syncFeishuForm();
  }

  async function onTestFeishu() {
    await testFeishu({
      app_id: feishuForm.app_id.trim(),
      app_secret: feishuForm.app_secret,
    });
  }

  async function switchTab(next: string) {
    const value = next === "channels" ? "channels" : "models";
    setTab(value);
    if (value === "channels") {
      await loadChannels();
      syncFeishuForm();
    }
  }

  const displayError = formError || error;

  return (
    <div className="flex h-full max-h-full flex-col overflow-hidden text-foreground">
      <header className="flex shrink-0 items-center gap-4 border-b border-border bg-card/80 px-5 py-3.5 backdrop-blur-md">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          ← 返回对话
        </Button>
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Nexus Lark Mind</h1>
          <p className="text-xs text-muted-foreground">设置 · 模型与通道</p>
        </div>
      </header>

      <Tabs
        value={tab}
        onValueChange={(v) => void switchTab(v)}
        className="mx-auto grid min-h-0 w-full max-w-[1100px] flex-1 overflow-hidden md:grid-cols-[180px_minmax(0,1fr)]"
      >
        <TabsList className="h-auto w-full flex-row justify-start gap-1.5 overflow-x-auto rounded-none border-b border-border bg-transparent p-3 md:flex-col md:overflow-y-auto md:border-b-0 md:border-r">
          <TabsTrigger
            value="models"
            className="w-auto justify-start px-2.5 py-2 data-[state=active]:bg-primary/15 data-[state=active]:shadow-none md:w-full"
          >
            模型
          </TabsTrigger>
          <TabsTrigger
            value="channels"
            className="w-auto justify-start px-2.5 py-2 data-[state=active]:bg-primary/15 data-[state=active]:shadow-none md:w-full"
          >
            通道
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value="models"
          className="mt-0 min-h-0 space-y-5 overflow-y-auto overscroll-contain px-5 py-4.5 pb-10"
        >
          {displayError && !editingId ? (
            <p className="text-sm text-destructive">{displayError}</p>
          ) : null}
          {loading ? <p className="text-xs text-muted-foreground">加载中…</p> : null}

          <section>
            <h2 className="mb-1.5 text-[15px] font-semibold">默认 Provider</h2>
            <p className="mb-2.5 text-xs text-muted-foreground">
              新对话优先使用；也可在 Composer 临时切换。
            </p>
            <div className="max-w-xs">
              <Select
                value={doc.default_provider || undefined}
                onValueChange={(v) => void onDefault(v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择默认 Provider" />
                </SelectTrigger>
                <SelectContent>
                  {providerOptions.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </section>

          <section>
            <h2 className="mb-1.5 text-[15px] font-semibold">内置 Provider（.env）</h2>
            <p className="mb-2.5 text-xs text-muted-foreground">
              只读。改 Key / 模型列表请编辑 `.env` 后重启。
            </p>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-2.5">
              {doc.builtins.map((p) => (
                <Card key={p.id} className="border-border/80 bg-card/40 shadow-none">
                  <CardHeader className="space-y-1 p-3 pb-1">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-sm">{p.label}</CardTitle>
                      <Badge
                        variant="outline"
                        className={cn(
                          "px-1.5 py-0 text-[10px] font-normal",
                          p.configured && "border-teal/40 text-teal",
                        )}
                      >
                        {p.configured ? "已配置" : "未配置"}
                      </Badge>
                    </div>
                    <CardDescription className="text-[11px]">
                      {p.id} · {p.api}
                    </CardDescription>
                    <p className="break-all font-mono text-[11px] text-muted-foreground">
                      {p.base_url}
                    </p>
                  </CardHeader>
                  <CardContent className="p-3 pt-0">
                    {modelChips(p.models, p.default_model)}
                  </CardContent>
                  <CardFooter className="p-3 pt-0">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={testingModel || !p.configured}
                      onClick={() => void runModelTest(p.id)}
                    >
                      测试连通性
                    </Button>
                  </CardFooter>
                </Card>
              ))}
            </div>
          </section>

          <section>
            <div className="mb-2.5 flex items-start justify-between gap-3">
              <div>
                <h2 className="mb-1.5 text-[15px] font-semibold">自定义 Provider</h2>
                <p className="text-xs text-muted-foreground">
                  填 Base URL + API Key 后可自动拉取 `/models`；保存前可测连通性。
                </p>
              </div>
              <Button type="button" size="sm" onClick={startCreate}>
                ＋ 新增
              </Button>
            </div>

            <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-2.5">
              {doc.customs.map((p) => (
                <Card
                  key={p.id}
                  className="border-primary/25 bg-card/40 shadow-none"
                >
                  <CardHeader className="space-y-1 p-3 pb-1">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-sm">{p.label || p.id}</CardTitle>
                      <Badge
                        variant="outline"
                        className={cn(
                          "px-1.5 py-0 text-[10px] font-normal",
                          p.configured && "border-teal/40 text-teal",
                        )}
                      >
                        {p.configured ? "可用" : "缺 Key/模型"}
                      </Badge>
                    </div>
                    <CardDescription className="text-[11px]">
                      {p.id} · {p.api}
                    </CardDescription>
                    <p className="break-all font-mono text-[11px] text-muted-foreground">
                      {p.base_url}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      Key: {p.api_key_set ? p.api_key_preview : "未设置"}
                    </p>
                  </CardHeader>
                  <CardContent className="p-3 pt-0">
                    {modelChips(p.models, p.default_model)}
                  </CardContent>
                  <CardFooter className="flex flex-wrap gap-1 p-3 pt-0">
                    <Button type="button" variant="ghost" size="sm" onClick={() => startEdit(p)}>
                      编辑
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={testingModel}
                      onClick={() => void runModelTest(p.id)}
                    >
                      测试连通性
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => void onDelete(p.id)}
                    >
                      删除
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => void onDefault(p.id)}
                    >
                      设为默认
                    </Button>
                  </CardFooter>
                </Card>
              ))}
              {!doc.customs.length ? (
                <p className="text-xs text-muted-foreground">还没有自定义 Provider。</p>
              ) : null}
            </div>
            {modelTestHint && !editingId ? (
              <p className="mt-2 text-xs text-muted-foreground">{modelTestHint}</p>
            ) : null}
          </section>

          <Dialog open={!!editingId} onOpenChange={(open) => !open && resetForm()}>
            <DialogContent className="max-h-[92vh] max-w-lg overflow-y-auto sm:max-w-[560px]">
              <DialogHeader>
                <DialogTitle>
                  {editingId === "__new__" ? "新增 Provider" : `编辑 ${editingId}`}
                </DialogTitle>
                <DialogDescription className="sr-only">
                  配置自定义模型 Provider
                </DialogDescription>
              </DialogHeader>

              {displayError ? (
                <p className="text-sm text-destructive">{displayError}</p>
              ) : null}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">ID（小写短横线）</Label>
                  <Input
                    value={form.id}
                    disabled={editingId !== "__new__"}
                    placeholder="my-proxy"
                    onChange={(e) => setForm((f) => ({ ...f, id: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">显示名</Label>
                  <Input
                    value={form.label}
                    placeholder="My Proxy"
                    onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label className="text-xs text-muted-foreground">协议</Label>
                  <Select
                    value={form.api}
                    onValueChange={(v) => setForm((f) => ({ ...f, api: v }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openai-completions">openai-completions</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label className="text-xs text-muted-foreground">Base URL</Label>
                  <Input
                    value={form.base_url}
                    placeholder="https://api.example.com/v1"
                    onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
                    onBlur={scheduleDiscover}
                  />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label className="text-xs text-muted-foreground">
                    API Key{editingId !== "__new__" ? "（留空则保留原值）" : ""}
                  </Label>
                  <Input
                    type="password"
                    value={form.api_key}
                    placeholder="sk-..."
                    autoComplete="off"
                    onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
                    onBlur={scheduleDiscover}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">默认模型</Label>
                  <Input
                    value={form.default_model}
                    placeholder="gpt-4o-mini"
                    list="discovered-models"
                    onChange={(e) =>
                      setForm((f) => ({ ...f, default_model: e.target.value }))
                    }
                  />
                  <datalist id="discovered-models">
                    {discoveredModelList.map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">
                    模型列表（自动拉取 / 可改）
                  </Label>
                  <Input
                    value={form.models}
                    placeholder="拉取后自动填入，也可手改"
                    onChange={(e) => setForm((f) => ({ ...f, models: e.target.value }))}
                  />
                </div>
                <div className="flex items-center gap-2 sm:col-span-2">
                  <Switch
                    checked={form.enabled}
                    onCheckedChange={(checked) =>
                      setForm((f) => ({ ...f, enabled: checked }))
                    }
                    id="provider-enabled"
                  />
                  <Label htmlFor="provider-enabled" className="text-xs text-muted-foreground">
                    启用
                  </Label>
                </div>
              </div>

              {discoverHint ? (
                <p className="text-xs text-muted-foreground">{discoverHint}</p>
              ) : null}
              {modelTestHint ? (
                <p className="text-xs text-muted-foreground">{modelTestHint}</p>
              ) : null}

              <DialogFooter className="flex-wrap gap-2 sm:justify-between">
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={discovering || saving}
                    onClick={() => void fetchAvailableModels()}
                  >
                    {discovering ? "拉取中…" : "拉取可用模型"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={testingModel || saving}
                    onClick={() => void runModelTest()}
                  >
                    {testingModel ? "测试中…" : "测试连通性"}
                  </Button>
                </div>
                <div className="flex gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={resetForm}>
                    取消
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={saving}
                    onClick={() => void onSave()}
                  >
                    {saving ? "保存中…" : "保存"}
                  </Button>
                </div>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </TabsContent>

        <TabsContent
          value="channels"
          className="mt-0 min-h-0 space-y-5 overflow-y-auto overscroll-contain px-5 py-4.5 pb-10"
        >
          {channelError ? (
            <p className="text-sm text-destructive">{channelError}</p>
          ) : null}
          {channelLoading ? (
            <p className="text-xs text-muted-foreground">加载中…</p>
          ) : null}

          <section>
            <h2 className="mb-1.5 text-[15px] font-semibold">通道概览</h2>
            <p className="mb-2.5 text-xs text-muted-foreground">
              {channelDoc.product || "Nexus Lark Mind"} 可接入多个外部应用通道；凭证保存在本机
              `data/channels.json`。
            </p>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-2.5">
              {(channelDoc.channels || []).map((c) => (
                <Card
                  key={c.id}
                  className={cn(
                    "border-border/80 bg-card/40 shadow-none",
                    c.id === "feishu" && "border-primary/25",
                  )}
                >
                  <CardHeader className="space-y-1 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-sm">{c.display_name}</CardTitle>
                      <Badge
                        variant="outline"
                        className={cn(
                          "px-1.5 py-0 text-[10px] font-normal",
                          c.configured && c.enabled && "border-teal/40 text-teal",
                        )}
                      >
                        {c.configured
                          ? c.enabled
                            ? "已接入"
                            : "已配置未启用"
                          : "未配置"}
                      </Badge>
                    </div>
                    <CardDescription className="text-[11px]">
                      {c.id} · {c.hint}
                    </CardDescription>
                    {c.source ? (
                      <p className="text-[11px] text-muted-foreground">来源: {c.source}</p>
                    ) : null}
                  </CardHeader>
                </Card>
              ))}
            </div>
          </section>

          <section>
            <h2 className="mb-1.5 text-[15px] font-semibold">飞书 Channel</h2>
            <p className="mb-3 text-xs text-muted-foreground leading-relaxed">
              在飞书开放平台创建企业自建应用，把 App ID / App Secret 填入下方，即可将该应用加入
              Nexus Lark Mind。推荐开启「长连接」接收事件（无需公网回调）。
            </p>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">显示名</Label>
                <Input
                  value={feishuForm.display_name}
                  placeholder="飞书"
                  onChange={(e) =>
                    setFeishuForm((f) => ({ ...f, display_name: e.target.value }))
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">App ID</Label>
                <Input
                  value={feishuForm.app_id}
                  placeholder="cli_xxxxxxxx"
                  autoComplete="off"
                  onChange={(e) =>
                    setFeishuForm((f) => ({ ...f, app_id: e.target.value }))
                  }
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label className="text-xs text-muted-foreground">
                  App Secret{feishu?.app_secret_set ? "（留空则保留原值）" : ""}
                </Label>
                <Input
                  type="password"
                  value={feishuForm.app_secret}
                  placeholder="填写飞书应用 Secret"
                  autoComplete="off"
                  onChange={(e) =>
                    setFeishuForm((f) => ({ ...f, app_secret: e.target.value }))
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">
                  Verification Token（可选）
                </Label>
                <Input
                  type="password"
                  value={feishuForm.verification_token}
                  autoComplete="off"
                  onChange={(e) =>
                    setFeishuForm((f) => ({
                      ...f,
                      verification_token: e.target.value,
                    }))
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Encrypt Key（可选）</Label>
                <Input
                  type="password"
                  value={feishuForm.encrypt_key}
                  autoComplete="off"
                  onChange={(e) =>
                    setFeishuForm((f) => ({ ...f, encrypt_key: e.target.value }))
                  }
                />
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="feishu-enabled"
                  checked={feishuForm.enabled}
                  onCheckedChange={(checked) =>
                    setFeishuForm((f) => ({ ...f, enabled: checked }))
                  }
                />
                <Label htmlFor="feishu-enabled" className="text-xs text-muted-foreground">
                  启用飞书通道
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="feishu-long"
                  checked={feishuForm.use_long_connection}
                  onCheckedChange={(checked) =>
                    setFeishuForm((f) => ({ ...f, use_long_connection: checked }))
                  }
                />
                <Label htmlFor="feishu-long" className="text-xs text-muted-foreground">
                  使用长连接收事件
                </Label>
              </div>
            </div>

            {feishu ? (
              <p className="mt-2 text-xs text-muted-foreground">
                当前有效 App ID: {feishu.app_id_effective || "—"}
                {feishu.app_secret_preview
                  ? ` · Secret ${feishu.app_secret_preview}`
                  : ""}
              </p>
            ) : null}
            {feishuTestHint ? (
              <p className="mt-2 text-xs text-muted-foreground">{feishuTestHint}</p>
            ) : null}

            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={channelTesting || channelSaving}
                onClick={() => void onTestFeishu()}
              >
                {channelTesting ? "测试中…" : "测试连通性"}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={channelSaving}
                onClick={() => void onSaveFeishu()}
              >
                保存并接入
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={channelSaving}
                onClick={() => void reloadFeishu()}
              >
                重载长连接
              </Button>
            </div>
          </section>
        </TabsContent>
      </Tabs>
    </div>
  );
}
