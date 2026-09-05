# 製程流程圖 × 下游分析整合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓製程流程圖成為下游分析（SPC / Monte-Carlo / Exploration）的參數化入口：新增跨節點關聯鍵、節點資料面板可點擊跳轉（帶入欄位）、下游 tab 依節點篩選。

**Architecture:** 三層分工 — 引擎層把 `association_keys` 加進 `ProjectManifest` 並擴充 `project/flow-graph` IPC；前端新增一個 zustand 跳轉 store（`processFlowNavStore`）+ 共用 helper（`processFlowContext.ts`）讓「從流程圖跳進來」與「在目標 tab 選節點」共用同一套套用邏輯；目標 tab（SPC/MC/Exploration）掛載時消費上下文、初始化欄位，並加「製程節點」篩選下拉。跳轉**不自動載入資料源**（只帶 dataset_id + 欄位），資料源未載入即顯示提示。

**Tech Stack:** TypeScript + React 19 + Ant Design 5 + zustand；Python 引擎 manifest.py / main.py；引擎測試 pytest；前端驗證 `npx tsc --noEmit` + `npm run build`。

**設計文件參考:** `docs/superpowers/specs/2026-09-05-process-flow-analysis-integration-design.md`

**約定（workflow）：**
- 引擎測試命令：`cd engine && .venv/bin/python -m pytest tests/ -q`
- 前端驗證：`npx tsc --noEmit`、`npm run build`
- 三語 i18n 一致性：所有 `t('processFlow.*')` / `t('spc.*')` 新 key 必須三檔（en/zh-TW/es-MX）同步加
- 每次提交單一邏輯變更；commit message 慣例見各 Task
- commit 排除：`engine/.coverage`、`src-tauri/icons/` 未追蹤目錄
- 引擎 handler 測試慣例：直接 `handle_request("method", params)`（見 `tests/test_main_handlers.py`）

---

## File Structure

| 檔案 | 動作 | 責任 |
|------|------|------|
| `engine/src/process_intelligence_engine/project/manifest.py` | Modify | `ProjectManifest.association_keys` + `set_association_keys()` |
| `engine/src/process_intelligence_engine/main.py` | Modify | `_handle_project_flow_graph` 支援 `set_association_keys` |
| `engine/tests/test_manifest_nodes.py` | Modify | association_keys 存取與持久化測試 |
| `engine/tests/test_main_handlers.py` | Modify | handler 層 set/get 測試 |
| `src/lib/engine.ts` | Modify | `FlowGraph.association_keys` 型別 + `setAssociationKeys()` |
| `src/stores/processFlowNavStore.ts` | **Create** | 跳轉 store（pending / navigate / consume） |
| `src/lib/processFlowContext.ts` | **Create** | 節點上下文套用 helper（共用） |
| `src/App.tsx` | Modify | 訂閱跳轉 store 切換 tab |
| `src/features/process-flow/ProcessFlow.tsx` | Modify | 關聯鍵 UI + 跳轉按鈕 |
| `src/features/spc/SPC.tsx` | Modify | 消費上下文 + 節點篩選 |
| `src/features/monte-carlo/MonteCarlo.tsx` | Modify | 消費上下文 + 節點篩選 |
| `src/features/exploration/Exploration.tsx` | Modify | 消費上下文 + 節點篩選 |
| `src/i18n/en.json` `zh-TW.json` `es-MX.json` | Modify | 三語新 keys |

---

## Task 1: 引擎 — ProjectManifest.association_keys + set_association_keys (TDD)

**Files:**
- Modify: `engine/src/process_intelligence_engine/project/manifest.py`
- Test: `engine/tests/test_manifest_nodes.py`

- [ ] **Step 1: Write failing tests**

在 `tests/test_manifest_nodes.py` 末尾追加：

```python
def test_manifest_association_keys_default_empty():
    eng = _engine()
    g = eng.get_flow_graph()
    assert "association_keys" in g
    assert g["association_keys"] == []

def test_manifest_set_association_keys_persists():
    eng = _engine()
    eng.set_association_keys(["barcode", "serial_no", "batch_no"])
    g = eng.get_flow_graph()
    assert g["association_keys"] == ["barcode", "serial_no", "batch_no"]

def test_manifest_association_keys_survive_reload():
    import json
    eng = _engine()
    eng.set_association_keys(["work_order"])
    # 重載 manifest 物件
    from process_intelligence_engine.project.manifest import ProjectManifest
    with open(eng._manifest_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    m2 = ProjectManifest.from_dict(d)
    assert m2.association_keys == ["work_order"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_manifest_nodes.py -q`
Expected: 3 FAIL — `association_keys` attribute/column missing。

