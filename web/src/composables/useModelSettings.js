import { ref } from "vue";

export function useModelSettings() {
  const doc = ref({ default_provider: "", builtins: [], customs: [] });
  const loading = ref(false);
  const saving = ref(false);
  const error = ref("");

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const resp = await fetch("/api/settings/models");
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "load failed");
      doc.value = json.data || { default_provider: "", builtins: [], customs: [] };
    } catch (err) {
      error.value = String(err);
    } finally {
      loading.value = false;
    }
  }

  async function saveProvider(form) {
    saving.value = true;
    error.value = "";
    try {
      const resp = await fetch("/api/settings/models/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "save failed");
      await load();
      return json.data;
    } catch (err) {
      error.value = String(err);
      throw err;
    } finally {
      saving.value = false;
    }
  }

  async function removeProvider(id) {
    saving.value = true;
    error.value = "";
    try {
      const resp = await fetch(`/api/settings/models/providers/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "delete failed");
      await load();
    } catch (err) {
      error.value = String(err);
      throw err;
    } finally {
      saving.value = false;
    }
  }

  async function setDefault(providerId) {
    saving.value = true;
    try {
      const resp = await fetch("/api/settings/models/default", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider_id: providerId }),
      });
      const json = await resp.json();
      if (!json.ok) throw new Error(json.error?.message || "set default failed");
      doc.value.default_provider = providerId;
    } catch (err) {
      error.value = String(err);
      throw err;
    } finally {
      saving.value = false;
    }
  }

  async function discoverModels({ base_url, api_key, provider_id }) {
    const resp = await fetch("/api/settings/models/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_url, api_key, provider_id }),
    });
    const json = await resp.json();
    if (!json.ok) throw new Error(json.error?.message || "discover failed");
    return json.data;
  }

  async function testConnectivity({ base_url, api_key, model, provider_id }) {
    const resp = await fetch("/api/settings/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_url, api_key, model, provider_id }),
    });
    const json = await resp.json();
    if (!json.ok) throw new Error(json.error?.message || "test failed");
    return json.data;
  }

  return {
    doc,
    loading,
    saving,
    error,
    load,
    saveProvider,
    removeProvider,
    setDefault,
    discoverModels,
    testConnectivity,
  };
}
