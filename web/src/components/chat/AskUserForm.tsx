import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type AskQuestion = {
  id: string;
  prompt: string;
  options?: { id: string; label: string }[];
  allow_multiple?: boolean;
  allow_custom?: boolean;
};

export type AskUserItem = {
  id?: string;
  title?: string;
  status?: string;
  questions?: AskQuestion[];
  answers?: unknown;
};

export type AskUserFormProps = {
  item: AskUserItem;
  onSubmit?: (ev: { answers: Record<string, { selected: unknown; custom: string | null }> }) => void;
  onDismiss?: () => void;
  className?: string;
};

export function AskUserForm({ item, onSubmit, onDismiss, className }: AskUserFormProps) {
  const pending = item.status === "pending";
  const questions = item.questions || [];

  const [state, setState] = useState<Record<string, string | string[]>>({});
  const [customs, setCustoms] = useState<Record<string, string>>({});

  useEffect(() => {
    setState((prev) => {
      const next = { ...prev };
      for (const q of questions) {
        if (next[q.id] === undefined) next[q.id] = q.allow_multiple ? [] : "";
      }
      return next;
    });
    setCustoms((prev) => {
      const next = { ...prev };
      for (const q of questions) {
        if (next[q.id] === undefined) next[q.id] = "";
      }
      return next;
    });
  }, [questions]);

  const answeredLabel = useMemo(
    () => (item.status === "answered" ? "已回答" : item.status),
    [item.status],
  );

  function toggleMulti(qid: string, oid: string) {
    setState((prev) => {
      const cur = Array.isArray(prev[qid]) ? [...(prev[qid] as string[])] : [];
      const i = cur.indexOf(oid);
      if (i >= 0) cur.splice(i, 1);
      else cur.push(oid);
      return { ...prev, [qid]: cur };
    });
  }

  function handleSubmit() {
    const answers: Record<string, { selected: unknown; custom: string | null }> = {};
    for (const q of questions) {
      const selected = state[q.id];
      const custom = (customs[q.id] || "").trim();
      answers[q.id] = {
        selected: q.allow_multiple ? selected || [] : selected || null,
        custom: q.allow_custom !== false ? custom || null : null,
      };
    }
    onSubmit?.({ answers });
  }

  return (
    <div
      className={cn(
        "grid max-w-[min(100%,720px)] gap-2.5 rounded-[10px] border border-primary/35 bg-primary/10 px-3 py-2.5",
        item.status === "answered" && "opacity-85",
        className,
      )}
    >
      <div className="flex items-center gap-2 text-sm">
        <span className="text-xs font-bold text-primary">询问</span>
        <span className="font-semibold text-foreground">{item.title || "需要你的确认"}</span>
        {!pending ? <span className="ml-auto text-xs text-muted-foreground">{answeredLabel}</span> : null}
      </div>

      {questions.map((q) => (
        <div key={q.id} className="grid gap-1.5 border-t border-white/5 pt-1">
          <div className="text-sm text-foreground">{q.prompt}</div>
          {(q.options || []).length > 0 ? (
            <div className="grid gap-1">
              {q.options!.map((opt) => (
                <label
                  key={opt.id}
                  className="flex cursor-pointer items-start gap-2 text-xs text-muted-foreground"
                >
                  {q.allow_multiple ? (
                    <Checkbox
                      disabled={!pending}
                      checked={(Array.isArray(state[q.id]) ? (state[q.id] as string[]) : []).includes(
                        opt.id,
                      )}
                      onCheckedChange={() => toggleMulti(q.id, opt.id)}
                    />
                  ) : (
                    <input
                      type="radio"
                      disabled={!pending}
                      name={`ask-${item.id || "x"}-${q.id}`}
                      value={opt.id}
                      checked={state[q.id] === opt.id}
                      onChange={() => setState((prev) => ({ ...prev, [q.id]: opt.id }))}
                      className="mt-0.5"
                    />
                  )}
                  <span className="text-foreground">{opt.label}</span>
                </label>
              ))}
            </div>
          ) : null}
          {q.allow_custom !== false ? (
            <Input
              disabled={!pending}
              value={customs[q.id] || ""}
              onChange={(e) => setCustoms((prev) => ({ ...prev, [q.id]: e.target.value }))}
              placeholder="自定义答案（可选）"
              className="h-7 bg-black/30 text-xs"
            />
          ) : null}
        </div>
      ))}

      {pending ? (
        <div className="flex gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 border-primary/55 px-3 text-xs text-primary"
            onClick={handleSubmit}
          >
            提交
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 px-3 text-xs"
            onClick={() => onDismiss?.()}
          >
            跳过
          </Button>
        </div>
      ) : item.answers ? (
        <pre className="m-0 whitespace-pre-wrap font-mono text-xs text-muted-foreground">
          {JSON.stringify(item.answers, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

export default AskUserForm;
