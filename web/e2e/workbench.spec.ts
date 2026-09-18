/**
 * Key-path e2e against demo-mode adapters (PLAYWRIGHT_BASE_URL, default :8000).
 * Skip only when the process is down; CI must fail if the stack never booted.
 */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { openWorkbench, requireAdapters } from "./helpers";

test.describe("workspace trust", () => {
  test("bind workspace shows trust confirmation", async ({ page, request }) => {
    await requireAdapters(request);
    await openWorkbench(page);

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nlm-e2e-ws-"));
    await page.getByTestId("workspace-path-input").fill(dir);
    await page.getByTestId("workspace-bind-btn").click();

    const dialog = page.getByTestId("workspace-trust-dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByText("信任此文件夹？")).toBeVisible();
    await page.getByTestId("workspace-trust-skip").click();
    await expect(dialog).toBeHidden();
  });
});

test.describe("knowledge base", () => {
  test("add document then search hits", async ({ page, request }) => {
    await requireAdapters(request);
    await page.goto("/knowledge", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("knowledge-library-rail")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("knowledge-ingest-paste").click();
    await expect(page.getByTestId("knowledge-add-content")).toBeVisible({ timeout: 20_000 });

    const token = `nlm_e2e_kb_${Date.now()}`;
    await page.getByTestId("knowledge-add-title").fill(`E2E ${token}`);
    await page.getByTestId("knowledge-add-content").fill(`Marker ${token} in the local knowledge base.`);
    await page.getByTestId("knowledge-add-submit").click();
    await expect(page.getByText(token).first()).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("knowledge-search-input").fill(token);
    await page.getByTestId("knowledge-search-submit").click();
    await expect(page.getByText(token).first()).toBeVisible({ timeout: 15_000 });
  });

  test("knowledge picker stays on local when WeKnora is unconfigured", async ({ page, request }) => {
    await requireAdapters(request);
    await openWorkbench(page);

    await page.getByTestId("knowledge-scope-picker").first().click();
    await expect(page.getByTestId("knowledge-scope-local")).toBeVisible();
    await expect(page.getByText(/未配置 WeKnora|本地知识库/).first()).toBeVisible();
    await page.getByTestId("knowledge-scope-local").click();
    await expect(page.getByTestId("knowledge-scope-picker").first()).toContainText("本地知识库");
  });

  test("labeled entries open dedicated knowledge chat", async ({ page, request }) => {
    await requireAdapters(request);
    await openWorkbench(page);

    await expect(page.getByTestId("view-ring-knowledge")).toContainText("知识库");
    await expect(page.getByTestId("topbar-knowledge-entry")).toContainText("知识库");
    await expect(page.getByTestId("empty-open-knowledge")).toBeVisible();
    await expect(page.getByTestId("composer-open-knowledge")).toBeVisible();

    await page.getByTestId("empty-open-knowledge").click();
    await expect(page).toHaveURL(/\/knowledge/);
    await expect(page.getByTestId("knowledge-page")).toBeVisible();
    await expect(page.getByTestId("knowledge-search-input")).toBeVisible();
    await expect(page.getByTestId("knowledge-go-chat")).toBeVisible();
    await expect(page.getByTestId("knowledge-import-file")).toBeVisible();
    await expect(page.getByTestId("knowledge-library-rail")).toBeVisible();
    await expect(page.getByTestId("knowledge-ingest-files")).toBeVisible();
    await expect(page.getByTestId("knowledge-ingest-paste")).toBeVisible();
    await expect(page.getByTestId("knowledge-format-pdf")).toBeVisible();
    await expect(page.getByTestId("composer-open-knowledge")).toHaveCount(0);
  });
});

test.describe("session uploads", () => {
  test("composer upload shows a revocable chip", async ({ page, request }) => {
    await requireAdapters(request);
    await openWorkbench(page);

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nlm-e2e-up-"));
    const filePath = path.join(dir, "session-note.md");
    const token = `nlm_e2e_upload_${Date.now()}`;
    fs.writeFileSync(filePath, `# ${token}\n\nTemporary session document.\n`, "utf8");

    await page.getByTestId("composer-file-input").setInputFiles(filePath);
    const chip = page.getByTestId("session-upload-chip");
    await expect(chip).toBeVisible({ timeout: 20_000 });
    await expect(chip).toContainText("session-note");
    await chip.click();
    await expect(chip).toHaveCount(0);
  });
});
