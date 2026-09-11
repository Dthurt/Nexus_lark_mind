import { cn } from "@/lib/utils";

const STATUS_GLYPH: Record<string, string> = {
  pending: "○",
  in_progress: "◉",
  completed: "✓",
  cancelled: "–",
};

export type TodoRow = {
  id?: string;
  content?: string;
  status?: string;
};

export type TodoListItem = {
  items?: TodoRow[];
};

export type TodoListCardProps = {
  item: TodoListItem;
  className?: string;
};

export function TodoListCard({ item, className }: TodoListCardProps) {
  const rows = item.items || [];

  return (
    <div
      className={cn(
        "my-2 rounded-[10px] border border-border bg-card/50 px-3 py-2.5",
        className,
      )}
      role="status"
      aria-label="Agent todos"
    >
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Todos
        </span>
        <span className="text-[11px] text-muted-foreground">{rows.length}</span>
      </div>
      <ul className="m-0 grid list-none gap-1 p-0">
        {rows.map((row) => (
          <li
            key={row.id || row.content}
            className="grid grid-cols-[1.1rem_1fr] items-start gap-2 text-[13px]"
            data-status={row.status}
          >
            <span
              className={cn(
                "text-xs leading-snug text-muted-foreground",
                row.status === "in_progress" && "text-teal",
              )}
              aria-hidden
            >
              {STATUS_GLYPH[row.status || ""] || "○"}
            </span>
            <span
              className={cn(
                "todo-text",
                row.status === "completed" && "text-muted-foreground line-through decoration-1",
                row.status === "cancelled" && "text-muted-foreground opacity-70",
              )}
            >
              {row.content}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default TodoListCard;
