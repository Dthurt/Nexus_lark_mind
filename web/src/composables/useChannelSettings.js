import { ref } from "vue";

export function useChannelSettings() {
  const doc = ref({ product: "Nexus Lark Mind", channels: [] });
  const loading = ref(false);
  const saving = ref(false);
  const testing = ref(false);
  const error = ref("");
  const testHint = ref("");

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const resp = await fetch("/api/settings/channels");
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "load failed");
      doc.value = json.data || { product: "Nexus Lark Mind", channels: [] };
    } catch (err) {
      error.value = String(err);
    } finally {
      loading.value = false;
    }
  }

  async function saveFeishu(form) {
    saving.value = true;
    error.value = "";
    try {
      const resp = await fetch("/api/settings/channels/feishu", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "save failed");
      doc.value = json.data;
      return json.data;
    } catch (err) {
      error.value = String(err);
      throw err;
    } finally {
      saving.value = false;
    }
  }

  async function testFeishu({ app_id, app_secret } = {}) {
    testing.value = true;
    testHint.value = "正在请求飞书 tenant_access_token…";
    error.value = "";
    try {
      const resp = await fetch("/api/settings/channels/feishu/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ app_id, app_secret }),
      });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "test failed");
      testHint.value = json.data?.message || "连通成功";
      return json.data;
    } catch (err) {
      testHint.value = String(err.message || err);
      error.value = String(err);
      throw err;
    } finally {
      testing.value = false;
    }
  }

  async function reloadFeishu() {
    saving.value = true;
    try {
      const resp = await fetch("/api/settings/channels/feishu/reload", { method: "POST" });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "reload failed");
      doc.value = json.data;
      return json.data;
    } catch (err) {
      error.value = String(err);
      throw err;
    } finally {
      saving.value = false;
    }
  }

  function feishuChannel() {
    return (doc.value.channels || []).find((c) => c.id === "feishu") || null;
  }

  return {
    doc,
    loading,
    saving,
    testing,
    error,
    testHint,
    load,
    saveFeishu,
    testFeishu,
    reloadFeishu,
    feishuChannel,
  };
}
