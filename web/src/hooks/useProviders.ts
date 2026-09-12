import { useCallback, useMemo, useState } from "react";
import { listProviders } from "@/api/endpoints";
import type { ProviderCatalog } from "@/types/api";

const PROVIDER_KEY = "nlm_provider";
const MODEL_KEY = "nlm_model";

export function useProviders() {
  const [catalog, setCatalog] = useState<ProviderCatalog>({
    default_provider: "glm",
    default_model: "",
    providers: [],
  });
  const [providerId, setProviderId] = useState(() => localStorage.getItem(PROVIDER_KEY) || "");
  const [modelName, setModelName] = useState(() => localStorage.getItem(MODEL_KEY) || "");

  const providerOptions = useMemo(() => {
    const list = catalog.providers || [];
    if (!list.length) {
      return [{ value: "", label: "未配置 Provider（请检查 .env API Key）" }];
    }
    return list.map((p) => {
      const base = p.label || p.id;
      const isCustom = p.source === "custom" || p.builtin === false;
      return { value: p.id, label: isCustom ? `${base}（自定义）` : base };
    });
  }, [catalog.providers]);

  const modelOptions = useMemo(() => {
    const provider = (catalog.providers || []).find((x) => x.id === providerId);
    const models = (provider && provider.models) || [];
    if (!models.length) {
      const fallback = modelName || catalog.default_model || "";
      return [{ value: fallback, label: fallback || "(无可用模型)" }];
    }
    return models.map((name) => ({ value: name, label: name }));
  }, [catalog.default_model, catalog.providers, modelName, providerId]);

  const providersDisabled = useMemo(
    () => !(catalog.providers || []).length,
    [catalog.providers],
  );

  const modelsDisabled = useMemo(() => {
    if (providersDisabled) return true;
    const provider = (catalog.providers || []).find((x) => x.id === providerId);
    return !((provider && provider.models) || []).length && !modelName;
  }, [catalog.providers, modelName, providerId, providersDisabled]);

  const applyDefaults = useCallback(
    (
      preferredProvider?: string | null,
      preferredModel?: string | null,
      catOverride?: ProviderCatalog,
    ) => {
      const cat = catOverride;
      setCatalog((prev) => {
        const source = cat || prev;
        const providers = source.providers || [];
        if (!providers.length) {
          setProviderId("");
          setModelName("");
          return cat || prev;
        }
        // Settings「设为默认」优先于浏览器里残留的旧选择（常见是预制 glm）。
        const want =
          preferredProvider ||
          source.default_provider ||
          localStorage.getItem(PROVIDER_KEY) ||
          providers[0].id;
        const nextProvider = providers.some((p) => p.id === want)
          ? (want as string)
          : providers[0].id;
        setProviderId(nextProvider);
        localStorage.setItem(PROVIDER_KEY, nextProvider);

        const provider = providers.find((x) => x.id === nextProvider);
        const models = (provider && provider.models) || [];
        if (!models.length) {
          const emptyModel =
            preferredModel ||
            (nextProvider === source.default_provider ? source.default_model : "") ||
            "";
          setModelName(emptyModel);
          if (emptyModel) localStorage.setItem(MODEL_KEY, emptyModel);
          return cat || prev;
        }
        const wantModel =
          preferredModel ||
          (nextProvider === source.default_provider ? source.default_model : "") ||
          localStorage.getItem(MODEL_KEY) ||
          (provider && provider.default_model) ||
          models[0];
        const nextModel = models.includes(wantModel as string)
          ? (wantModel as string)
          : models[0];
        setModelName(nextModel);
        localStorage.setItem(MODEL_KEY, nextModel);
        return cat || prev;
      });
    },
    [],
  );

  const load = useCallback(async () => {
    let data: ProviderCatalog | undefined;
    try {
      data = await listProviders(true);
      if (data) setCatalog(data);
    } catch {
      /* keep defaults */
    }
    // Do not force stale localStorage over server default_provider.
    applyDefaults(undefined, undefined, data);
  }, [applyDefaults]);

  const onProviderChange = useCallback(
    (id: string) => {
      setProviderId(id);
      localStorage.setItem(PROVIDER_KEY, id);
      const provider = (catalog.providers || []).find((x) => x.id === id);
      applyDefaults(id, provider && provider.default_model);
    },
    [applyDefaults, catalog.providers],
  );

  const onModelChange = useCallback((name: string) => {
    setModelName(name);
    localStorage.setItem(MODEL_KEY, name);
  }, []);

  return {
    catalog,
    providerId,
    modelName,
    providerOptions,
    modelOptions,
    providersDisabled,
    modelsDisabled,
    load,
    onProviderChange,
    onModelChange,
  };
}
