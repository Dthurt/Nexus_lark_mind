import { createApp } from "vue";
import App from "./App.vue";
import "./styles/workbench.css";
import NlmUi, { SlotNames, uiSlots } from "@nlm/ui";
import WebSearchToolCard from "@/components/WebSearchToolCard.vue";
import WorkspaceToolCard from "@/components/WorkspaceToolCard.vue";
import { createContext } from "@/runtime/createContext";
import { applyBuiltinModules } from "@/runtime/modules";

const app = createApp(App);
app.use(NlmUi);

// Cordis-lite composition root
const nlmCtx = createContext({ slots: uiSlots });
applyBuiltinModules(nlmCtx);
app.provide("nlmCtx", nlmCtx);

// Keyed tool views
uiSlots.register(SlotNames.TOOL_CALL_VIEW, "keyed", {
  id: "web_search",
  key: "web_search",
  component: WebSearchToolCard,
});
uiSlots.register(SlotNames.TOOL_CALL_VIEW, "keyed", {
  id: "cli_web_search_web_search",
  key: "cli_web_search_web_search",
  component: WebSearchToolCard,
});

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
  uiSlots.register(SlotNames.TOOL_CALL_VIEW, "keyed", {
    id: `ws_${key}`,
    key,
    component: WorkspaceToolCard,
  });
}

app.mount("#app");

if (import.meta.hot) {
  import.meta.hot.dispose(() => nlmCtx.dispose());
}
