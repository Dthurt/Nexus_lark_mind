import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ChangeEvent,
} from "react";
import { Mic, Paperclip, Plus, Square, ArrowUp, ListTodo, ShieldCheck, Layers2 } from "lucide-react";

import type { InboxItem } from "@/api/endpoints";
import { ContextMeter } from "@/components/chat/ContextMeter";
import { MentionPopover } from "@/components/composer/MentionPopover";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  applyMentionReplacement,
  detectMentionAt,
  type ContextRef,
} from "@/lib/contextRefs";
import {
  suggestStrongerModel,
  tierMeetsModelFloor,
  type ExperienceTierId,
} from "@/lib/experienceTier";
import {
  cacheHitRate,
  estimateCostCny,
  formatCny,
  formatDurationMs,
  formatTokenCount,
} from "@/lib/pricing";
import { formatUsage } from "@/lib/pretty";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export type ComposerOption = { value: string; label: string };

export type ComposerProps = {
  value?: string;
  onChange?: (v: string) => void;
  providerId?: string;
  modelName?: string;
  onProviderIdChange?: (v: string) => void;
  onModelNameChange?: (v: string) => void;
  providerOptions?: ComposerOption[];
  modelOptions?: ComposerOption[];
  providersDisabled?: boolean;
  modelsDisabled?: boolean;
  toolsEnabled?: boolean;
  onToolsEnabledChange?: (v: boolean) => void;
  agentMode?: string;
  onAgentModeChange?: (v: string) => void;
  autoAccept?: boolean;
  onAutoAcceptChange?: (v: boolean) => void;
  multitask?: boolean;
  onMultitaskChange?: (v: boolean) => void;
  permissionPreset?: "read-only" | "workspace-write" | "danger-full-access" | string;
  onPermissionPresetChange?: (v: "read-only" | "workspace-write" | "danger-full-access") => void;
  planEnforcement?: "hard" | "soft" | string;
  onPlanEnforcementChange?: (v: "hard" | "soft") => void;
  experienceTier?: "fast" | "balanced" | "high" | string;
  onExperienceTierChange?: (v: "fast" | "balanced" | "high") => void;
  reasoningEffort?: "low" | "medium" | "high" | string;
  onReasoningEffortChange?: (v: "low" | "medium" | "high") => void;
  sessionUsage?: Record<string, any>;
  items?: any[];
  tools?: any[];
  cwd?: string;
  workspaceTitle?: string;
  workspaceKind?: string;
  sshHostId?: string;
  contextRefs?: ContextRef[];
  onAddContextRef?: (ref: ContextRef) => void;
  onRemoveContextRef?: (path: string) => void;
  gitBranch?: string;
  gitInsertions?: number;
  gitDeletions?: number;
  busy?: boolean;
  busyEnterMode?: "queue" | "steer";
  onBusyEnterModeChange?: (v: "queue" | "steer") => void;
  inboxItems?: InboxItem[];
  onRemoveInboxItem?: (id: string) => void;
  onProviderChange?: (v: string) => void;
  onModelChange?: (v: string) => void;
  onSend?: (opts?: { alternate?: boolean }) => void;
  onStop?: () => void;
  className?: string;
};

declare global {
  interface Window {
    SpeechRecognition?: any;
    webkitSpeechRecognition?: any;
  }
}

