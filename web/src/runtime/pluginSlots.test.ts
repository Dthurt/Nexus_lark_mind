import { describe, expect, it } from "vitest";

import {
  listAllSlots,
  listSlotKeys,
  registerSlot,
  SlotNames,
  unregisterSlot,
} from "@/runtime/pluginSlots";
import {
  listRegisteredToolViews,
  registerToolView,
  unregisterToolView,
} from "@/components/tools/toolRegistry";

describe("pluginSlots", () => {
  it("registers and lists keyed contributions", () => {
    registerSlot(SlotNames.COMPOSER_ACTION, "test-action", { id: 1 });
    expect(listSlotKeys(SlotNames.COMPOSER_ACTION)).toContain("test-action");
    expect(listAllSlots().some((s) => s.slot === SlotNames.COMPOSER_ACTION)).toBe(true);
    unregisterSlot(SlotNames.COMPOSER_ACTION, "test-action");
    expect(listSlotKeys(SlotNames.COMPOSER_ACTION)).not.toContain("test-action");
  });
});

describe("toolRegistry slots bridge", () => {
  it("exposes registered tool views via listRegisteredToolViews", () => {
    const Fake = () => null;
    registerToolView("__test_view__", Fake as any);
    expect(listRegisteredToolViews()).toContain("__test_view__");
    unregisterToolView("__test_view__");
    expect(listRegisteredToolViews()).not.toContain("__test_view__");
  });
});