- [ ] **Step 3: Implement manifest changes**

`manifest.py` 的 `ProjectManifest` dataclass（line ~148 `settings` 之後）加欄位：

```python
    settings: dict[str, Any] = field(default_factory=dict)
    association_keys: list[str] = field(default_factory=list)
```

`ProjectEngine` 類別（`delete_process_node` 之後）加方法：

```python
    def set_association_keys(self, keys: list[str]) -> dict[str, Any]:
        self._ensure_project()
        manifest = self._load()
        manifest.association_keys = [str(k).strip() for k in keys if str(k).strip()]
        self._save()
        return {"association_keys": list(manifest.association_keys)}
```

`get_flow_graph()`（line 506-522）的 return 改為：

```python
        return {
            "nodes": nodes,
            "edges": edges,
            "association_keys": list(manifest.association_keys),
        }
```

（`association_keys` 走 `to_dict`/`from_dict` 的 `asdict`/`__dataclass_fields__` 自動序列化，無需另行處理。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/test_manifest_nodes.py -q`
Expected: 全 PASS（含既有 5 個 + 新 3 個）。

- [ ] **Step 5: Run full engine suite**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: 全 PASS（原 284 passed, 1 skipped → 287 passed, 1 skipped，含既有 xfail 情境）。

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/project/manifest.py engine/tests/test_manifest_nodes.py
git commit -m "feat(engine): ProjectManifest.association_keys + set_association_keys"
```

---

