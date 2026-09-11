/** Theme helpers for Mermaid / ECharts / Draw.io surfaces & exports. */

export type DiagramThemeMode = "light" | "dark";

export function diagramThemeMode(): DiagramThemeMode {
  return document.documentElement.getAttribute("data-theme") === "day" ? "light" : "dark";
}

export function isLightDiagramTheme() {
  return diagramThemeMode() === "light";
}

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Solid panel fill (fullscreen chrome, PNG backdrop). */
export function diagramPanelBg() {
  const solid = cssVar("--panel-solid");
  if (solid) return solid;
  return isLightDiagramTheme() ? "#f8fafc" : "#0d1520";
}

/** Canvas / viewport fill behind diagrams. */
export function diagramCanvasBg() {
  const bg = cssVar("--background");
  if (bg) return `hsl(${bg})`;
  return isLightDiagramTheme() ? "#f1f5f9" : "#0a121c";
}

export function mermaidThemeName(): "default" | "dark" {
  return isLightDiagramTheme() ? "default" : "dark";
}

/** Readable ink for rasterized Mermaid label fallbacks. */
export function diagramInk() {
  const ink = cssVar("--ink");
  if (ink) return ink;
  return isLightDiagramTheme() ? "#0f172a" : "#e8eef6";
}

export const THEME_CHANGE_EVENT = "nlm-theme-change";

export function dispatchThemeChange(theme: string) {
  try {
    window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: theme }));
  } catch {
    /* ignore */
  }
}
