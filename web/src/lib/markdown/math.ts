/** KaTeX math — protect delimiters from Markdown, then render. */

let katexReady: Promise<{ katex: any }> | null = null;

async function ensureKatex() {
  if (!katexReady) {
    katexReady = Promise.all([
      import("katex"),
      import("katex/dist/katex.min.css"),
    ]).then(([katexMod]) => ({
      katex: (katexMod as any).default || katexMod,
    }));
  }
  return katexReady;
}

function ph(i: number) {
  return `%%NLM_MATH_${i}%%`;
}

/**
 * Pull math out of markdown so marked cannot mangle `_`, `*`, etc. inside TeX.
 * Supports $$ $$ , \\[ \\] , $ $ , \\( \\) .
 */
export function protectMath(markdown: string) {
  const slots: { tex: string; display: boolean }[] = [];
  let text = String(markdown || "");

  const stash = (tex: string, display: boolean) => {
    const id = slots.length;
    slots.push({ tex: String(tex).trim(), display: !!display });
    return ph(id);
  };

  // Display math first
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_: string, tex: string) => stash(tex, true));
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, (_: string, tex: string) => stash(tex, true));
  // Inline \( ... \)
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_: string, tex: string) => stash(tex, false));
  // Inline $...$ (single-line; avoid $$)
  text = text.replace(/(?<!\$)\$(?!\$)((?:\\.|[^$\n\\])+?)\$(?!\$)/g, (_: string, tex: string) => stash(tex, false));

  return { text, slots };
}

function renderSlot(katex: any, slot: { tex: string; display: boolean }) {
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
  } catch {
    const fallback = escapeHtml(slot.tex);
    return slot.display
      ? `<pre class="katex-fallback">${fallback}</pre>`
      : `<code class="katex-fallback">${fallback}</code>`;
  }
}

function escapeHtml(s: string) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Replace %%NLM_MATH_n%% placeholders in HTML with KaTeX output. */
export async function applyMathPlaceholders(html: string, slots: { tex: string; display: boolean }[]) {
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

/** Render one LaTeX string into an element (Office canvas + chat). */
export async function renderLatex(target: HTMLElement | null, latex: string, display = true) {
  if (!target) return;
  const tex = String(latex || "").trim();
  if (!tex) {
    target.textContent = "";
    return;
  }
  const { katex } = await ensureKatex();
  try {
    katex.render(tex, target, {
      displayMode: !!display,
      throwOnError: false,
      strict: "ignore",
      trust: false,
      output: "html",
    });
  } catch {
    target.textContent = tex;
    target.classList.add("katex-fallback");
  }
}

/** DOM pass for any leftover delimiters (rare). */
export async function renderMathIn(root: HTMLElement | null) {
  if (!root) return;
  // Placeholders are applied in markdown pipeline; keep a light auto-render fallback
  try {
    const auto = await import("katex/contrib/auto-render");
    const renderMathInElement =
      (auto as any).default || (auto as any).renderMathInElement || auto;
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