## Task 2: 引擎 — project/flow-graph IPC 支援 association_keys (TDD)

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_main_handlers.py`

- [ ] **Step 1: Write failing test**

在 `tests/test_main_handlers.py` 末尾追加（沿用 `handle_request` 直接呼叫慣例）：

```python
def test_handle_flow_graph_set_association_keys():
    result = handle_request("project/flow-graph", {"set_association_keys": ["barcode", "batch_no"]})
    assert result["association_keys"] == ["barcode", "batch_no"]
    again = handle_request("project/flow-graph", {})
    assert again["association_keys"] == ["barcode", "batch_no"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_main_handlers.py::test_handle_flow_graph_set_association_keys -v`
Expected: FAIL — `get_flow_graph` 忽略 params，無 set 動作、且無 `association_keys` 欄。

- [ ] **Step 3: Implement handler**

`main.py` 的 `_handle_project_flow_graph`（line 1766）改為：

```python
def _handle_project_flow_graph(params: dict) -> dict:
    keys = params.get("set_association_keys")
    if keys is not None:
        return PROJECT_ENGINE.set_association_keys(keys)
    return PROJECT_ENGINE.get_flow_graph()
```

（`project/flow-graph` 的 dispatch 分支已存在，無需改。）`main.py` 需確保 `PROJECT_ENGINE` 狀態於測試間隔離——沿用既有 test 對 `PROJECT_ENGINE` 的共用方式即可（單測內先 set 再 get 驗證同結果）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && .venv/bin/python -m pytest tests/test_main_handlers.py -q`
Expected: 全 PASS（含既有 handlers 測試）。

- [ ] **Step 5: Run full engine suite**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: 288 passed, 1 skipped。

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/main.py engine/tests/test_main_handlers.py
git commit -m "feat(engine): project/flow-graph set_association_keys IPC"
```

---

## Task 3: 前端 — engine.ts FlowGraph.association_keys + setAssociationKeys()

**Files:**
- Modify: `src/lib/engine.ts:1372-1390`

- [ ] **Step 1: Extend FlowGraph type**

`src/lib/engine.ts` 的 `FlowGraph` interface 改為：

```ts
export interface FlowGraph {
  nodes: FlowNode[]
  edges: FlowEdge[]
  association_keys: string[]
}
```

在 `getFlowGraph()` 之後（line ~1390）加：

```ts
export async function setAssociationKeys(keys: string[]): Promise<{ association_keys: string[] }> {
  return engineCall<{ association_keys: string[] }>('project/flow-graph', {
    set_association_keys: keys,
  } as unknown as Record<string, unknown>)
}
```

- [ ] **Step 2: Typecheck**

Run: `npx tsc --noEmit`
Expected: clean（ProcessFlow 內 `FlowGraph` 型別會暫時缺 `association_keys` 初始化——若報錯，見 Task 4 Step 3 一併處理；若 tsc 因 `void loadData()` 前未 set 而報「missing property」，先暫以 `association_keys: []` 初始值補上）。

- [ ] **Step 3: Commit**

```bash
git add src/lib/engine.ts
git commit -m "feat(engine-api): FlowGraph.association_keys + setAssociationKeys"
```

---

## Task 4: 前端 — 跳轉 store + 共用 helper（基礎設施）

**Files:**
- Create: `src/stores/processFlowNavStore.ts`
- Create: `src/lib/processFlowContext.ts`

- [ ] **Step 1: Create nav store**

`src/stores/processFlowNavStore.ts`：

```ts
import { create } from 'zustand'
import type { AppTab } from '../types'

export interface ProcessNodeContext {
  nodeId: string
  displayName: string
  field?: string
  dataSourceIds?: string[]
}

interface ProcessFlowNavState {
  pending: { targetTab: AppTab; context: ProcessNodeContext } | null
  navigate: (targetTab: AppTab, context: ProcessNodeContext) => void
  consume: () => ProcessNodeContext | undefined
}

export const useProcessFlowNavStore = create<ProcessFlowNavState>((set) => ({
  pending: null,
  navigate: (targetTab, context) => set({ pending: { targetTab, context } }),
  consume: () => {
    let ctx: ProcessNodeContext | undefined
    set((s) => {
      ctx = s.pending?.context
      return { pending: null }
    })
    return ctx
  },
}))
```

- [ ] **Step 2: Create shared context helper**

`src/lib/processFlowContext.ts`：

```ts
import { useProcessFlowNavStore, type ProcessNodeContext } from '../stores/processFlowNavStore'
import { getFlowGraph, type FlowNode } from './engine'

export interface NodeContextResult {
  context: ProcessNodeContext | undefined
  node: FlowNode | null
  dataSourceLoaded: boolean
}

export function consumeNodeContext(): ProcessNodeContext | undefined {
  return useProcessFlowNavStore.getState().consume()
}

export async function findNodeById(nodeId: string): Promise<FlowNode | null> {
  try {
    const graph = await getFlowGraph()
    return graph.nodes.find((n) => n.process_node_id === nodeId) ?? null
  } catch {
    return null
  }
}

export function dataSourceLoaded(dataSourceIds: string[] | undefined, currentDatasetId: string | undefined): boolean {
  if (!dataSourceIds || dataSourceIds.length === 0) return true
  return dataSourceIds.includes(currentDatasetId ?? '')
}
```

- [ ] **Step 3: Typecheck**

Run: `npx tsc --noEmit`
Expected: clean（新檔案無參照問題）。若此步順便把 ProcessFlow 的 `useState<FlowGraph>` 初始化補上 `association_keys: []`（見 Task 5），本步只驗證兩個新檔獨立無 error。

- [ ] **Step 4: Commit**

```bash
git add src/stores/processFlowNavStore.ts src/lib/processFlowContext.ts
git commit -m "feat(ui): processFlow nav store + context helper"
```

---

## Task 5: ProcessFlow — 關聯鍵 UI + 跳轉按鈕

**Files:**
- Modify: `src/features/process-flow/ProcessFlow.tsx`
- Modify: `src/i18n/en.json` / `zh-TW.json` / `es-MX.json`

- [ ] **Step 1: Import 新 API + store**

`src/features/process-flow/ProcessFlow.tsx` 的 import 區補充：

```ts
import { setAssociationKeys, type FlowGraph } from '../../lib/engine'
import { useProcessFlowNavStore } from '../../stores/processFlowNavStore'
```

（既有 import 已有 `getFlowGraph`、`type FlowGraph`。）

- [ ] **Step 2: 關聯鍵初始值與載入**

`const [graph, setGraph] = useState<FlowGraph>({ nodes: [], edges: [] })` 改為：

```ts
const [graph, setGraph] = useState<FlowGraph>({ nodes: [], edges: [], association_keys: [] })
```

`loadData()` 內 Promise.all 後，`setGraph` 前確保 `g.association_keys` 有值（引擎已有預設空陣列），無需額外處理。

- [ ] **Step 3: 空選面板 → 關聯鍵編輯**

元件 `return` 中 Properties Card 的 `selectedNode ? (...) : (<Alert .../>)` 分支的 `Alert` 改為關聯鍵編輯區：

```tsx
) : (
  <Space direction="vertical" style={{ width: '100%' }} size={8}>
    <Typography.Text strong>{t('processFlow.associationKeys')}</Typography.Text>
    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
      {t('processFlow.associationKeysDesc')}
    </Typography.Text>
    <Select
      mode="tags"
      style={{ width: '100%' }}
      placeholder={t('processFlow.associationKeysPlaceholder')}
      value={graph.association_keys}
      onChange={async (vals) => {
        const keys = vals as string[]
        try {
          const res = await setAssociationKeys(keys)
          setGraph((prev) => ({ ...prev, association_keys: res.association_keys }))
          messageApi.success(t('processFlow.associationKeysSaved'))
        } catch {
          messageApi.error(t('processFlow.saveError'))
        }
      }}
    />
  </Space>
)
```

（`Typography`、`Select`、`messageApi` 均已 import。）

- [ ] **Step 4: 跳轉按鈕（節點屬性面板）**

在既有屬性面板的 `machine_mapping` Select（line ~735-740）之後、`connectTo` 區塊之前，插入：

```tsx
{/* Jump to downstream analysis */}
<Typography.Text strong style={{ marginTop: 8 }}>
  {t('processFlow.jumpToAnalysis')}
