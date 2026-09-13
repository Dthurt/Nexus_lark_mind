# Canvas（旁侧产物面板）

工作台里的 **Canvas** 对齐 Cursor 的旁侧文档体验：不是无限白板，而是 **对话旁边一块可持久、可编辑的活页面**，用来放图表、表格、交付稿与自定义视图，避免全堆在气泡里。

主入口：Topbar 的 Canvas 图标、命令面板、消息图工具栏「Canvas」、Delivery「Canvas」、Agent 工具 `open_canvas`。

相关：聊天内图表渲染见 [diagrams.md](./diagrams.md)；交付审计见 [interaction-modes.md](./interaction-modes.md#delivery-artifact-plan--diagram--changes)；插件扩展见 [plugins.md](./plugins.md#ui-槽位cordis-lite)。

---

## 1. 产品定位

| 是 | 不是 |
|----|------|
| Chat ∥ Canvas 分栏产物区 | 无限节点白板 / Miro |
| 按 **会话** 存的多 tab 文档 | 全局唯一画布 |
| Mermaid / ECharts / Draw.io / Markdown / Table 编辑器 | 仅只读预览 |
| Agent 可 `open_canvas` 驱动 | 仅用户手动打开 |
| 可选落盘 `{cwd}/.nlm/canvases/` | 替代 Git / 源码仓库 |

与 **RightDock Delivery** 的分工：

- **Delivery**：计划批准后的「计划 → 图示 → 改仓审计」长文档（偏过程与变更）。
- **Canvas**：任意时刻打开的旁侧活文档（偏当前正在看/改的图与表）。Delivery 也可一键「打开到 Canvas」。

---

## 2. 路线图（已完成）

| 阶段 | 内容 | 状态 |
|------|------|------|
| **P1** | Chat∥Canvas 分栏；Mermaid/Delivery 打开；多 tab；会话 `localStorage` | Done |
| **P2** | Mermaid / ECharts / Draw.io 实编辑 + 写回；聊天工具栏 Canvas | Done |
| **P3** | Agent `open_canvas`、`.nlm/canvases`、REST `/canvas`、`registerCanvasView` / `canvas.view` | Done |

无限白板 / 自由节点图 **不做**（见 [deferred.md](./deferred.md)）。

---

## 3. 用户怎么用

### 3.1 打开

| 入口 | 行为 |
|------|------|
| Topbar **Canvas** 图标 | 切换分栏开/关（空面板也可开） |
| 命令面板 | 「打开 / 关闭 Canvas」「新建 Markdown Canvas」 |
| 消息内 Mermaid / ECharts / Draw.io 工具栏 **Canvas** | 把当前源码打开为对应 kind 的 tab（同内容会去重更新） |
| RightDock **Delivery → Canvas** | 打开交付 markdown |
| Agent 调用 `open_canvas` | SSE `task.canvas_open` → 自动打开 |

窄屏（&lt;900px）上下堆叠：上聊天、下 Canvas。

### 3.2 编辑与写回

分栏/预览/源码模式（视 kind）：

| 操作 | 含义 |
|------|------|
| **预览** | 只刷新预览，不写会话文档 |
| **应用** / **应用源码** | 把当前源码写回该 Canvas 文档（`localStorage`） |
| **复制** | 复制带 fence 的 markdown / 源码 |
| Draw.io **同步编辑器** | 向嵌入的 diagrams.net 请求 export，写回 XML |
| Draw.io 嵌入内保存 | `save` / `export` postMessage → 写回 |
| 顶栏 **保存** | `POST /api/sessions/{id}/canvas`：聊天文件卡片 + 本地 `.nlm/canvases/`（需绑定本机 cwd） |

### 3.3 Tab

- 最多保留约 **24** 个文档 / 会话。
- 关闭最后一个 tab 会收起面板；会话切换会加载该会话的 Canvas 快照。

---

## 4. 文档模型

前端：`web/src/lib/canvasDoc.ts`

```ts
type CanvasDocKind =
  | "markdown"
  | "mermaid"
  | "drawio"
  | "echarts"
  | "delivery"
  | "table";

type CanvasDoc = {
  id: string;          // cv_…
  title: string;
  kind: CanvasDocKind;
  body: string;        // 源码 / JSON / markdown
  updatedAt: string;   // ISO
  source?: string;     // 打开来源 / 去重键
};
```

会话状态（`localStorage` 键 `nlm_canvas_{sessionId}`）：

```json
{
  "open": true,
  "activeId": "cv_…",
  "docs": [ /* CanvasDoc[] */ ]
}
```

浏览器事件（用户入口与 SSE 最终都收敛到此）：

```ts
window.dispatchEvent(
  new CustomEvent("nlm-canvas-open", {
    detail: {
      kind: "mermaid",
      title: "架构",
      body: "graph TD; A-->B",
      dedupeKey: "mermaid:…",
      source: optional,
    },
  }),
);
```

Hook：`useCanvasSession(sessionId)` → `openDoc` / `updateDoc` / `updateActiveBody` / `togglePane` …

---

## 5. 内置视图（kind → UI）

注册表：`web/src/components/canvas/canvasRegistry.tsx`  
启动注册：`registerBuiltinCanvasViews.tsx`（由 `main.tsx` import）

| kind | 组件 | 说明 |
|------|------|------|
| `mermaid` | `MermaidCanvasEditor` | 分栏预览 + 源码；应用写回 |
| `echarts` | `EchartsCanvasEditor` | JSON option；应用前校验 `parseEchartsOption` |
| `drawio` | `DrawioCanvasEditor` | 嵌入 diagrams.net（可配）+ 源码 + 离线 SVG 兜底 |
| `table` | `TableCanvasView` | JSON 对象数组或 Markdown 管道表 |
| `markdown` / `delivery` | `MarkdownCanvasView` | Markdown 预览 + 源码 |
| （未知） | 回退 `MarkdownCanvasView` | |

未知 kind 仍可打开；插件用同名 key 覆盖内置视图。

### Table body 约定

JSON：

```json
[{"name":"a","n":1},{"name":"b","n":2}]
```

或 Markdown：

```md
| name | n |
| ---- | - |
| a    | 1 |
```

---

## 6. Agent：`open_canvas`

内置在 `builtin.workspace`（`workspace_tools.py`），**无需审批**（`SAFE_TOOLS`），计划模式也可用（`PLAN_ALLOWED_TOOLS`）。

### 参数

| 字段 | 必填 | 说明 |
|------|------|------|
| `body` | 是 | 文档正文（mermaid 源码、echarts JSON、drawio XML、markdown、表数据等） |
| `kind` | 否 | `markdown` \| `mermaid` \| `drawio` \| `echarts` \| `table` \| `delivery`（默认 `markdown`） |
| `title` | 否 | Tab 标题 |
| `file_name` | 否 | `.nlm/canvases/` 下文件名（默认由 title/kind 推导扩展名） |
| `persist` | 否 | 默认 `true`；本机 cwd 时落盘；SSH 落盘会记入 `persist_error`，UI 仍会打开 |

### 返回（工具结果摘要）

```json
{
  "ok": true,
  "kind": "mermaid",
  "title": "架构",
  "body": "…",
  "path": ".nlm/canvases/架构.mmd",
  "persist_error": null,
  "dedupe_key": ".nlm/canvases/架构.mmd"
}
```

### 事件链路

```
AgentRunner (open_canvas 成功)
  → chunk { canvas_open: { kind, title, body, dedupeKey, path } }
  → task_dispatcher → EventType.TASK_CANVAS_OPEN ("task.canvas_open")
  → Web SSE
  → useChatStream → window "nlm-canvas-open"
  → useCanvasSession.openDoc
  → CanvasPane + getCanvasView(kind)
```

系统提示（`agent_prompts.DIAGRAMS_MATH`）会引导：大图/表除 fence 外可再调 `open_canvas`。

示例：

> 画一个登录时序，用 mermaid，并用 open_canvas 打开到旁侧。

---

## 7. HTTP API

### `POST /api/sessions/{session_id}/canvas`

把内容发到会话（文件卡片）并可选写入工作区。

请求体：

```json
{
  "name": "架构.mmd",
  "content": "# 架构\n\n```mermaid\ngraph TD; A-->B\n```\n",
  "kind": "mermaid",
  "title": "架构",
  "cwd": "E:\\\\proj",
  "workspace_kind": "local"
}
```

响应要点：`file`（聊天卡片）、`workspace`（`{ ok, path, abs_path }` 或 `error`）、`canvas`。

前端：`postSessionCanvas()`（`web/src/api/endpoints.ts`）。Canvas 顶栏 **保存** 即调此接口。

落盘实现：`src/common/canvas_store.py` → `{cwd}/.nlm/canvases/`（**仅 local**；与 Delivery 的 `.nlm/deliveries/` 对称）。

---

## 8. 前端结构（关键路径）

| 路径 | 职责 |
|------|------|
| `web/src/lib/canvasDoc.ts` | 模型、localStorage、事件名 |
| `web/src/hooks/useCanvasSession.ts` | 会话状态、open/update、监听事件 |
| `web/src/components/canvas/CanvasPane.tsx` | 分栏 UI、tab、保存、视图宿主 |
| `web/src/components/canvas/*Editor*.tsx` / `*View.tsx` | 各 kind 编辑器 |
| `web/src/components/canvas/canvasRegistry.tsx` | `registerCanvasView` / `getCanvasView` |
| `web/src/pages/WorkbenchPage.tsx` | `nlm-center-split` 布局接线 |
| `web/src/styles/workbench.css` | `.nlm-center-split` / `.nlm-workspace--canvas` |
| `web/src/hooks/useChatStream.ts` | `task.canvas_open` |
| `web/src/lib/markdown/{render,echarts,drawio}.ts` | 聊天工具栏 Canvas 按钮 |

布局：Canvas 打开时工作区加宽（`nlm-workspace--canvas`），中栏 `minmax(0,1fr) minmax(280px,42%)`。

---

## 9. 插件：自定义 Canvas 视图

与 `registerToolView` 对称：

```ts
import { registerCanvasView } from "@/components/canvas/canvasRegistry";
import type { CanvasViewProps } from "@/components/canvas/canvasRegistry";

function MyKanbanView({ doc, onCommit }: CanvasViewProps) {
  // doc.kind / doc.body / doc.title
  // 编辑后 onCommit(nextBody) 写回会话 Canvas
  return <div>…</div>;
}

registerCanvasView("kanban", MyKanbanView);
```

- Slot 名：`SlotNames.CANVAS_VIEW` = `"canvas.view"`
- 在 `main.tsx`（或插件入口）副作用注册
- Dock **插件 → 扩展槽** 列出已注册 key
- Agent：`open_canvas` 时 `kind: "kanban"`（若未在 schema enum 中，服务端会落到 `markdown`——自定义 kind 建议先扩展 TOOLS enum，或前端仅用用户事件打开）

> 当前工具 schema 的 `kind` enum 为固定集合。纯前端自定义 kind 可用 `nlm-canvas-open` 打开；若要让模型直接选该 kind，需同步改 `workspace_tools.TOOLS` 里 `open_canvas` 的 enum。

前端扩展细节另见 [web/docs/canvas-views.md](../web/docs/canvas-views.md)。

---

## 10. 与聊天图表的关系

聊天气泡内仍渲染 fence（只读工具栏）；Canvas 是 **可编辑副本**：

1. 气泡内点 Canvas → 复制 body 进会话文档  
2. 在 Canvas 里改并 **应用** → 只更新 Canvas 文档，**不会**自动改历史气泡  
3. 需要进仓库时用 **保存** → `.nlm/canvases/` 或自行 `write_file`

体验档 **Fast** 时聊天内 Draw.io 降级为源码；仍可打开 Canvas，但嵌入编辑依赖网络/本地 `/drawio/`。详见 [experience-tiers.md](./experience-tiers.md)、[diagrams.md](./diagrams.md)。

---

## 11. 测试

| 测试 | 覆盖 |
|------|------|
| `tests/test_canvas_store.py` | `.nlm/canvases` 写入、SSH 拒绝、文件名消毒 |
| `web/src/lib/canvasDoc.test.ts` | create / localStorage / echarts parse |
| `web/src/components/canvas/canvasRegistry.test.ts` | 注册表 + table 解析 |

```bash
pytest tests/test_canvas_store.py -q
cd web && npm test -- src/lib/canvasDoc.test.ts src/components/canvas/canvasRegistry.test.ts
```

---

## 12. 故障排查

| 现象 | 排查 |
|------|------|
| 点 Canvas 无反应 | 刷新前端；确认 `useCanvasSession` 已挂在 Workbench；看控制台是否 `nlm-canvas-open` |
| Agent 调了工具但未打开 | 看 SSE 是否有 `task.canvas_open`；Kernel/Orchestrator 是否含新 `EventType`；硬刷新前端 |
| **保存** 无磁盘文件 | 需 **local** cwd；SSH 仅发聊天卡片；看 toast / `workspace.error` |
| Draw.io 只有离线 SVG | 未部署 `web/public/drawio/` 或未设 `localStorage.nlm_drawio_embed`；Canvas 编辑器默认可用远程 embed |
| ECharts 应用失败 | body 须为合法 option JSON（可容忍尾逗号/智能引号） |

---

## Related

- [diagrams.md](./diagrams.md) — 聊天内 Mermaid / ECharts / Draw.io  
- [interaction-modes.md](./interaction-modes.md) — Delivery 与计划模式  
- [plugins.md](./plugins.md) — Cordis-lite 槽位  
- [client-architecture.md](./client-architecture.md) — 工作台布局  
- [workspaces.md](./workspaces.md) — cwd 与 `.nlm/`  
- [deferred.md](./deferred.md) — 已完成项与仍延期项  
- [web/docs/canvas-views.md](../web/docs/canvas-views.md) — 前端扩展 API  
