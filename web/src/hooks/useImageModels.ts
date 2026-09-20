import { useCallback, useMemo, useState } from "react";
import { getModelSettings, putPluginConfig, setDefaultProvider } from "@/api/endpoints";
import type { ProviderEntry } from "@/types/api";

const IMAGE_PROVIDER_KEY = "nlm_image_provider";
const IMAGE_MODEL_KEY = "nlm_image_model";

export function useImageModels() {
  const [providers, setProviders] = useState<ProviderEntry[]>([]);
  const [providerId, setProviderId] = useState(() => localStorage.getItem(IMAGE_PROVIDER_KEY) || "");
  const [modelName, setModelName] = useState(() => localStorage.getItem(IMAGE_MODEL_KEY) || "");

  const load = useCallback(async () => {
    try {
      const doc = await getModelSettings();
      const list = (doc.images || doc.customs || []).filter(
        (p) => (p.kind || "chat") === "image" && p.enabled !== false,
      );
      setProviders(list);
      const storedProvider = localStorage.getItem(IMAGE_PROVIDER_KEY) || "";
      const preferred =
        storedProvider || doc.default_image_provider || list[0]?.id || "";
      if (preferred && list.some((p) => p.id === preferred)) {
        setProviderId(preferred);
        localStorage.setItem(IMAGE_PROVIDER_KEY, preferred);
        const entry = list.find((p) => p.id === preferred);
        const models = entry?.models || [];
        const storedModel = localStorage.getItem(IMAGE_MODEL_KEY) || "";
        const want = storedModel || entry?.default_model || models[0] || "";
        if (want) {
          setModelName(want);
          localStorage.setItem(IMAGE_MODEL_KEY, want);
        }
      }
    } catch {
      /* keep empty */
    }
  }, []);

  const providerOptions = useMemo(
    () => providers.map((p) => ({ value: p.id, label: p.label || p.id })),
    [providers],
  );

  const modelOptions = useMemo(() => {
    const entry = providers.find((p) => p.id === providerId);
    const models = entry?.models || [];
    if (!models.length) {
      return modelName ? [{ value: modelName, label: modelName }] : [];
    }
    return models.map((name) => ({ value: name, label: name }));
  }, [modelName, providerId, providers]);

  const onProviderChange = useCallback(
    async (id: string) => {
      setProviderId(id);
      try {
        localStorage.setItem(IMAGE_PROVIDER_KEY, id);
      } catch {
        /* ignore */
      }
      const entry = providers.find((p) => p.id === id);
      const next = entry?.default_model || entry?.models?.[0] || "";
      if (next) {
        setModelName(next);
        try {
          localStorage.setItem(IMAGE_MODEL_KEY, next);
        } catch {
          /* ignore */
        }
      }
      try {
        await setDefaultProvider(id, "image");
      } catch {
        /* settings save is best-effort */
      }
      try {
        await putPluginConfig("builtin.image_gen", {
          IMAGE_PROVIDER: id,
          IMAGE_MODEL: next || modelName,
        });
      } catch {
        /* plugin may be disabled */
      }
    },
    [modelName, providers],
  );

  const onModelChange = useCallback(
    async (name: string) => {
      setModelName(name);
      try {
        localStorage.setItem(IMAGE_MODEL_KEY, name);
      } catch {
        /* ignore */
      }
      try {
        await putPluginConfig("builtin.image_gen", {
          IMAGE_PROVIDER: providerId,
          IMAGE_MODEL: name,
        });
      } catch {
        /* plugin may be disabled */
      }
    },
    [providerId],
  );

  return {
    imageProviderId: providerId,
    imageModelName: modelName,
    imageProviderOptions: providerOptions,
    imageModelOptions: modelOptions,
    imageConfigured: providers.length > 0,
    loadImageModels: load,
    onImageProviderChange: onProviderChange,
    onImageModelChange: onModelChange,
  };
}