</Typography.Text>
{selectedNode.out_quality_outputs.length > 0 && (
  <Space wrap>
    <Button
      size="small"
      icon={<LineChartOutlined />}
      onClick={() => gotoAnalysisTab('spc', selectedNode)}
    >
      {t('processFlow.jumpToSqc')}
    </Button>
    <Button
      size="small"
      icon={<RobotOutlined />}
      onClick={() => gotoAnalysisTab('monteCarlo', selectedNode)}
    >
      {t('processFlow.jumpToMonteCarlo')}
    </Button>
  </Space>
)}
{selectedNode.in_control_parameters.length > 0 && (
  <Button
    size="small"
    icon={<BarChartOutlined />}
    onClick={() => gotoAnalysisTab('exploration', selectedNode)}
  >
    {t('processFlow.jumpToExploration')}
  </Button>
)}
```

需新增 icons import：

```ts
import {
  PlusOutlined,
  DeleteOutlined,
  CheckOutlined,
  WarningOutlined,
  ArrowRightOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  ApartmentOutlined,
  LineChartOutlined,
  RobotOutlined,
  BarChartOutlined,
} from '@ant-design/icons'
```

在元件內（`saveMapping` 附近）新增 handler：

```ts
const gotoAnalysisTab = (
  tab: 'spc' | 'monteCarlo' | 'exploration',
  node: FlowNode,
) => {
  const dataSourceIds = [
    ...(node.output_data_sources ?? []),
    ...(node.input_data_sources ?? []),
  ]
  const field =
    tab === 'exploration'
      ? node.in_control_parameters?.[0]
      : node.out_quality_outputs?.[0]
  useProcessFlowNavStore.getState().navigate(tab, {
    nodeId: node.process_node_id,
    displayName: node.display_name,
    field,
    dataSourceIds,
  })
}
```

（`FlowNode` 型別已 import。）

- [ ] **Step 5: i18n 三語**

新增 keys（en / zh-TW / es-MX 三檔 `processFlow` 區塊皆加，值分別翻成對應語言）：

```
associationKeys                          Flow association keys / 流程關聯鍵 / Claves de asociación de flujo
associationKeysDesc                      Cross-node analysis joins via common keys (spec §11A) / 跨節點分析透過共同關聯鍵串接（規格 §11A）/ El análisis entre nodos se une mediante claves comunes (§11A)
associationKeysPlaceholder               barcode, serial_no, batch_no, work_order
associationKeysSaved                     Association keys saved / 關聯鍵已儲存 / Claves de asociación guardadas
jumpToAnalysis                           Jump to analysis / 跳到分析 / Ir al análisis
jumpToSqc                                SPC / SPC / SPC
jumpToMonteCarlo                         Monte-Carlo / 蒙地卡羅 / Monte-Carlo
jumpToExploration                        Exploration / 探索分析 / Exploración
```

- [ ] **Step 6: Verify**

Run: `npx tsc --noEmit`（clean）+ `npm run build`（成功）
Run: python 三語 JSON 檢查（三檔 key 一致、無缺漏）：
```bash
python3 -c "import json; a=json.load(open('src/i18n/en.json'));b=json.load(open('src/i18n/zh-TW.json'));c=json.load(open('src/i18n/es-MX.json'));pf=lambda d:set(d['processFlow']);print('ok' if pf(a)==pf(b)==pf(c) else 'MISMATCH')"
```
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add src/features/process-flow/ProcessFlow.tsx src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(process-flow): association keys UI + jump buttons"
```

---

## Task 6: App.tsx — 訂閱跳轉 store 切換 tab

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Wire up subscription**

`src/App.tsx` import 區加：

```ts
import { useProcessFlowNavStore } from './stores/processFlowNavStore'
import { useEffect } from 'react'
```

`App()` 元件內 `const [activeTab, setActiveTab] = useState<AppTab>('project')` 之後加：

```ts
const pendingTarget = useProcessFlowNavStore((s) => s.pending?.targetTab)

useEffect(() => {
  if (pendingTarget && pendingTarget !== activeTab) {
    setActiveTab(pendingTarget)
  }
}, [pendingTarget, activeTab])
```

