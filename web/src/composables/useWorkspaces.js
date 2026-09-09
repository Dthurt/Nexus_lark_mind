import { ref } from "vue";

async function readJson(resp) {
  const text = await resp.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(
      resp.status === 404
        ? "接口不存在（404）。请重启本地服务：scripts\\start_local.bat"
        : `响应不是 JSON（HTTP ${resp.status}）`
    );
  }
  if (!resp.ok || !json?.ok) {
    const msg = json?.error?.message || json?.detail || `HTTP ${resp.status}`;
    throw new Error(String(msg));
  }
  return json;
}

export function useWorkspaces() {
  const workspaces = ref([]);
  const loading = ref(false);
  const error = ref("");
  const browse = ref(null);
  const sshHosts = ref([]);
  const sshConfigHosts = ref([]);
  const sshConfigPath = ref("");
  const sshBrowse = ref(null);

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const resp = await fetch("/api/workspaces");
      const json = await readJson(resp);
      workspaces.value = json.data?.workspaces || [];
    } catch (err) {
      error.value = String(err.message || err);
    } finally {
      loading.value = false;
    }
  }

  async function loadSshHosts() {
    const resp = await fetch("/api/ssh/hosts");
    const json = await readJson(resp);
    sshHosts.value = json.data?.hosts || [];
    return sshHosts.value;
  }

  async function loadSshConfigHosts() {
    const resp = await fetch("/api/ssh/config/hosts");
    const json = await readJson(resp);
    sshConfigHosts.value = json.data?.hosts || [];
    sshConfigPath.value = json.data?.config_path || "";
    return { hosts: sshConfigHosts.value, configPath: sshConfigPath.value, exists: json.data?.exists };
  }

  async function importSshConfig(alias, { label = "", default_path = "~" } = {}) {
    const resp = await fetch("/api/ssh/hosts/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alias, label, default_path }),
    });
    const json = await readJson(resp);
    await loadSshHosts();
    return json.data;
  }

  async function create(path, title = "") {
    const resp = await fetch("/api/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, title, kind: "local" }),
    });
    const json = await readJson(resp);
    await load();
    return json.data;
  }

  async function createSsh({ ssh_host_id, path, title = "" }) {
    const resp = await fetch("/api/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "ssh", ssh_host_id, path, title }),
    });
    const json = await readJson(resp);
    await load();
    return json.data;
  }

  async function upsertSshHost(form) {
    const resp = await fetch("/api/ssh/hosts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const json = await readJson(resp);
    await loadSshHosts();
    return json.data;
  }

  async function testSshHost(hostId) {
    const resp = await fetch(`/api/ssh/hosts/${encodeURIComponent(hostId)}/test`, {
      method: "POST",
    });
    return (await readJson(resp)).data;
  }

  async function remove(id) {
    const resp = await fetch(`/api/workspaces/${encodeURIComponent(id)}`, { method: "DELETE" });
    await readJson(resp);
    await load();
  }

  async function browsePath(path = "") {
    const q = path ? `?path=${encodeURIComponent(path)}` : "";
    const resp = await fetch(`/api/workspaces/browse${q}`);
    const json = await readJson(resp);
    browse.value = json.data;
    return json.data;
  }

  async function browseSsh(hostId, path = "") {
    const q = path ? `?path=${encodeURIComponent(path)}` : "";
    const resp = await fetch(`/api/ssh/hosts/${encodeURIComponent(hostId)}/browse${q}`);
    const json = await readJson(resp);
    sshBrowse.value = json.data;
    return json.data;
  }

  return {
    workspaces,
    loading,
    error,
    browse,
    sshHosts,
    sshConfigHosts,
    sshConfigPath,
    sshBrowse,
    load,
    loadSshHosts,
    loadSshConfigHosts,
    importSshConfig,
    create,
    createSsh,
    upsertSshHost,
    testSshHost,
    remove,
    browsePath,
    browseSsh,
  };
}
