import { ref } from "vue";

export function usePlugins() {
  const plugins = ref([]);
  const tools = ref([]);
  const loading = ref(false);
  const reloading = ref(false);
  const error = ref("");

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const [pResp, tResp] = await Promise.all([fetch("/api/plugins"), fetch("/api/tools")]);
      const pJson = await pResp.json();
      const tJson = await tResp.json();
      if (pJson.ok) plugins.value = pJson.data || [];
      if (tJson.ok) tools.value = tJson.data || [];
    } catch {
      error.value = "无法加载插件列表";
      plugins.value = [];
      tools.value = [];
    } finally {
      loading.value = false;
    }
  }

  async function toggle(pluginId, enabled) {
    const path = enabled ? "enable" : "disable";
    const resp = await fetch(`/api/plugins/${encodeURIComponent(pluginId)}/${path}`, {
      method: "POST",
    });
    const json = await resp.json();
    if (!json.ok) throw new Error(json.error?.message || "toggle failed");
    await load();
  }

  async function reload(pluginId = null) {
    reloading.value = true;
    try {
      const url = pluginId
        ? `/api/plugins/${encodeURIComponent(pluginId)}/reload`
        : "/api/plugins/reload";
      const resp = await fetch(url, { method: "POST" });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "reload failed");
      if (Array.isArray(json.data)) {
        plugins.value = json.data;
        await load();
      } else {
        await load();
      }
    } finally {
      reloading.value = false;
    }
  }

  return { plugins, tools, loading, reloading, error, load, toggle, reload };
}
