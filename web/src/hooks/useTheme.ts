import { useCallback, useState } from "react";

const STORAGE_KEY = "nlm-theme";

export const THEME_ORDER = ["day", "gray", "night", "ocean", "rose"] as const;

export type Theme = (typeof THEME_ORDER)[number];

const LABELS: Record<Theme, string> = {
  day: "白天",
  gray: "灰阶",
  night: "夜晚",
  ocean: "海洋",
  rose: "玫瑰",
};

export function normalizeTheme(value: string | null | undefined): Theme {
  const v = String(value || "").toLowerCase();
  if (v === "light" || v === "day") return "day";
  if (v === "gray" || v === "grey" || v === "mid") return "gray";
  if (v === "dark" || v === "night") return "night";
  if (v === "ocean") return "ocean";
  if (v === "rose") return "rose";
  return "night";
}

export function themeLabel(theme: string | null | undefined): string {
  return LABELS[normalizeTheme(theme)] || LABELS.night;
}

export function applyTheme(theme: string | null | undefined): Theme {
  const next = normalizeTheme(theme);
  const root = document.documentElement;
  root.setAttribute("data-theme", next);
  root.style.colorScheme = next === "day" ? "light" : "dark";
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore */
  }
  try {
    window.dispatchEvent(new CustomEvent("nlm-theme-change", { detail: next }));
  } catch {
    /* ignore */
  }
  return next;
}

export function loadStoredTheme(): Theme {
  try {
    return normalizeTheme(localStorage.getItem(STORAGE_KEY) || "night");
  } catch {
    return "night";
  }
}

export function cycleTheme(current?: string | null): Theme {
  const cur = normalizeTheme(current ?? loadStoredTheme());
  const idx = THEME_ORDER.indexOf(cur);
  const next = THEME_ORDER[(idx + 1) % THEME_ORDER.length];
  return applyTheme(next);
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => loadStoredTheme());

  const setTheme = useCallback((next: string) => {
    setThemeState(applyTheme(next));
  }, []);

  const cycle = useCallback(() => {
    setThemeState((prev) => cycleTheme(prev));
  }, []);

  return {
    theme,
    setTheme,
    cycle,
    label: themeLabel(theme),
  };
}
