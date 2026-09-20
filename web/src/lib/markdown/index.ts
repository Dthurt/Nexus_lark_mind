/**
 * Public markdown APIs for MarkdownBody (and related chat UI).
 * Matches Vue MarkdownBody.vue imports from @/utils/markdown (+ echarts/math).
 */

export {
  renderMarkdown,
  renderMarkdownLight,
  renderMarkdownWithMath,
  decorateMarkdownLinks,
  enhanceCodeBlocks,
  enhanceMarkdownRoot,
  renderMermaidIn,
  sanitizeMermaidSource,
  extractMermaidSource,
  renderDrawioIn,
  enhanceChatImages,
  renderMindmapIn,
} from "./render";

export { splitSettledMarkdown } from "./streamSplit";

export {
  renderEchartsIn,
  disposeEchartsIn,
  normalizeEchartsMarkdown,
  isEchartsLang,
  looksLikeEchartsOption,
  parseEchartsOption,
} from "./echarts";

export { renderMathIn, renderLatex, protectMath, applyMathPlaceholders } from "./math";

export {
  isDrawioLang,
  looksLikeDrawioXml,
  normalizeDrawioXml,
  drawioMarkdownHtml,
} from "./drawio";

export { isMindmapLang, mindmapMarkdownHtml } from "./mindmap";

export { openMermaidFullscreen, closeMermaidFullscreen } from "./mermaidFullscreen";