> 說明：`pending` 由目標 tab mount 時 `consume()` 清除；`App` 僅負責切換 `activeTab`。若已在同一 tab，不切換（避免 loop），而目標 tab 的 mount effect 仍會消費上下文。

- [ ] **Step 2: Verify**

Run: `npx tsc --noEmit`（clean）+ `npm run build`（成功）

- [ ] **Step 3: Commit**

```bash
git add src/App.tsx
git commit -m "feat(ui): subscribe processFlow nav store in App.tsx"
```

---

## Task 7: SPC — 消費上下文 + 依節點篩選

**Files:**
- Modify: `src/features/spc/SPC.tsx`
- Modify: `src/i18n/en.json` / `zh-TW.json` / `es-MX.json`

- [ ] **Step 1: Import helper + state**

`SPC.tsx` import 區加：

```ts
import { consumeNodeContext, findNodeById, dataSourceLoaded } from '../../lib/processFlowContext'
import { getFlowGraph, type FlowNode } from '../../lib/engine'
```

元件內新增 state（`column` state 之後）：

```ts
const [flowNodes, setFlowNodes] = useState<FlowNode[]>([])
const [selectedFlowNode, setSelectedFlowNode] = useState<FlowNode | null>(null)
const [sourceLoaded, setSourceLoaded] = useState(true)
const [sourceTag, setSourceTag] = useState<string | undefined>()
```

- [ ] **Step 2: 載入節點清單 + 消費跳轉上下文**

新增 mount effect：

```ts
useEffect(() => {
  void getFlowGraph()
    .then((g) => setFlowNodes(g.nodes))
    .catch(() => {})

  const ctx = consumeNodeContext()
  if (!ctx) {
    setSourceTag(undefined)
    return
  }
  setSourceTag(ctx.displayName)
  void findNodeById(ctx.nodeId).then((node) => {
    if (!node) return
    setSelectedFlowNode(node)
    const loaded = dataSourceLoaded(ctx.dataSourceIds, importResult?.dataset_id)
    setSourceLoaded(loaded)
    const preferred = ctx.field && numericColumns.includes(ctx.field)
      ? ctx.field
      : node.out_quality_outputs?.find((c) => numericColumns.includes(c))
    if (preferred) setColumn(preferred)
  })
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [])
```

> 注意：`importResult` 在 mount 時可能尚未就緒；此 effect 為一次性。若跳轉時資料源未載入，`sourceLoaded=false` → 顯示提示。

- [ ] **Step 3: 節點篩選下拉（工具列）**

`<Card title={t('spc.title')}>` 內、`Space wrap style={{ marginBottom: 12 }}` 開頭，插入第一個 Form.Item：

```tsx
{flowNodes.length > 0 && (
  <Form.Item label={t('spc.filterByNode')} style={{ margin: 0 }}>
    <Select
      allowClear
      style={{ width: 220 }}
      placeholder={t('spc.filterByNodePlaceholder')}
      value={selectedFlowNode?.process_node_id}
      options={flowNodes.map((n) => ({
        value: n.process_node_id,
        label: n.display_name,
      }))}
      onChange={(nodeId) => {
        const node = flowNodes.find((n) => n.process_node_id === nodeId)
        if (!node) {
          setSelectedFlowNode(null)
          setSourceTag(undefined)
          setSourceLoaded(true)
          return
        }
        setSelectedFlowNode(node)
        setSourceTag(node.display_name)
        const loaded = dataSourceLoaded(
          [...(node.output_data_sources ?? []), ...(node.input_data_sources ?? [])],
          importResult?.dataset_id,
        )
        setSourceLoaded(loaded)
        const preferred = node.out_quality_outputs?.find((c) => numericColumns.includes(c))
        if (preferred) setColumn(preferred)
      }}
    />
  </Form.Item>
)}
```

- [ ] **Step 4: 來源 Tag + 未載入提示**

`Space wrap` 結尾（現有 validation Tag 與內容之後、`</Space>` 前）插入來源 Tag：

```tsx
{sourceTag && (
  <Tag color="purple">製程節點：{sourceTag}</Tag>
)}
```

並在同 Card 內（`</Space>` 之後）插入未載入提示：

```tsx
{sourceTag && !sourceLoaded && importResult && (
  <Alert
    type="warning"
    showIcon
    message={t('spc.dataSourceNotLoaded')}
    style={{ marginTop: 8 }}
  />
)}
```

若 `importResult` 為 null（尚未載入任何資料）則顯示提示：