export function Composer({
  value = "",
  onChange,
  providerId = "",
  modelName = "",
  onProviderIdChange,
  onModelNameChange,
  providerOptions = [],
  modelOptions = [],
  providersDisabled = false,
  modelsDisabled = false,
  toolsEnabled = true,
  onToolsEnabledChange,
  agentMode = "agent",
  onAgentModeChange,
  autoAccept = false,
  onAutoAcceptChange,
  multitask = true,
  onMultitaskChange,
  permissionPreset = "workspace-write",
  onPermissionPresetChange,
  planEnforcement = "hard",
  onPlanEnforcementChange,
  experienceTier = "balanced",
  onExperienceTierChange,
  reasoningEffort = "medium",
  onReasoningEffortChange,
  sessionUsage = {},
  items = [],
  tools = [],
  cwd = "",
  workspaceTitle = "",
  workspaceKind = "local",
  sshHostId = "",
  contextRefs = [],
  onAddContextRef,
  onRemoveContextRef,
  gitBranch = "",
  gitInsertions = 0,
  gitDeletions = 0,
  busy = false,
  busyEnterMode = "queue",
  onBusyEnterModeChange,
  inboxItems = [],
  onRemoveInboxItem,
  onProviderChange,
  onModelChange,
  onSend,
  onStop,
  className,
}: ComposerProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRootRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const plusBtnRef = useRef<HTMLButtonElement>(null);
  const [mention, setMention] = useState<{ start: number; query: string } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [listening, setListening] = useState(false);
  const [compactBar, setCompactBar] = useState(
    () => (typeof window !== "undefined" ? window.matchMedia("(max-width: 720px)").matches : false),
  );
  const recognitionRef = useRef<any>(null);
  const voiceBaseRef = useRef("");
  const valueRef = useRef(value);
  valueRef.current = value;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const voiceSupported =
    typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  const tokenStat = formatUsage(sessionUsage);
  const hasDraft = !!(value || "").trim();
  const needsWorkspace = !(cwd || "").trim();
  const needsModel = !(providerId || "").trim() || !(modelName || "").trim();
  const sendBlockedHint = needsWorkspace
    ? "请先绑定工作目录（空态选择器或侧栏工作区）"
    : needsModel
      ? "请先在下方选择 Provider / 模型"
      : "";
  const canSend = hasDraft && !needsWorkspace && !needsModel;
  const actionTitle = busy
    ? hasDraft
      ? "发送到收件箱"
      : "终止"
    : sendBlockedHint || "发送";
  const planOn = agentMode === "plan";
  const busyHint =
    busyEnterMode === "steer"
      ? "Agent 忙碌中 · Enter 中途引导（下一步注入）· Ctrl+Enter 改为排队 · 空内容点按钮终止"
      : "Agent 忙碌中 · Enter 排队（本轮结束后发）· Ctrl+Enter 改为引导 · 空内容点按钮终止";

  const applyExperienceTier = useCallback(
    (id: ExperienceTierId) => {
      onExperienceTierChange?.(id);
      if (tierMeetsModelFloor(id, modelName)) return;
      const stronger = suggestStrongerModel(modelOptions, modelName);
      if (stronger) {
        toast.message(`体验档 ${id} 建议更强模型`, {
          description: `当前 ${modelName || "未选"} 偏弱，可一键切换`,
          action: {
            label: `用 ${stronger}`,
            onClick: () => onModelNameChange?.(stronger),
          },
        });
      } else {
        toast.message(`体验档 ${id} 建议更强模型`, {
          description: "当前模型偏弱，请在 Composer 中切换 Provider / 模型",
        });
      }
    },
    [modelName, modelOptions, onExperienceTierChange, onModelNameChange],
  );

  const modelLabel = useMemo(() => {
    const m = (modelName || "").trim();
    const p = (providerId || "").trim();
    if (m && p) return `${p}/${m}`;
    return m || p || "选择模型";
  }, [modelName, providerId]);

  const lastPromptTokens = useMemo(() => {
    for (let i = items.length - 1; i >= 0; i -= 1) {
      const it = items[i];
      if (it?.kind === "msg" && it.role === "assistant" && it.usage?.prompt_tokens) {
        return Number(it.usage.prompt_tokens) || 0;
      }
    }
    return 0;
  }, [items]);

  const visibleTools = toolsEnabled ? tools : [];

  const sessionCache = useMemo(() => {
    const cached = Number(sessionUsage?.cached_tokens || 0);
    const rate = cacheHitRate(sessionUsage);
    return {
      text:
        cached > 0
          ? `缓存 ${formatTokenCount(cached)} · ${rate >= 10 ? Math.round(rate) : rate.toFixed(1)}%`
          : "缓存 0%",
    };
  }, [sessionUsage]);

  const sessionCost = useMemo(() => {
    const est = estimateCostCny(sessionUsage, { modelName, providerId });
    return formatCny(est.yuan);
  }, [sessionUsage, modelName, providerId]);

  const sessionDuration = formatDurationMs(sessionUsage?.duration_ms);

  const sessionStatsTitle = useMemo(() => {
    const parts = [
      sessionUsage?.estimated ? "本会话累计（含估算）" : "本会话累计",
      tokenStat,
      sessionCache.text,
      sessionCost,
    ];
    if (sessionDuration) parts.push(`耗时 ${sessionDuration}`);
    parts.push("费用按模型大致单价估算（人民币），仅供参考");
    return parts.join(" · ");
  }, [sessionUsage, tokenStat, sessionCache.text, sessionCost, sessionDuration]);

  const stopVoice = useCallback(() => {
    try {
      recognitionRef.current?.stop?.();
    } catch {
      /* ignore */
    }
    setListening(false);
  }, []);

  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    const next = Math.min(Math.max(el.scrollHeight, 34), 160);
    el.style.height = `${next}px`;
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [value, resizeTextarea]);

  const toggleVoice = useCallback(() => {
    if (!voiceSupported || busy) return;
    if (listening) {
      stopVoice();
      return;
    }
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new Ctor();
    recognitionRef.current = recognition;
    recognition.lang = "zh-CN";
    recognition.interimResults = true;
    recognition.continuous = false;
    voiceBaseRef.current = valueRef.current || "";
    let finalText = "";

    const pushVoiceText = (committed: string, interim = "") => {
      const prefix = voiceBaseRef.current;
      const spoken = `${committed}${interim}`.trim();
      if (!spoken) {
        onChangeRef.current?.(prefix);
        return;
      }
      const sep = prefix && !/\s$/.test(prefix) ? " " : "";
      onChangeRef.current?.(prefix + sep + spoken);
    };

    recognition.onstart = () => setListening(true);
    recognition.onerror = (ev: any) => {
      const msg =
        ev?.error === "not-allowed" ? "麦克风权限被拒绝" : `语音失败: ${ev?.error || "unknown"}`;
      toast.error(msg);
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
      if (finalText.trim()) pushVoiceText(finalText.trim());
      requestAnimationFrame(resizeTextarea);
    };
    recognition.onresult = (ev: any) => {
      let gotFinal = false;
      for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
        if (!ev.results[i].isFinal) continue;
        finalText += ev.results[i][0]?.transcript || "";
        gotFinal = true;
      }
      if (!gotFinal) return;
      pushVoiceText(finalText.trim());
      requestAnimationFrame(resizeTextarea);
    };
    try {
      recognition.start();
    } catch (err: any) {
      toast.error(String(err?.message || err));
      setListening(false);
    }
  }, [busy, listening, resizeTextarea, stopVoice, voiceSupported]);

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    function onDocPointer(ev: PointerEvent) {
      if (!menuOpen) return;
      const root = menuRootRef.current;
      if (root && !root.contains(ev.target as Node)) closeMenu();
    }
    function onKey(ev: globalThis.KeyboardEvent) {
      if (ev.key === "Escape") closeMenu();
    }
    document.addEventListener("pointerdown", onDocPointer, true);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("pointerdown", onDocPointer, true);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [menuOpen, closeMenu]);

  useEffect(() => () => stopVoice(), [stopVoice]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 720px)");
    const onChange = () => setCompactBar(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  function onPrimary(e?: FormEvent) {
    e?.preventDefault();
    if (busy) {
      if (hasDraft) onSend?.();
      else onStop?.();
      return;
    }
    if (!canSend) {
      if (sendBlockedHint) toast.error(sendBlockedHint);
      return;
    }
    onSend?.();
  }

  function onTextareaKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (mention && (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Escape")) {
      // MentionPopover listens on window capture; don't send.
      return;
    }
    if (e.key === "Escape") {
      closeMenu();
      setMention(null);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      if (mention) return; // popover handles Enter
      e.preventDefault();
      const alternate = e.ctrlKey || e.metaKey;
      if (busy) {
        if (hasDraft) onSend?.({ alternate });
        return;
      }
      if (!canSend) {
        if (sendBlockedHint) toast.error(sendBlockedHint);
        return;
      }
      onSend?.({ alternate });
    }
  }

  function onTextareaChange(e: ChangeEvent<HTMLTextAreaElement>) {
    const next = e.target.value;
    onChange?.(next);
    const caret = e.target.selectionStart ?? next.length;
    setMention(detectMentionAt(next, caret));
    requestAnimationFrame(resizeTextarea);
  }

  function onMentionSelect(ref: ContextRef) {
    const el = textareaRef.current;
    const caret = el?.selectionStart ?? value.length;
    const hit = mention || detectMentionAt(value, caret);
    if (hit) {
      const { text, caret: nextCaret } = applyMentionReplacement(
        value,
        hit.start,
        caret,
        ref.path || ref.label || "",
      );
      onChange?.(text);
      requestAnimationFrame(() => {
        if (el) {
          el.focus();
          el.setSelectionRange(nextCaret, nextCaret);
        }
        resizeTextarea();
      });
    }
    onAddContextRef?.(ref);
    setMention(null);
  }

  function pickFile() {
    fileInputRef.current?.click();
  }

  function onFilePicked(ev: ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    if (!file) return;
    const name = file.name || "file";
    const pathHint = (file as any).path || name;
    onAddContextRef?.({ path: String(pathHint).replace(/\\/g, "/"), kind: "file", label: name });
    const base = value || "";
    const mentionTok = `@${pathHint}`;
    const next = base.trim() ? `${base.trim()}\n${mentionTok}` : mentionTok;
    onChange?.(next);
    ev.target.value = "";
    closeMenu();
    requestAnimationFrame(() => plusBtnRef.current?.focus());
  }

  return (
    <form className={cn("composer w-full min-w-0", className)} onSubmit={onPrimary}>
      <div
        className={cn(
          "composer-shell flex w-full min-w-0 flex-col overflow-visible rounded-xl border border-border bg-muted/40 transition-shadow",
          "focus-within:border-primary/50 focus-within:shadow-[0_0_0_2px_rgba(58,156,240,0.12)]",
          busy && "busy ring-1 ring-primary/35",
        )}
      >
        {busy ? (
          <div className="flex flex-wrap items-center gap-2 border-b border-border/60 px-2.5 py-1.5 text-[11px]">
            <span className="text-muted-foreground">忙碌时可发消息：</span>
            <div className="inline-flex rounded-md border border-border/70 p-0.5">
              <button
                type="button"
                className={cn(
                  "rounded px-2 py-0.5 font-medium transition-colors",
                  busyEnterMode === "steer"
                    ? "bg-violet-500/20 text-violet-700 dark:text-violet-200"
                    : "text-muted-foreground hover:text-foreground",
                )}
                title="在下一个模型步骤前注入，打断当前思路"
                onClick={() => onBusyEnterModeChange?.("steer")}
              >
                中途引导
              </button>
              <button
                type="button"
                className={cn(
                  "rounded px-2 py-0.5 font-medium transition-colors",
                  busyEnterMode === "queue"
                    ? "bg-sky-500/20 text-sky-700 dark:text-sky-200"
                    : "text-muted-foreground hover:text-foreground",
                )}
                title="等本轮结束后作为下一条用户消息发送"
                onClick={() => onBusyEnterModeChange?.("queue")}
              >
                排队
              </button>
            </div>
            <span className="text-muted-foreground">
              Enter 发送到
              {busyEnterMode === "steer" ? "引导" : "排队"}
              · Ctrl+Enter 临时切换
            </span>
          </div>
        ) : null}

        {inboxItems.length ? (
          <ul className="flex max-h-28 flex-col gap-1 overflow-y-auto border-b border-border/60 px-2.5 py-1.5">
            {inboxItems.map((it) => (
              <li
                key={it.id}
                className="flex items-start gap-2 rounded-md bg-muted/40 px-2 py-1.5 text-[12px]"
              >
                <span
                  className={cn(
                    "mt-0.5 shrink-0 rounded px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                    it.kind === "steer"
                      ? "bg-violet-500/15 text-violet-700 dark:text-violet-300"
                      : "bg-sky-500/15 text-sky-700 dark:text-sky-300",
                  )}
                >
                  {it.kind === "steer" ? "引导" : "排队"}
                </span>
                <span className="min-w-0 flex-1 whitespace-pre-wrap break-words text-foreground/90">
                  {it.content}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 shrink-0 px-1.5 text-[11px] text-muted-foreground"
                  onClick={() => onRemoveInboxItem?.(it.id)}
                >
                  撤销
                </Button>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="grid min-w-0 grid-cols-[auto_1fr_auto] items-end gap-1.5 px-2 pb-1 pt-1.5">
          <div ref={menuRootRef} className="relative self-end pb-1.5">
            <Button
              ref={plusBtnRef}
              type="button"
              variant="outline"
              size="icon"
              className={cn(
                "size-[26px] rounded-full text-muted-foreground",
                menuOpen && "border-foreground/20 bg-muted text-foreground",
              )}
              title="附件 · 模式 · 模型"
              aria-label="打开附件与模式菜单"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
            >
              <Plus className="size-3.5" />
            </Button>

            {menuOpen ? (
              <div
                className="absolute bottom-[calc(100%+8px)] left-0 z-40 flex w-[min(300px,78vw)] flex-col gap-0.5 rounded-xl border border-border bg-popover p-2 shadow-lg"
                role="menu"
              >
                <button
                  type="button"
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] hover:bg-muted"
                  role="menuitem"
                  onClick={pickFile}
                >
                  <Paperclip className="size-3.5 text-muted-foreground" aria-hidden />
                  <span className="font-medium">添加文件</span>
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  onChange={onFilePicked}
                />

                <div className="my-1 h-px bg-border" />
                <div className="px-2 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                  模式
                </div>

                <MenuToggle
                  label="Plan Mode"
                  checked={planOn}
                  onChange={(on) => onAgentModeChange?.(on ? "plan" : "agent")}
                />
                {planOn ? (
                  <MenuToggle
                    label="Plan 硬约束"
                    hint={planEnforcement === "soft" ? "当前：软提示" : "当前：禁写/shell"}
                    checked={planEnforcement !== "soft"}
                    onChange={(on) => onPlanEnforcementChange?.(on ? "hard" : "soft")}
                  />
                ) : null}
                <MenuToggle
                  label="Accept"
                  hint="自动接受写/shell"
                  checked={autoAccept}
                  onChange={(on) => onAutoAcceptChange?.(on)}
                />
                <MenuToggle
                  label="Multi-Task"
                  hint="允许子 agent"
                  checked={multitask}
                  onChange={(on) => onMultitaskChange?.(on)}
                />

                <div className="my-1 h-px bg-border" />
                <div className="px-2 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                  工具
                </div>
                <MenuToggle
                  label="启用工具"
                  checked={toolsEnabled}
                  onChange={(on) => onToolsEnabledChange?.(on)}
                />

                <div className="my-1 h-px bg-border" />
                <div className="px-2 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                  模型
                </div>
                {providersDisabled ? (
                  <p className="px-2 pb-1 text-[11px] leading-relaxed text-amber-200/90">
                    未检测到可用 Provider。请在 <strong>Settings → Models</strong> 配置
                    API Key，或检查 <code className="text-[10px]">.env</code>{" "}
                    中的模型密钥后刷新页面。
                  </p>
                ) : null}
                <div className="flex flex-col gap-1 px-2 pb-2 pt-1">
                  <label className="text-[11px] text-muted-foreground">Provider</label>
                  <Select
                    value={providerId ? providerId : "__empty"}
                    disabled={providersDisabled}
                    onValueChange={(v) => {
                      const next = v === "__empty" ? "" : v;
                      onProviderIdChange?.(next);
                      onProviderChange?.(next);
                    }}
                  >
                    <SelectTrigger className="h-8 w-full text-xs" aria-label="Provider">
                      <SelectValue placeholder="选择 Provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {providerOptions.map((opt) => (
                        <SelectItem
                          key={opt.value || "empty"}
                          value={opt.value || "__empty"}
                        >
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1 px-2 pb-2">
                  <label className="text-[11px] text-muted-foreground">Model</label>
                  <Select
                    value={modelName ? modelName : "__empty"}
                    disabled={modelsDisabled}
                    onValueChange={(v) => {
                      const next = v === "__empty" ? "" : v;
                      onModelNameChange?.(next);
                      onModelChange?.(next);
                    }}
                  >
                    <SelectTrigger className="h-8 w-full text-xs" aria-label="Model">
                      <SelectValue placeholder="选择 Model" />
                    </SelectTrigger>
                    <SelectContent>
                      {modelOptions.map((opt) => (
                        <SelectItem
                          key={opt.value || "empty"}
                          value={opt.value || "__empty"}
                        >
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ) : null}
          </div>

          <div className="flex min-w-0 items-start gap-1.5">
            {planOn || autoAccept || multitask ? (
              <div className="flex shrink-0 items-center gap-1 pt-[7px]" aria-label="已启用模式">
                {planOn ? (
                  <button
                    type="button"
                    className="inline-flex size-[22px] items-center justify-center rounded-md border border-amber-400/35 bg-amber-400/12 text-amber-400 transition-colors hover:bg-amber-400/20"
                    title="Plan Mode（点击关闭）"
                    aria-label="关闭 Plan Mode"
                    disabled={busy}
                    onClick={() => onAgentModeChange?.("agent")}
                  >
                    <ListTodo className="size-3.5" strokeWidth={2.25} />
                  </button>
                ) : null}
                {autoAccept ? (
                  <button
                    type="button"
                    className="inline-flex size-[22px] items-center justify-center rounded-md border border-emerald-400/35 bg-emerald-400/12 text-emerald-400 transition-colors hover:bg-emerald-400/20"
                    title="Accept（点击关闭）"
                    aria-label="关闭 Accept"
                    disabled={busy}
                    onClick={() => onAutoAcceptChange?.(false)}
                  >
                    <ShieldCheck className="size-3.5" strokeWidth={2.25} />
                  </button>
                ) : null}
                {multitask ? (
                  <button
                    type="button"
                    className="inline-flex size-[22px] items-center justify-center rounded-md border border-violet-400/35 bg-violet-400/12 text-violet-700 transition-colors hover:bg-violet-400/20 dark:text-violet-300"
                    title="Multi-Task 子 agent（点击关闭）"
                    aria-label="关闭 Multi-Task"
                    disabled={busy}
                    onClick={() => onMultitaskChange?.(false)}
                  >
                    <Layers2 className="size-3.5" strokeWidth={2.25} />
                  </button>
                ) : null}
              </div>
            ) : null}

            {contextRefs.length ? (
              <div className="mb-1 flex flex-wrap gap-1">
                {contextRefs.map((r) => (
                  <button
                    key={`${r.kind}:${r.path}`}
                    type="button"
                    className="inline-flex max-w-[200px] items-center gap-1 rounded-md border border-teal/30 bg-teal/10 px-1.5 py-0.5 font-mono text-[10px] text-teal"
                    title="点击移除"
                    onClick={() => onRemoveContextRef?.(r.path)}
                  >
                    <span className="truncate">@{r.path}</span>
                    <span className="opacity-60">×</span>
                  </button>
                ))}
              </div>
            ) : null}

            <div className="relative min-w-0 flex-1">
              <MentionPopover
                open={!!mention}
                query={mention?.query || ""}
                cwd={cwd}
                workspaceKind={workspaceKind}
                sshHostId={sshHostId}
                onSelect={onMentionSelect}
                onClose={() => setMention(null)}
              />
              <Textarea
                ref={textareaRef}
                value={value}
                placeholder={
                  busy
                    ? busyHint
                    : needsWorkspace
                      ? "先绑定工作目录，再输入消息…"
                      : needsModel
                        ? "先选择 Provider / 模型，再输入消息…"
                        : "输入消息 · @ 附加文件 · Enter 发送 · Shift+Enter 换行"
                }
                onChange={onTextareaChange}
                onKeyDown={onTextareaKeyDown}
                onSelect={(e) => {
                  const el = e.currentTarget;
                  setMention(detectMentionAt(el.value, el.selectionStart ?? 0));
                }}
                className="min-h-[34px] max-h-40 min-w-0 flex-1 resize-none overflow-y-auto border-0 bg-transparent px-0.5 py-1.5 leading-[1.4] shadow-none focus-visible:ring-0"
                rows={1}
              />
            </div>
          </div>

          <div className="flex items-end gap-1.5 self-end pb-1.5">
            {voiceSupported ? (
              <Button
                type="button"
                variant="outline"
                size="icon"
                className={cn(
                  "size-[30px] rounded-full text-muted-foreground",
                  listening && "animate-pulse border-destructive/50 bg-destructive/75 text-white",
                )}
                disabled={busy && !hasDraft}
                title={listening ? "停止语音输入" : "语音输入"}
                aria-label={listening ? "停止语音输入" : "语音输入"}
                onClick={toggleVoice}
              >
                <Mic className="size-3.5" />
              </Button>
            ) : null}
            <Button
              type="submit"
              variant="outline"
              size="icon"
              className={cn(
                "size-[30px] rounded-full",
                busy && !hasDraft
                  ? "border-destructive/45 bg-destructive/15 text-destructive hover:bg-destructive/25 hover:text-destructive"
                  : canSend
                    ? "border-primary/40 bg-primary/12 text-primary hover:bg-primary/18 hover:text-primary"
                    : "text-muted-foreground opacity-35",
              )}
              disabled={!busy && !canSend}
              title={actionTitle}
              aria-label={actionTitle}
            >
              {busy && !hasDraft ? (
                <Square className="size-3 fill-current" />
              ) : (
                <ArrowUp className="size-3.5" strokeWidth={2.25} />
              )}
            </Button>
          </div>
        </div>

        {!compactBar ? (
          <div className="flex flex-wrap items-start gap-x-4 gap-y-2 border-t border-border/60 px-2.5 py-2">
            <ComposerSegmentGroup
              label="权限"
              hint={
                permissionPreset === "read-only"
                  ? "禁写/shell"
                  : permissionPreset === "danger-full-access"
                    ? "不问了"
                    : "写需审批"
              }
              options={[
                { id: "read-only", label: "只读" },
                { id: "workspace-write", label: "可写" },
                { id: "danger-full-access", label: "全权限" },
              ]}
              value={permissionPreset}
              onChange={(v) =>
                onPermissionPresetChange?.(v as "read-only" | "workspace-write" | "danger-full-access")
              }
              disabled={busy}
            />
            <ComposerSegmentGroup
              label="体验档"
              hint={
                experienceTier === "fast"
                  ? "仅 Mermaid"
                  : experienceTier === "high"
                    ? "偏 Draw.io"
                    : "默认"
              }
              options={[
                { id: "fast", label: "Fast" },
                { id: "balanced", label: "Balanced" },
                { id: "high", label: "High" },
              ]}
              value={experienceTier}
              onChange={(v) => applyExperienceTier(v as ExperienceTierId)}
              disabled={busy}
            />
            <ComposerSegmentGroup
              label="推理"
              hint={
                reasoningEffort === "low"
                  ? "简短"
                  : reasoningEffort === "high"
                    ? "更深"
                    : "默认"
              }
              options={[
                { id: "low", label: "Low" },
                { id: "medium", label: "Med" },
                { id: "high", label: "High" },
              ]}
              value={reasoningEffort}
              onChange={(v) => onReasoningEffortChange?.(v as "low" | "medium" | "high")}
              disabled={busy}
            />
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-1 border-t border-border/60 px-2 py-1.5">
            {(
              [
                ["read-only", "只读"],
                ["workspace-write", "可写"],
                ["danger-full-access", "全开"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-medium",
                  permissionPreset === id
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:text-foreground",
                )}
                disabled={busy}
                onClick={() => onPermissionPresetChange?.(id)}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        <div className="flex w-full min-w-0 flex-nowrap items-center gap-2 border-t border-border px-2 pb-2 pt-1.5">
          {cwd ? (
            <div className="inline-flex max-w-[48%] min-w-0 flex-nowrap items-center gap-2" title={cwd}>
              <span className="inline-flex min-w-0 max-w-full items-center gap-1 text-xs text-muted-foreground">
                <FolderIcon />
                <span className="truncate">{workspaceTitle || cwd}</span>
              </span>
              {gitBranch ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-xs text-teal">
                  <BranchIcon />
                  <span className="max-w-[88px] truncate">{gitBranch}</span>
                  {gitInsertions || gitDeletions ? (
                    <span
                      className="ml-0.5 inline-flex gap-1 font-mono text-[10px]"
                      title={`相对 HEAD：+${gitInsertions} / -${gitDeletions}`}
                    >
                      {gitInsertions ? (
                        <span className="text-[#3ecf8e]">+{gitInsertions}</span>
                      ) : null}
                      {gitDeletions ? (
                        <span className="text-[#e07070]">-{gitDeletions}</span>
                      ) : null}
                    </span>
                  ) : null}
                </span>
              ) : null}
              {workspaceKind === "ssh" ? (
                <span className="shrink-0 rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground">
                  SSH
                </span>
              ) : null}
            </div>
          ) : null}

          <button
            type="button"
            className="max-w-[160px] truncate rounded-md border border-transparent bg-transparent px-1.5 py-0.5 font-mono text-xs text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground"
            title={modelLabel}
            onClick={() => setMenuOpen((v) => !v)}
          >
            {modelLabel}
          </button>

          <span
            className="ml-auto inline-flex min-w-0 flex-nowrap items-center justify-end gap-1.5"
            title={sessionStatsTitle}
          >
            <span className="shrink-0 whitespace-nowrap font-mono text-xs text-muted-foreground">
              {tokenStat}
            </span>
            <span className="shrink-0 whitespace-nowrap font-mono text-xs text-violet-700 dark:text-violet-300/90">
              {sessionCache.text}
            </span>
            <span className="shrink-0 whitespace-nowrap font-mono text-xs text-emerald-700 dark:text-emerald-300/90">
              {sessionCost}
            </span>
            <ContextMeter
              items={items}
              tools={visibleTools}
              modelName={modelName}
              cwd={cwd}
              workspaceTitle={workspaceTitle}
              lastPromptTokens={lastPromptTokens}
              draft={value}
            />
          </span>
        </div>
      </div>
    </form>
  );
}

function ComposerSegmentGroup({
  label,
  hint,
  options,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  hint: string;
  options: { id: string; label: string }[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="inline-flex rounded-md border border-border/70 p-0.5">
        {options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            disabled={disabled}
            className={cn(
              "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
              value === opt.id
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
            onClick={() => onChange(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{hint}</p>
    </div>
  );
}

function MenuToggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "grid w-full grid-cols-[1fr_auto] items-center gap-x-2.5 gap-y-0.5 rounded-lg px-2.5 py-2 text-left text-[13px] hover:bg-muted",
        checked && "on",
      )}
      role="menuitemcheckbox"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
    >
      <span className="font-medium">{label}</span>
      {hint ? <span className="col-start-1 row-start-2 text-[11px] text-muted-foreground">{hint}</span> : null}
      <Switch
        checked={checked}
        onCheckedChange={onChange}
        className={cn(hint ? "row-span-2" : "", "pointer-events-none")}
        tabIndex={-1}
        aria-hidden
      />
    </button>
  );
}

function FolderIcon() {
  return (
    <svg className="size-3 shrink-0" viewBox="0 0 24 24" aria-hidden>
      <path
        d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function BranchIcon() {
  return (
    <svg className="size-3 shrink-0" viewBox="0 0 24 24" aria-hidden>
      <circle cx="6" cy="6" r="2.2" fill="currentColor" />
      <circle cx="6" cy="18" r="2.2" fill="currentColor" />
      <circle cx="18" cy="12" r="2.2" fill="currentColor" />
      <path
        d="M6 8v8M8 6c6 0 8 2 8 6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default Composer;
