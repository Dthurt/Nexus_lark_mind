/** Theme: day | gray | night (persisted). */

const STORAGE_KEY = "nlm-theme";
export const THEME_ORDER = ["day", "gray", "night"];

const LABELS = {
  day: "白天",
  gray: "灰阶",
  night: "夜晚",
};

export function normalizeTheme(value) {
  const v = String(value || "").toLowerCase();
  if (v === "light" || v === "day") return "day";
  if (v === "gray" || v === "grey" || v === "mid") return "gray";
  if (v === "dark" || v === "night") return "night";
  return "night";
}

export function themeLabel(theme) {
  return LABELS[normalizeTheme(theme)] || LABELS.night;
}

export function applyTheme(theme) {
  const next = normalizeTheme(theme);
  const root = document.documentElement;
  root.setAttribute("data-theme", next);
  root.style.colorScheme = next === "day" ? "light" : "dark";
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore */
  }
  return next;
}

export function loadStoredTheme() {
  try {
    return normalizeTheme(localStorage.getItem(STORAGE_KEY) || "night");
  } catch {
    return "night";
  }
}

export function cycleTheme(current) {
  const cur = normalizeTheme(current);
  const idx = THEME_ORDER.indexOf(cur);
  const next = THEME_ORDER[(idx + 1) % THEME_ORDER.length];
  return applyTheme(next);
}
