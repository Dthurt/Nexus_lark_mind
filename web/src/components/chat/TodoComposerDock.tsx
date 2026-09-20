import { ChevronDown, ListTodo } from "lucide-react";
import { useMemo, useState } from "react";

import { TodoListCard, type TodoRow } from "@/components/chat/TodoListCard";
import { latestTodoRows, todoProgress, todosAllSettled } from "@/lib/todos";
import { cn } from "@/lib/utils";

export type TodoComposerDockProps = {
  items?: Array<{ kind?: string; items?: TodoRow[] }>;
  className?: string;
};

export function TodoComposerDock({ items = [], className }: TodoComposerDockProps) {
  const rows = useMemo(() => latestTodoRows(items), [items]);
  const [collapsed, setCollapsed] = useState(false);
  const progress = todoProgress(rows);
  if (!rows.length || todosAllSettled(rows)) return null;

  return (
    <div
      className={cn("nlm-todo-dock", className)}
      data-testid="todo-composer-dock"
      aria-label="进行中的 Todos"
    >
      <button
        type="button"
        className="nlm-todo-dock-head"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((v) => !v)}
      >
        <ListTodo className="size-3.5 shrink-0 text-teal" aria-hidden />
        <span className="min-w-0 truncate font-medium">Todos</span>
        <span className="shrink-0 text-[10px] text-muted-foreground">
          {progress.done}/{progress.total}
          {progress.current?.content ? ` · ${progress.current.content}` : ""}
        </span>
        <ChevronDown
          className={cn("ml-auto size-3.5 text-muted-foreground transition-transform", collapsed && "-rotate-90")}
          aria-hidden
        />
      </button>
      {collapsed ? null : (
        <TodoListCard item={{ items: rows }} variant="compact" className="nlm-todo-dock-body" />
      )}
    </div>
  );
}

export default TodoComposerDock;
