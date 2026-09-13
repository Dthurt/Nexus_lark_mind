import { useCallback, useState } from "react";
import {
  disablePlugin,
  enablePlugin,
  getPluginConfig,
  getPluginMarketplace,
  installPluginPackage,
  installPluginZip,
  listPlugins,
  listTools,
  putPluginConfig,
  reloadPlugin,
  reloadPlugins,
  type MarketplaceCatalog,
} from "@/api/endpoints";
import type { Plugin, PluginConfigSchema, Tool } from "@/types/api";

export function usePlugins() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [marketplace, setMarketplace] = useState<MarketplaceCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [pData, tData] = await Promise.all([listPlugins(), listTools()]);
      setPlugins(pData || []);
      setTools(tData || []);
    } catch {
      setError("无法加载插件列表");
      setPlugins([]);
      setTools([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMarketplace = useCallback(async () => {
    try {
      const data = await getPluginMarketplace();
      setMarketplace(data || { items: [] });
      return data;
    } catch (err: any) {
      setMarketplace({ items: [], hints: [String(err?.message || err)] });
      throw err;
    }
  }, []);

  const toggle = useCallback(
    async (pluginId: string, enabled: boolean) => {
      if (enabled) await enablePlugin(pluginId);
      else await disablePlugin(pluginId);
      await load();
    },
    [load],
  );

  const reload = useCallback(
    async (pluginId: string | null = null) => {
      setReloading(true);
      try {
        const data = pluginId ? await reloadPlugin(pluginId) : await reloadPlugins();
        if (Array.isArray(data)) {
          setPlugins(data);
          await load();
        } else {
          await load();
        }
        await loadMarketplace().catch(() => undefined);
      } finally {
        setReloading(false);
      }
    },
    [load, loadMarketplace],
  );

  const installFromPath = useCallback(
    async (path: string) => {
      const data = await installPluginPackage({ path });
      await load();
      await loadMarketplace().catch(() => undefined);
      return data;
    },
    [load, loadMarketplace],
  );

  const installFromZip = useCallback(
    async (file: File) => {
      const data = await installPluginZip(file);
      await load();
      await loadMarketplace().catch(() => undefined);
      return data;
    },
    [load, loadMarketplace],
  );

  const getConfig = useCallback(async (pluginId: string): Promise<PluginConfigSchema> => {
    return getPluginConfig(pluginId);
  }, []);

  const saveConfig = useCallback(
    async (pluginId: string, values: Record<string, unknown>) => {
      const data = await putPluginConfig(pluginId, values);
      await load();
      return data;
    },
    [load],
  );

  return {
    plugins,
    tools,
    marketplace,
    loading,
    reloading,
    error,
    load,
    loadMarketplace,
    toggle,
    reload,
    installFromPath,
    installFromZip,
    getConfig,
    saveConfig,
  };
}
