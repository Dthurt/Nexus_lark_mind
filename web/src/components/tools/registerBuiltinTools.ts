/**
 * Register builtin tool call views on module load.
 * Import from main.tsx or ChatMessages so registrations happen before first render.
 */
import { registerToolView } from "@/components/tools/toolRegistry";
import { WebSearchToolCard } from "@/components/tools/WebSearchToolCard";
import { WorkspaceToolCard } from "@/components/tools/WorkspaceToolCard";

registerToolView("web_search", WebSearchToolCard);
registerToolView("cli_web_search_web_search", WebSearchToolCard);

const workspaceToolKeys = [
  "glob",
  "grep",
  "list_dir",
  "read_file",
  "write_file",
  "edit_file",
  "run_shell",
];

for (const key of workspaceToolKeys) {
  registerToolView(key, WorkspaceToolCard);
  registerToolView(`builtin_workspace_${key}`, WorkspaceToolCard);
}

registerToolView("open_canvas", WorkspaceToolCard);
registerToolView("builtin_workspace_open_canvas", WorkspaceToolCard);

export {};
