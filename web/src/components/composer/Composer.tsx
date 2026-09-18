import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ChangeEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Mic, Paperclip, Plus, Square, ArrowUp, ListTodo, ShieldCheck, Layers2 } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import type { InboxItem, LocalKnowledgeBase, WeknoraHealth, WeknoraKb } from "@/api/endpoints";
import { deleteSessionUpload, listSessionUploads, uploadSessionDoc } from "@/api/endpoints";
import { ContextMeter } from "@/components/chat/ContextMeter";
import { KnowledgeScopePicker } from "@/components/knowledge/KnowledgeScopePicker";
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
import { composerKbPlaceholder, kbScopeLabel } from "@/lib/knowledgeScope";
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
  weknoraKbId?: string;
  weknoraKbName?: string;
  knowledgeKbs?: WeknoraKb[];
  localKbs?: LocalKnowledgeBase[];
  knowledgeHealth?: WeknoraHealth | null;
  onWeknoraKbChange?: (kbId: string, kbName: string) => void;
  onOpenKnowledge?: () => void;
  sessionId?: string;
  workspaceId?: string;
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
  weknoraKbId = "",
  weknoraKbName = "",
  knowledgeKbs = [],
  localKbs = [],
  knowledgeHealth = null,
  onWeknoraKbChange,
  onOpenKnowledge,
  sessionId = "",
  workspaceId = "",
  className,
}: ComposerProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRootRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const plusBtnRef = useRef<HTMLButtonElement>(null);
  const [mention, setMention] = useState<{ start: number; query: string } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [listening, setListening] = useState(false);
  const [uploads, setUploads] = useState<Array<{ doc_id: string; title: string }>>([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setUploads([]);
      return;
    }
    let cancelled = false;
    void listSessionUploads(sessionId)
      .then((data) => {
        if (cancelled) return;
        const docs = data?.docs || [];
        setUploads(
          docs.map((d) => ({
            doc_id: String(d.doc_id || ""),
            title: String(d.title || d.filename || d.doc_id || "upload"),
          })).filter((u) => u.doc_id),
        );
      })
      .catch(() => {
        if (!cancelled) setUploads([]);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);
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
    function isInsideFloatingUi(target: EventTarget | null) {
      if (!(target instanceof Element)) return false;
      // Radix Select / Popper content is portaled outside the plus-menu root.
      return !!target.closest(
        '[data-radix-popper-content-wrapper], [data-radix-select-viewport], [role="listbox"], [data-slot="select-content"]',
      );
    }
    function onDocPointer(ev: PointerEvent) {
      if (!menuOpen) return;
      if (isInsideFloatingUi(ev.target)) return;
      const root = menuRootRef.current;
      if (root && !root.contains(ev.target as Node)) closeMenu();
    }
    function onKey(ev: globalThis.KeyboardEvent) {
      if (ev.key !== "Escape") return;
      // Let an open Select close first; don't tear down the whole plus menu.
      if (document.querySelector('[data-radix-popper-content-wrapper] [role="listbox"], [role="listbox"]')) {
        return;
      }
      closeMenu();
    }
    document.addEventListener("pointerdown", onDocPointer, true);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("pointerdown", onDocPointer, true);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [menuOpen, closeMenu]);

  useEffect(() => () => stopVoice(), [stopVoice]);

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

  async function onFilePicked(ev: ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    if (!file) return;
    const name = file.name || "file";
    if (sessionId) {
      setUploading(true);
      try {
        const row = await uploadSessionDoc(sessionId, file, workspaceId);
        const title = String(row.title || name);
        const docId = String(row.doc_id || "");
        if (docId) {
          setUploads((prev) => [...prev.filter((u) => u.doc_id !== docId), { doc_id: docId, title }]);
        }
        toast.success(`已上传 ${title}，本轮对话会检索该附件`);
      } catch (err: any) {
        toast.error(String(err?.message || err || "上传失败"));
      } finally {
        setUploading(false);
        ev.target.value = "";
        closeMenu();
        requestAnimationFrame(() => plusBtnRef.current?.focus());
      }
      return;
    }
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

  async function removeUpload(docId: string) {
    if (!sessionId) return;
    try {
      await deleteSessionUpload(sessionId, docId);
      setUploads((prev) => prev.filter((u) => u.doc_id !== docId));
    } catch (err: any) {
      toast.error(String(err?.message || err));
    }
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
              title="附件 · 模式 · 权限 · 模型"
              aria-label="打开附件、模式与权限菜单"
              aria-expanded={menuOpen}
              data-testid="composer-attach-btn"
              onClick={() => setMenuOpen((v) => !v)}
            >
              <Plus className="size-3.5" />
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              data-testid="composer-file-input"
              accept=".md,.markdown,.mdx,.txt,.rst,.org,.pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.webp,.gif,.bmp"
              onChange={onFilePicked}
            />

            {menuOpen ? (
              <div
                className="absolute bottom-[calc(100%+8px)] left-0 z-40 flex max-h-[min(72vh,560px)] w-[min(360px,90vw)] flex-col gap-0.5 overflow-y-auto rounded-xl border border-border bg-popover p-2 shadow-lg"
                role="menu"
              >
                <button
                  type="button"
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] hover:bg-muted"
                  role="menuitem"
                  onClick={pickFile}
                >
                  <Paperclip className="size-3.5 text-muted-foreground" aria-hidden />
                  <span className="font-medium">{uploading ? "上传中…" : "添加文件"}</span>
                </button>

                <div className="my-1 h-px bg-border" />
                <div className="px-2 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                  模型
                </div>
                {providersDisabled ? (
                  <p className="px-2 pb-1 text-[11px] leading-relaxed text-amber-800 dark:text-amber-200/90">
                    未检测到可用 Provider。请在 <strong>Settings → Models</strong> 配置
                    API Key，或检查 <code className="text-[10px]">.env</code>{" "}
                    中的模型密钥后刷新页面。
                  </p>
                ) : null}
                <div className="grid grid-cols-2 gap-2 px-2 pb-2 pt-1">
                  <div className="flex min-w-0 flex-col gap-1">
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
                        <SelectValue placeholder="Provider" />
                      </SelectTrigger>
                      <SelectContent className="z-[200]" position="popper" sideOffset={6}>
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
                  <div className="flex min-w-0 flex-col gap-1">
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
                        <SelectValue placeholder="Model" />
                      </SelectTrigger>
                      <SelectContent className="z-[200]" position="popper" sideOffset={6}>
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

                <div className="my-1 h-px bg-border" />
                <div className="px-2 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                  模式
                </div>

                <div className="grid grid-cols-4 gap-1 px-2 pb-1.5 pt-1">
                  {(
                    [
                      {
                        id: "plan",
                        label: "Plan",
                        hint: "只读规划",
                        checked: planOn,
                        onChange: (on: boolean) => onAgentModeChange?.(on ? "plan" : "agent"),
                      },
                      {
                        id: "accept",
                        label: "Accept",
                        hint: "自动接受写/shell",
                        checked: autoAccept,
                        onChange: (on: boolean) => onAutoAcceptChange?.(on),
                      },
                      {
                        id: "multitask",
                        label: "Multi",
                        hint: "允许子 agent",
                        checked: multitask,
                        onChange: (on: boolean) => onMultitaskChange?.(on),
                      },
                      {
                        id: "tools",
                        label: "工具",
                        hint: "启用工具调用",
                        checked: toolsEnabled,
                        onChange: (on: boolean) => onToolsEnabledChange?.(on),
                      },
                    ] as const
                  ).map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      title={m.hint}
                      role="menuitemcheckbox"
                      aria-checked={m.checked}
                      className={cn(
                        "rounded-md px-0.5 py-1.5 text-center text-[11px] font-medium transition-colors",
                        m.checked
                          ? "bg-teal/15 text-teal"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                      onClick={() => m.onChange(!m.checked)}
                    >
                      {m.label}
                    </button>
                  ))}
                  {(
                    [
                      {
                        id: "plan",
                        checked: planOn,
                        onChange: (on: boolean) => onAgentModeChange?.(on ? "plan" : "agent"),
                        label: "Plan Mode",
                      },
                      {
                        id: "accept",
                        checked: autoAccept,
                        onChange: (on: boolean) => onAutoAcceptChange?.(on),
                        label: "Accept",
                      },
                      {
                        id: "multitask",
                        checked: multitask,
                        onChange: (on: boolean) => onMultitaskChange?.(on),
                        label: "Multi-Task",
                      },
                      {
                        id: "tools",
                        checked: toolsEnabled,
                        onChange: (on: boolean) => onToolsEnabledChange?.(on),
                        label: "启用工具",
                      },
                    ] as const
                  ).map((m) => (
                    <div key={`sw-${m.id}`} className="flex justify-center py-0.5">
                      <Switch
                        checked={m.checked}
                        onCheckedChange={m.onChange}
                        aria-label={m.label}
                      />
                    </div>
                  ))}
                </div>
                {planOn ? (
                  <MenuToggle
                    label="Plan 硬约束"
                    hint={planEnforcement === "soft" ? "当前：软提示" : "当前：禁写/shell"}
                    checked={planEnforcement !== "soft"}
                    onChange={(on) => onPlanEnforcementChange?.(on ? "hard" : "soft")}
                  />
                ) : null}

                <div className="my-1 h-px bg-border" />
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
                />
              </div>
            ) : null}
          </div>

          <div className="flex min-w-0 items-start gap-1.5">
            {planOn || autoAccept || multitask ? (
              <div className="flex shrink-0 items-center gap-1 pt-[7px]" aria-label="已启用模式">
                {planOn ? (
                  <button
                    type="button"
                    className="inline-flex size-[22px] items-center justify-center rounded-md border border-amber-500/35 bg-amber-500/12 text-amber-800 transition-colors hover:bg-amber-500/20 dark:text-amber-300"
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
                    className="inline-flex size-[22px] items-center justify-center rounded-md border border-emerald-500/35 bg-emerald-500/12 text-emerald-800 transition-colors hover:bg-emerald-500/20 dark:text-emerald-300"
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

            {uploads.length || contextRefs.length ? (
              <div className="mb-1 flex flex-wrap gap-1">
                {uploads.map((u) => (
                  <button
                    key={u.doc_id}
                    type="button"
                    data-testid="session-upload-chip"
                    className="inline-flex max-w-[200px] items-center gap-1 rounded-md border border-amber-500/35 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-900 dark:text-amber-200"
                    title="点击移除会话附件"
                    onClick={() => void removeUpload(u.doc_id)}
                  >
                    <span className="truncate">{u.title}</span>
                    <span className="opacity-60">×</span>
                  </button>
                ))}
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
                        : composerKbPlaceholder(weknoraKbId, weknoraKbName)
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

        <div className="flex w-full min-w-0 flex-nowrap items-center gap-2 border-t border-border px-2 pb-2 pt-1.5">
          {cwd ? (
            <div className="inline-flex max-w-[36%] min-w-0 flex-nowrap items-center gap-2" title={cwd}>
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

          <KnowledgeScopePicker
            value={weknoraKbId}
            name={weknoraKbName}
            kbs={knowledgeKbs}
            localKbs={localKbs}
            health={knowledgeHealth}
            onChange={onWeknoraKbChange}
            onOpenKnowledge={onOpenKnowledge}
          />

          <button
            type="button"
            className="max-w-[140px] truncate rounded-md border border-transparent bg-transparent px-1.5 py-0.5 font-mono text-xs text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground"
            title={`${modelLabel} · 基于「${kbScopeLabel(weknoraKbId, weknoraKbName)}」`}
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
  const trackRef = useRef<HTMLDivElement>(null);
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const dragRef = useRef<{ startX: number; moved: boolean; idx: number } | null>(null);
  const suppressClickRef = useRef(false);
  const reducedMotion = useReducedMotion();
  const [pill, setPill] = useState({ left: 0, width: 0, ready: false });

  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.id === value),
  );

  const syncPill = useCallback((idx: number) => {
    const btn = btnRefs.current[idx];
    if (!btn) return;
    setPill({ left: btn.offsetLeft, width: btn.offsetWidth, ready: true });
  }, []);

  useLayoutEffect(() => {
    if (dragRef.current) return;
    syncPill(selectedIndex);
  }, [selectedIndex, syncPill, options.length, value]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      if (dragRef.current) return;
      syncPill(selectedIndex);
    });
    ro.observe(track);
    return () => ro.disconnect();
  }, [selectedIndex, syncPill]);

  const indexFromClientX = useCallback(
    (clientX: number) => {
      const track = trackRef.current;
      if (!track || !options.length) return selectedIndex;
      const rect = track.getBoundingClientRect();
      const x = Math.min(Math.max(clientX - rect.left, 0), Math.max(rect.width - 0.001, 0));
      return Math.min(options.length - 1, Math.floor((x / rect.width) * options.length));
    },
    [options.length, selectedIndex],
  );

  const commitIndex = useCallback(
    (idx: number) => {
      const id = options[idx]?.id;
      if (!id) return;
      if (id !== value) onChange(id);
      else syncPill(idx);
    },
    [onChange, options, syncPill, value],
  );

  const onTrackPointerDown = (ev: ReactPointerEvent<HTMLDivElement>) => {
    if (disabled || ev.button !== 0) return;
    ev.currentTarget.setPointerCapture(ev.pointerId);
    const idx = indexFromClientX(ev.clientX);
    dragRef.current = { startX: ev.clientX, moved: false, idx };
    syncPill(idx);
  };

  const onTrackPointerMove = (ev: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    if (Math.abs(ev.clientX - drag.startX) > 4) drag.moved = true;
    const idx = indexFromClientX(ev.clientX);
    if (idx === drag.idx) return;
    drag.idx = idx;
    syncPill(idx);
  };

  const endDrag = (ev: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    suppressClickRef.current = drag.moved;
    try {
      ev.currentTarget.releasePointerCapture(ev.pointerId);
    } catch {
      /* already released */
    }
    commitIndex(drag.idx);
  };

  const onTrackKeyDown = (ev: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight" && ev.key !== "Home" && ev.key !== "End") {
      return;
    }
    ev.preventDefault();
    let next = selectedIndex;
    if (ev.key === "ArrowLeft") next = Math.max(0, selectedIndex - 1);
    if (ev.key === "ArrowRight") next = Math.min(options.length - 1, selectedIndex + 1);
    if (ev.key === "Home") next = 0;
    if (ev.key === "End") next = options.length - 1;
    commitIndex(next);
  };

  return (
    <div className="min-w-0 px-2 py-1.5">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 px-0.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <span className="truncate text-[10px] text-muted-foreground/85">{hint}</span>
      </div>
      <div
        ref={trackRef}
        role="radiogroup"
        aria-label={label}
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled || undefined}
        onKeyDown={onTrackKeyDown}
        onPointerDown={onTrackPointerDown}
        onPointerMove={onTrackPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={cn(
          "relative flex w-full touch-none select-none rounded-lg bg-black/[0.06] p-0.5 ring-1 ring-border/80 dark:bg-white/[0.08]",
          "outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        {pill.ready ? (
          <motion.div
            aria-hidden
            className="pointer-events-none absolute top-0.5 bottom-0.5 z-0 rounded-md bg-teal/18 shadow-sm ring-1 ring-teal/35 dark:bg-teal/25 dark:ring-teal/45"
            initial={false}
            animate={{ left: pill.left, width: pill.width }}
            transition={
              reducedMotion
                ? { duration: 0 }
                : { type: "spring", stiffness: 460, damping: 34, mass: 0.7 }
            }
          />
        ) : null}
        {options.map((opt, i) => {
          const active = opt.id === value;
          return (
            <button
              key={opt.id}
              ref={(el) => {
                btnRefs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              className={cn(
                "relative z-[1] min-w-0 flex-1 rounded-md px-1.5 py-1.5 text-[11px] font-medium transition-colors duration-150",
                active
                  ? "text-teal dark:text-teal"
                  : "text-muted-foreground hover:text-foreground/85",
              )}
              onClick={() => {
                if (suppressClickRef.current) {
                  suppressClickRef.current = false;
                  return;
                }
                onChange(opt.id);
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
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
