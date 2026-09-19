import { motion } from "motion/react";
import type { LucideIcon } from "lucide-react";

import { usePrefersReducedMotion } from "@/lib/motion";
import type { KnowledgeSection } from "@/lib/knowledgeScope";
import { cn } from "@/lib/utils";

export type KnowledgeSegmentItem = {
  id: KnowledgeSection;
  label: string;
  testId: string;
  Icon: LucideIcon;
};

export function KnowledgeSegment({
  value,
  items,
  onChange,
}: {
  value: KnowledgeSection;
  items: readonly KnowledgeSegmentItem[];
  onChange?: (id: KnowledgeSection) => void;
}) {
  const reduced = usePrefersReducedMotion();
  return (
    <div className="nlm-kb-seg" role="tablist" aria-label="知识库视图" data-testid="knowledge-sections">
      {items.map((item) => {
        const active = value === item.id;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={cn("nlm-kb-seg-item", active && "is-active")}
            data-testid={item.testId}
            data-key={item.id === "docs" ? "1" : item.id === "wiki" ? "2" : "3"}
            title={`${item.label} · ${item.id === "docs" ? "1" : item.id === "wiki" ? "2" : "3"}`}
            onClick={() => onChange?.(item.id)}
          >
            {active && !reduced ? (
              <motion.span
                layoutId="nlm-kb-seg-pill"
                className="nlm-kb-seg-pill"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            ) : active ? (
              <span className="nlm-kb-seg-pill" />
            ) : null}
            <item.Icon className="relative size-3.5" />
            <span className="relative">{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}