```tsx
{sourceTag && !importResult && (
  <Alert
    type="info"
    showIcon
    message={t('spc.loadDataFirst')}
    style={{ marginTop: 8 }}
  />
)}
```

- [ ] **Step 5: i18n 三語**

新增 keys（`spc.*` 三檔皆加）：

```
filterByNode                   Process node / 製程節點 / Nodo de proceso
filterByNodePlaceholder        Filter by node / 依節點篩選 / Filtrar por nodo
dataSourceNotLoaded            This node's data source is not loaded — import it in Data Import / 此節點資料源未載入，請到 Data Import 載入 / El origen de datos de este nodo no está cargado — impórtelo en Data Import
loadDataFirst                  No dataset loaded yet — import data in Data Import / 尚未載入資料集 — 請到 Data Import 載入 / Aún no hay datos — impórtelos en Data Import
```

- [ ] **Step 6: Verify**

Run: `npx tsc --noEmit` + `npm run build`
Run: 三語 JSON check（同上，對 spc 區塊）→ `ok`

- [ ] **Step 7: Commit**

```bash
git add src/features/spc/SPC.tsx src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(spc): process node filter + context consumption"
```

---

## Task 8: Monte-Carlo — 消費上下文 + 依節點篩選

**Files:**
- Modify: `src/features/monte-carlo/MonteCarlo.tsx`
- Modify: `src/i18n/en.json` / `zh-TW.json` / `es-MX.json`

- [ ] **Step 1: Import helper + state**

`MonteCarlo.tsx` import 區加：

```ts
import { consumeNodeContext, findNodeById, dataSourceLoaded } from '../../lib/processFlowContext'
import { getFlowGraph, type FlowNode } from '../../lib/engine'
```

元件內新增 state：

```ts
const [flowNodes, setFlowNodes] = useState<FlowNode[]>([])
const [selectedFlowNode, setSelectedFlowNode] = useState<FlowNode | null>(null)
const [sourceLoaded, setSourceLoaded] = useState(true)
const [sourceTag, setSourceTag] = useState<string | undefined>()
```

- [ ] **Step 2: 載入節點清單 + 消費跳轉上下文**

新增 mount effect（一次性）：

```ts
useEffect(() => {
  void getFlowGraph()
    .then((g) => setFlowNodes(g.nodes))
    .catch(() => {})

  const ctx = consumeNodeContext()
  if (!ctx) {
    setSourceTag(undefined)
    return
  }
  setSourceTag(ctx.displayName)
  void findNodeById(ctx.nodeId).then((node) => {
    if (!node) return
    setSelectedFlowNode(node)
    const loaded = dataSourceLoaded(ctx.dataSourceIds, importResult?.dataset_id)
    setSourceLoaded(loaded)
    const preferred = ctx.field && numericColumns.includes(ctx.field)
      ? ctx.field
      : node.out_quality_outputs?.find((c) => numericColumns.includes(c))
    if (preferred) setSpecOutput(preferred as never)
  })
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [])
```

> MC 目前沒有 numeric 欄位清單——`numericColumns` 需自行計算（若無 importResult 回空陣列）。於 component 內加：
> ```ts
> const numericColumns = importResult
>   ? Object.entries(importResult.stats.column_stats)
>       .filter(([, s]) => s.numeric)
>       .map(([name]) => name)
>   : []
> ```
> 且 MC 的輸出欄位 state 需確認名稱（見下列 Step 3 之輔助 setter）。

- [ ] **Step 3: 節點篩選下拉（工具列）**

`<Card title={t('monteCarlo.title')}>` 內、`Space wrap style={{ marginBottom: 12 }}` 開頭插入第一個 Form.Item（同 SPC Task 7 Step 3 結構，但 `onChange` 內 preferred 用 `out_quality_outputs?.find(...)`）。MC 目前選擇模型是 `selectedModel`，無直接「輸出欄位」下拉——**簡化**：若跳轉上下文提供 field，直接把它設為分析使用的 `spec.outputField`（若 store 提供 `setSpec`）。

在 API 呼叫處（`importResult` + `selectedModel` guard 內）確認 `spec?.outputField` 即刻起到作用；若 MC 不依賴 outputField，則跳轉時只顯示來源 Tag，不强行改欄位。

- [ ] **Step 4: 來源 Tag + 未載入提示**

同 SPC Task 7 Step 4 結構，插在 `Space wrap` 之後：

```tsx
{sourceTag && (
  <Tag color="purple">製程節點：{sourceTag}</Tag>
)}
{sourceTag && !sourceLoaded && importResult && (
  <Alert type="warning" showIcon message={t('monteCarlo.dataSourceNotLoaded')} style={{ marginTop: 8 }} />
)}
{sourceTag && !importResult && (
  <Alert type="info" showIcon message={t('monteCarlo.loadDataFirst')} style={{ marginTop: 8 }} />
)}
```

