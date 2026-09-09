import { computed, ref } from "vue";

const PROVIDER_KEY = "nlm_provider";
const MODEL_KEY = "nlm_model";

export function useProviders() {
  const catalog = ref({ default_provider: "glm", default_model: "", providers: [] });
  const providerId = ref(localStorage.getItem(PROVIDER_KEY) || "");
  const modelName = ref(localStorage.getItem(MODEL_KEY) || "");

  const providerOptions = computed(() => {
    const list = catalog.value.providers || [];
    if (!list.length) {
      return [{ value: "", label: "未配置 Provider（请检查 .env API Key）" }];
    }
    return list.map((p) => ({ value: p.id, label: p.label || p.id }));
  });

  const modelOptions = computed(() => {
    const provider = (catalog.value.providers || []).find((x) => x.id === providerId.value);
    const models = (provider && provider.models) || [];
    if (!models.length) {
      const fallback = modelName.value || catalog.value.default_model || "";
      return [{ value: fallback, label: fallback || "(无可用模型)" }];
    }
    return models.map((name) => ({ value: name, label: name }));
  });

  const providersDisabled = computed(() => !(catalog.value.providers || []).length);
  const modelsDisabled = computed(() => {
    if (providersDisabled.value) return true;
    const provider = (catalog.value.providers || []).find((x) => x.id === providerId.value);
    return !((provider && provider.models) || []).length && !modelName.value;
  });

  function applyDefaults(preferredProvider, preferredModel) {
    const providers = catalog.value.providers || [];
    if (!providers.length) {
      providerId.value = "";
      modelName.value = "";
      return;
    }
    const want =
      preferredProvider ||
      localStorage.getItem(PROVIDER_KEY) ||
      catalog.value.default_provider ||
      providers[0].id;
    providerId.value = providers.some((p) => p.id === want) ? want : providers[0].id;
    localStorage.setItem(PROVIDER_KEY, providerId.value);

    const provider = providers.find((x) => x.id === providerId.value);
    const models = (provider && provider.models) || [];
    if (!models.length) {
      modelName.value = preferredModel || catalog.value.default_model || "";
      return;
    }
    const wantModel =
      preferredModel ||
      localStorage.getItem(MODEL_KEY) ||
      (provider && provider.default_model) ||
      models[0];
    modelName.value = models.includes(wantModel) ? wantModel : models[0];
    localStorage.setItem(MODEL_KEY, modelName.value);
  }

  async function load() {
    try {
      const resp = await fetch("/api/providers?configured_only=true");
      const json = await resp.json();
      if (json.ok && json.data) catalog.value = json.data;
    } catch {
      /* keep defaults */
    }
    applyDefaults(localStorage.getItem(PROVIDER_KEY), localStorage.getItem(MODEL_KEY));
  }

  function onProviderChange(id) {
    providerId.value = id;
    localStorage.setItem(PROVIDER_KEY, id);
    const provider = (catalog.value.providers || []).find((x) => x.id === id);
    applyDefaults(id, provider && provider.default_model);
  }

  function onModelChange(name) {
    modelName.value = name;
    localStorage.setItem(MODEL_KEY, name);
  }

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
