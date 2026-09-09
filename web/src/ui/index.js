import NlmButton from "./NlmButton.vue";
import NlmSwitch from "./NlmSwitch.vue";
import NlmSelect from "./NlmSelect.vue";
import NlmTextarea from "./NlmTextarea.vue";
import NlmChip from "./NlmChip.vue";
import NlmTabs from "./NlmTabs.vue";
import MarkdownBody from "./MarkdownBody.vue";
import { SlotNames, createSlotRegistry, uiSlots } from "./slots.js";

const components = {
  NlmButton,
  NlmSwitch,
  NlmSelect,
  NlmTextarea,
  NlmChip,
  NlmTabs,
  MarkdownBody,
};

export {
  NlmButton,
  NlmSwitch,
  NlmSelect,
  NlmTextarea,
  NlmChip,
  NlmTabs,
  MarkdownBody,
  SlotNames,
  createSlotRegistry,
  uiSlots,
};

export default {
  install(app) {
    for (const [name, comp] of Object.entries(components)) {
      app.component(name, comp);
    }
    app.config.globalProperties.$nlmSlots = uiSlots;
    app.provide("nlmSlots", uiSlots);
  },
};
