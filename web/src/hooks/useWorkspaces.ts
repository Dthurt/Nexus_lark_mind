import { useCallback, useState } from "react";
import {
  browseSsh,
  browseWorkspace,
  createWorkspace,
  deleteWorkspace,
  importSshHost,
  listHosts,
  listSshConfigHosts,
  listWorkspaces,
  testHost,
  upsertHost,
} from "@/api/endpoints";
import type { BrowseResult, SshConfigHost, SshHost, Workspace } from "@/types/api";

export function useWorkspaces() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [browse, setBrowse] = useState<BrowseResult | null>(null);
  const [sshHosts, setSshHosts] = useState<SshHost[]>([]);
  const [sshConfigHosts, setSshConfigHosts] = useState<SshConfigHost[]>([]);
  const [sshConfigPath, setSshConfigPath] = useState("");
  const [sshBrowse, setSshBrowse] = useState<BrowseResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listWorkspaces();
      setWorkspaces(data?.workspaces || []);
    } catch (err: any) {
      setError(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSshHosts = useCallback(async () => {
    const data = await listHosts();
    const hosts = data?.hosts || [];
    setSshHosts(hosts);
    return hosts;
  }, []);

  const loadSshConfigHosts = useCallback(async () => {
    const data = await listSshConfigHosts();
    const hosts = data?.hosts || [];
    setSshConfigHosts(hosts);
    setSshConfigPath(data?.config_path || "");
    return { hosts, configPath: data?.config_path || "", exists: data?.exists };
  }, []);

  const importSshConfig = useCallback(
    async (alias: string, { label = "", default_path = "~" }: { label?: string; default_path?: string } = {}) => {
      const data = await importSshHost({ alias, label, default_path });
      await loadSshHosts();
      return data;
    },
    [loadSshHosts],
  );

  const create = useCallback(
    async (path: string, title = "") => {
      const data = await createWorkspace({ path, title, kind: "local" });
      await load();
      return data;
    },
    [load],
  );

  const createSsh = useCallback(
    async ({
      ssh_host_id,
      path,
      title = "",
    }: {
      ssh_host_id: string;
      path: string;
      title?: string;
    }) => {
      const data = await createWorkspace({ kind: "ssh", ssh_host_id, path, title });
      await load();
      return data;
    },
    [load],
  );

  const upsertSshHost = useCallback(
    async (form: any) => {
      const data = await upsertHost(form);
      await loadSshHosts();
      return data;
    },
    [loadSshHosts],
  );

  const testSshHost = useCallback(async (hostId: string) => {
    return testHost(hostId);
  }, []);

  const remove = useCallback(
    async (id: string) => {
      await deleteWorkspace(id);
      await load();
    },
    [load],
  );

  const browsePath = useCallback(async (path = "") => {
    const data = await browseWorkspace(path);
    setBrowse(data);
    return data;
  }, []);

  const browseSshPath = useCallback(async (hostId: string, path = "") => {
    const data = await browseSsh(hostId, path);
    setSshBrowse(data);
    return data;
  }, []);

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
    browseSsh: browseSshPath,
  };
}
