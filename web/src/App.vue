<script setup>
import { ref } from "vue";
import WorkbenchView from "@/views/WorkbenchView.vue";
import SettingsView from "@/views/SettingsView.vue";

const page = ref("workbench"); // workbench | settings
const catalogTick = ref(0);

function openSettings() {
  page.value = "settings";
}
function backWorkbench() {
  page.value = "workbench";
}
function onSettingsChanged() {
  catalogTick.value += 1;
}
</script>

<template>
  <SettingsView
    v-if="page === 'settings'"
    @back="backWorkbench"
    @changed="onSettingsChanged"
  />
  <WorkbenchView
    v-else
    :catalog-tick="catalogTick"
    @open-settings="openSettings"
  />
</template>