（`Tag`/`Alert` 若未 import 需補。）

- [ ] **Step 5: i18n 三語**

新增 keys（`monteCarlo.*`）：

```
filterByNode                   Process node / 製程節點 / Nodo de proceso
filterByNodePlaceholder        Filter by node / 依節點篩選 / Filtrar por nodo
dataSourceNotLoaded            This node's data source is not loaded — import it in Data Import / 此節點資料源未載入，請到 Data Import 載入 / El origen de datos de este nodo no está cargado — impórtelo en Data Import
loadDataFirst                  No dataset loaded yet — import data in Data Import / 尚未載入資料集 — 請到 Data Import 載入 / Aún no hay datos — impórtelos en Data Import
```

- [ ] **Step 6: Verify**

Run: `npx tsc --noEmit` + `npm run build`
Run: 三語 JSON check → `ok`

- [ ] **Step 7: Commit**

```bash
git add src/features/monte-carlo/MonteCarlo.tsx src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(monte-carlo): process node filter + context consumption"
```

---

## Task 9: Exploration — 消費上下文 + 依節點篩選

**Files:**
- Modify: `src/features/exploration/Exploration.tsx`
- Modify: `src/i18n/en.json` / `zh-TW.json` / `es-MX.json`

- [ ] **Step 1: Import helper + state**

`Exploration.tsx` import 區加：

```ts
import { consumeNodeContext, findNodeById, dataSourceLoaded } from '../../lib/processFlowContext'
import { getFlowGraph, type FlowNode } from '../../lib/engine'
```

元件內新增 state：

```ts
const [flowNodes, setFlowNodes] = useState<FlowNode[]>([])
const [selectedFlowNode, setSelectedFlowNode] = useState<FlowNode | null>(null)
const [sourceLoaded, setSourceLoaded] = useState(true)
const [sourceTag, setSourceTag] = useState<string | undefined>()
```

- [ ] **Step 2: 載入節點清單 + 消費跳轉上下文**

新增 mount effect：

```ts
useEffect(() => {
  void getFlowGraph()
    .then((g) => setFlowNodes(g.nodes))
    .catch(() => {})

  const ctx = consumeNodeContext()
  if (!ctx) {
    setSourceTag(undefined)
    return
  }
  setSourceTag(ctx.displayName)
  void findNodeById(ctx.nodeId).then((node) => {
    if (!node) return
    setSelectedFlowNode(node)
    const loaded = dataSourceLoaded(ctx.dataSourceIds, importResult?.dataset_id)
    setSourceLoaded(loaded)
    const preferred = ctx.field && numericColumns.includes(ctx.field)
      ? ctx.field
      : node.in_control_parameters?.find((c) => numericColumns.includes(c))
    if (preferred) {
      setColumn(preferred)
      setTrendColumn(preferred)
      setTsColumn(preferred)
    }
  })
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [])
```

- [ ] **Step 3: 節點篩選下拉（工具列）**

`return` 頂端 `<Card title={t('exploration.title')}>`（line 628）內、`<Tabs>` 之前插入：

```tsx
{flowNodes.length > 0 && (
  <Space style={{ marginBottom: 12 }}>
    <Form.Item label={t('exploration.filterByNode')} style={{ margin: 0 }}>
      <Select
        allowClear
        style={{ width: 220 }}
        placeholder={t('exploration.filterByNodePlaceholder')}
        value={selectedFlowNode?.process_node_id}
        options={flowNodes.map((n) => ({ value: n.process_node_id, label: n.display_name }))}
        onChange={(nodeId) => {
          const node = flowNodes.find((n) => n.process_node_id === nodeId)
          if (!node) {
            setSelectedFlowNode(null)
            setSourceTag(undefined)
            setSourceLoaded(true)
            return
          }
          setSelectedFlowNode(node)
          setSourceTag(node.display_name)
          const loaded = dataSourceLoaded(
            [...(node.input_data_sources ?? []), ...(node.output_data_sources ?? [])],
            importResult?.dataset_id,
          )
          setSourceLoaded(loaded)
          const preferred = node.in_control_parameters?.find((c) => numericColumns.includes(c))
          if (preferred) {
            setColumn(preferred)
            setTrendColumn(preferred)
            setTsColumn(preferred)
          }
        }}
      />
    </Form.Item>
    {sourceTag && (
      <Tag color="purple">製程節點:{sourceTag}</Tag>
    )}
  </Space>
)}
{sourceTag && !sourceLoaded && importResult && (
  <Alert
    type="warning"
    showIcon
    message={t('exploration.dataSourceNotLoaded')}
    style={{ marginBottom: 12 }}
  />
)}
{sourceTag && !importResult && (
  <Alert
    type="info"
    showIcon
    message={t('exploration.loadDataFirst')}
    style={{ marginBottom: 12 }}
  />
)}
```

