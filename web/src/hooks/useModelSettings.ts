import { useCallback, useState } from "react";
import {
  discoverModels,
  getModelSettings,
  removeProvider,
  saveProvider,
  setDefaultProvider,
  testModel,
} from "@/api/endpoints";
import type { ProviderDoc, ProviderEntry } from "@/types/api";

export function useModelSettings() {
  const [doc, setDoc] = useState<ProviderDoc>({
    default_provider: "",
    builtins: [],
    customs: [],
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getModelSettings();
      setDoc(data || { default_provider: "", builtins: [], customs: [] });
    } catch (err: any) {
      setError(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  }, []);

  const saveProviderForm = useCallback(
    async (form: Partial<ProviderEntry> & { id: string }) => {
      setSaving(true);
      setError("");
      try {
        const data = await saveProvider(form);
        await load();
        return data;
      } catch (err: any) {
        setError(String(err?.message || err));
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [load],
  );

  const removeProviderById = useCallback(
    async (id: string) => {
      setSaving(true);
      setError("");
      try {
        await removeProvider(id);
        await load();
      } catch (err: any) {
        setError(String(err?.message || err));
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [load],
  );

  const setDefault = useCallback(async (providerId: string) => {
    setSaving(true);
    try {
      await setDefaultProvider(providerId);
      setDoc((prev) => ({ ...prev, default_provider: providerId }));
    } catch (err: any) {
      setError(String(err?.message || err));
      throw err;
    } finally {
      setSaving(false);
    }
  }, []);

  const discover = useCallback(
    async ({
      base_url,
      api_key,
      provider_id,
    }: {
      base_url?: string;
      api_key?: string;
      provider_id?: string;
    }) => {
      return discoverModels({ base_url, api_key, provider_id });
    },
    [],
  );

  const testConnectivity = useCallback(
    async ({
      base_url,
      api_key,
      model,
      provider_id,
    }: {
      base_url?: string;
      api_key?: string;
      model?: string;
      provider_id?: string;
    }) => {
      return testModel({ base_url, api_key, model, provider_id });
    },
    [],
  );

  return {
    doc,
    loading,
    saving,
    error,
    load,
    saveProvider: saveProviderForm,
    removeProvider: removeProviderById,
    setDefault,
    discoverModels: discover,
    testConnectivity,
  };
}
