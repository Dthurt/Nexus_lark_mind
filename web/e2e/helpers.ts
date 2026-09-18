import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/** Skip locally when the stack is down; fail in CI instead of silent empty-page skips. */
export async function requireAdapters(request: APIRequestContext): Promise<void> {
  const res = await request.get("/health").catch(() => null);
  const up = Boolean(res && res.ok());
  if (up) return;
  if (process.env.CI) {
    throw new Error("adapters /health is not reachable (e2e stack did not start)");
  }
  test.skip(true, "adapters not running on baseURL");
}

export async function openWorkbench(page: Page): Promise<void> {
  const res = await page.goto("/", { waitUntil: "domcontentloaded" }).catch(() => null);
  if (!res || res.status() >= 500) {
    if (process.env.CI) {
      throw new Error(`workbench GET / failed: ${res ? res.status() : "no response"}`);
    }
    test.skip(true, "adapters not running on baseURL");
  }
  await expect(page.getByText("Nexus Lark Mind").first()).toBeVisible({ timeout: 20_000 });
}
