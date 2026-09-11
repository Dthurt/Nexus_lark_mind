import { useCallback, useState } from "react";
import {
  disablePlugin,
  enablePlugin,
  getPluginConfig,
  listPlugins,
  listTools,
  putPluginConfig,
  reloadPlugin,
  reloadPlugins,
} from "@/api/endpoints";
import type { Plugin, PluginConfigSchema, Tool } from "@/types/api";

export function usePlugins() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
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
      } finally {
        setReloading(false);
      }
    },
    [load],
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
    loading,
    reloading,
    error,
    load,
    toggle,
    reload,
    getConfig,
    saveConfig,
  };
}
