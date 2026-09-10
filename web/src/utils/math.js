/** KaTeX math — protect delimiters from Markdown, then render. */

let katexReady = null;

async function ensureKatex() {
  if (!katexReady) {
    katexReady = Promise.all([
      import("katex"),
      import("katex/dist/katex.min.css"),
    ]).then(([katexMod]) => ({
      katex: katexMod.default || katexMod,
    }));
  }
  return katexReady;
}

function ph(i) {
  return `%%NLM_MATH_${i}%%`;
}

/**
 * Pull math out of markdown so marked cannot mangle `_`, `*`, etc. inside TeX.
 * Supports $$ $$ , \\[ \\] , $ $ , \\( \\) .
 */
export function protectMath(markdown) {
  const slots = [];
  let text = String(markdown || "");

  const stash = (tex, display) => {
    const id = slots.length;
    slots.push({ tex: String(tex).trim(), display: !!display });
    return ph(id);
  };

  // Display math first
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => stash(tex, true));
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, (_, tex) => stash(tex, true));
  // Inline \( ... \)
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_, tex) => stash(tex, false));
  // Inline $...$ (single-line; avoid $$)
  text = text.replace(/(?<!\$)\$(?!\$)((?:\\.|[^$\n\\])+?)\$(?!\$)/g, (_, tex) => stash(tex, false));

  return { text, slots };
}

function renderSlot(katex, slot) {
  try {
    const html = katex.renderToString(slot.tex, {
      displayMode: slot.display,
      throwOnError: false,
      strict: "ignore",
      trust: false,
      output: "html",
    });
    if (slot.display) {
      return `<div class="katex-display-host">${html}</div>`;
    }
    return `<span class="katex-inline-host">${html}</span>`;
  } catch (err) {
    const fallback = escapeHtml(slot.tex);
    return slot.display
      ? `<pre class="katex-fallback">${fallback}</pre>`
      : `<code class="katex-fallback">${fallback}</code>`;
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Replace %%NLM_MATH_n%% placeholders in HTML with KaTeX output. */
export async function applyMathPlaceholders(html, slots) {
  if (!slots?.length) return html;
  const { katex } = await ensureKatex();
  let out = String(html || "");
  for (let i = 0; i < slots.length; i += 1) {
    const token = ph(i);
    const rendered = renderSlot(katex, slots[i]);
    if (!out.includes(token)) continue;
    // Prefer replacing a whole paragraph that only contains the placeholder
    const para = new RegExp(`<p>\\s*${token.replace(/%/g, "\\%")}\\s*</p>`, "g");
    if (para.test(out)) {
      out = out.replace(para, rendered);
    } else {
      out = out.split(token).join(rendered);
    }
  }
  return out;
}

/** DOM pass for any leftover delimiters (rare). */
export async function renderMathIn(root) {
  if (!root) return;
  // Placeholders are applied in markdown pipeline; keep a light auto-render fallback
  try {
    const auto = await import("katex/contrib/auto-render");
    const renderMathInElement = auto.default || auto.renderMathInElement || auto;
    renderMathInElement(root, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
      strict: "ignore",
      ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option", "svg"],
    });
  } catch (err) {
    console.warn("katex auto-render failed", err);
  }
}