（`Form`/`Select`/`Space`/`Tag`/`Alert` 需於 import 區確認已有——目前已有 `Select`、`Form`；`Space`/`Tag`/`Alert` 需補 import。）

- [ ] **Step 4: i18n 三語**

新增 keys（`exploration.*`）：

```
filterByNode                   Process node / 製程節點 / Nodo de proceso
filterByNodePlaceholder        Filter by node / 依節點篩選 / Filtrar por nodo
dataSourceNotLoaded            This node's data source is not loaded — import it in Data Import / 此節點資料源未載入，請到 Data Import 載入 / El origen de datos de este nodo no está cargado — impórtelo en Data Import
loadDataFirst                  No dataset loaded yet — import data in Data Import / 尚未載入資料集 — 請到 Data Import 載入 / Aún no hay datos — impórtelos en Data Import
```

- [ ] **Step 5: Verify**

Run: `npx tsc --noEmit` + `npm run build`
Run: 三語 JSON check → `ok`

- [ ] **Step 6: Commit**

```bash
git add src/features/exploration/Exploration.tsx src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(exploration): process node filter + context consumption"
```

---

## Task 10: 最終整合驗證 + 文件收尾 + push

**Files:**
- Modify: `PROGRESS.md`、`TASK.md`、`README.md`

- [ ] **Step 1: 全量驗證**

Run（依序、單一指令）：
```bash
cd engine && .venv/bin/python -m pytest tests/ -q
```
Expected: 288 passed, 1 skipped

```bash
cd .. && npx tsc --noEmit && npm run build
```
Expected: clean、build 成功

```bash
python3 -c "import json; 
a=json.load(open('src/i18n/en.json'));b=json.load(open('src/i18n/zh-TW.json'));c=json.load(open('src/i18n/es-MX.json'));
s=lambda d:{'processFlow':set(d.get('processFlow',{})),'spc':set(d.get('spc',{})),'monteCarlo':set(d.get('monteCarlo',{})),'exploration':set(d.get('exploration',{}))};
print('ok' if s(a)==s(b)==s(c) else 'MISMATCH')"
```
Expected: `ok`

- [ ] **Step 2: 更新 docs**

- `PROGRESS.md`：append「製程流程 × 下游分析整合（FAI）」進度段落。
- `TASK.md`：把本計劃各 Task 標記完成。
- `README.md`：若功能清單含製程流程 tab，補一句 FAI 整合說明。

- [ ] **Step 3: Final commit + push**

```bash
git add -A
git commit -m "docs: FAI 整合完成 + 3 階段驗證"
git push origin main
```

（排除 `engine/.coverage` 與未追蹤 icons——確保 `.gitignore` 或 `git add` 不含這些。）

---

## Self-Review

**Spec 涵蓋（對照設計文件）：**
- §5 Step 1 關聯鍵 → Task 1 (manifest) / Task 2 (IPC) / Task 3 (engine.ts) / Task 5 (§5.2 UI) ✅
- §6 Step 2 跳轉 → Task 4 (store/helper) / Task 5 Step 4 (跳轉按鈕) / Task 6 (App 訂閱) / Task 7-9 (下游消費) ✅
- §7 Step 3 依節點篩選 → Task 7-9 的節點篩選下拉 ✅
- §6.2 資料源處理（不自動載入）→ `dataSourceLoaded()` + 未載入/未載資料 Alert ✅
- §8 檔案變更清單 → 全數對應 ✅

**Placeholder 掃描：** 無 TBD/TODO。Task 8 有一處「需確認 MC 輸出欄位 state 名稱」的實作細節語氣——已改為具體說明：MC 跳轉只顯示來源 Tag 並（若可行）設 `spec.outputField`，不做强迫改欄位，避免侵入 MC 既有模型選擇邏輯。（執行時若發現 MC 有既有「輸出欄位」下拉，直接對應套用即可。）

**型別一致性：** `ProcessNodeContext`（nodeId/displayName/field/dataSourceIds）、`navigate(targetTab, context)`、`consume()`、`findNodeById`、`dataSourceLoaded` 於 Task 4 定義，Task 5-9 一致引用。`FlowGraph.association_keys` 於 Task 1(引擎)/3(型別)/5(UI)一致。`setAssociationKeys(keys) → { association_keys }` 各步一致。