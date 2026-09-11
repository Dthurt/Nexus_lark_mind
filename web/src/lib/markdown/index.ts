/**
 * Public markdown APIs for MarkdownBody (and related chat UI).
 * Matches Vue MarkdownBody.vue imports from @/utils/markdown (+ echarts/math).
 */

export {
  renderMarkdown,
  renderMarkdownWithMath,
  decorateMarkdownLinks,
  enhanceCodeBlocks,
  enhanceMarkdownRoot,
  renderMermaidIn,
  sanitizeMermaidSource,
  extractMermaidSource,
  renderDrawioIn,
  enhanceChatImages,
} from "./render";

export {
  renderEchartsIn,
  disposeEchartsIn,
  normalizeEchartsMarkdown,
  isEchartsLang,
  looksLikeEchartsOption,
} from "./echarts";

export { renderMathIn, protectMath, applyMathPlaceholders } from "./math";

export {
  isDrawioLang,
  looksLikeDrawioXml,
  normalizeDrawioXml,
  drawioMarkdownHtml,
} from "./drawio";

export { openMermaidFullscreen, closeMermaidFullscreen } from "./mermaidFullscreen";
