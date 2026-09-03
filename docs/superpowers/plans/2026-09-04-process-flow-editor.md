# 製程流程圖完整編輯器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將製程流程圖擴充為完整圖形化編輯器（拖曳 / pan / zoom / minimap / port 連線 / 自動佈局 / 節點資料映射），並修復建立第二個節點時節點被擠出畫布且無法拉回的 bug。

**Architecture:** 維持自建 SVG（`ProcessFlow.tsx`），引入「世界座標 vs 視口（pan+zoom）」兩層轉換。位置與資料映射持久化到引擎 `ProcessNode`（新增 `x`/`y` 欄位，向後相容）。引擎已具備 `update_process_node` 任意欄位更新，後端 handler 免改，僅需擴充 dataclass 與 create 透傳。

**Tech Stack:** Tauri 2.0 + React 18 + TypeScript + Ant Design 5（前端）；Python 3.11（引擎）；零新依賴。

**規格來源：** `docs/superpowers/specs/2026-09-04-process-flow-editor-design.md`

---

## 檔案結構

- **引擎**
  - Modify: `engine/src/process_intelligence_engine/project/manifest.py` — `ProcessNode` 加 `x/y`；`create_process_node` 透傳 `x/y`。
  - Test: `engine/tests/test_manifest_nodes.py`（新增）
- **前端**
  - Modify: `src/lib/engine.ts` — `ProcessNode` 加 `x/y` 型別。
  - Modify: `src/features/process-flow/ProcessFlow.tsx` — 主要改寫（座標系、拖曳、pan/zoom、minimap、port 連線、自動佈局、資料映射面板）。
  - Modify: `src/i18n/en.json` / `zh-TW.json` / `es-MX.json` — 新增 `processFlow.*` keys。

---

## 前置：設定專案測試命令

- 引擎測試：`cd engine && .venv/bin/python -m pytest tests/ -q`
- 前端型別/建置：`cd <repo-root> && npx tsc --noEmit && npm run build`
- 手動執行：`npm run dev`（純網頁 vite；需重新匯入資料以套用引擎變更）

---

## Task 1: 引擎 ProcessNode 加 x/y 欄位（TDD）

**Files:**
- Modify: `engine/src/process_intelligence_engine/project/manifest.py:107-126`
- Create: `engine/tests/test_manifest_nodes.py`

- [ ] **Step 1: 寫 failing test**

```python
import tempfile, os
from process_intelligence_engine.project.manifest import ProjectEngine

def _engine():
    root = tempfile.mkdtemp()
    eng = ProjectEngine()
    eng.create_project(root, name="Test", operator="t")
    return eng

def test_node_has_x_y_defaults():
    eng = _engine()
    node = eng.create_process_node("A", "aoi")
    assert node["x"] == 0.0
    assert node["y"] == 0.0

def test_node_create_accepts_x_y():
    eng = _engine()
    node = eng.create_process_node("A", "aoi", x=100.0, y=-50.0)
    assert node["x"] == 100.0
    assert node["y"] == -50.0

def test_node_update_x_y_persists():
    eng = _engine()
    node = eng.create_process_node("A", "aoi")
    nid = node["process_node_id"]
    updated = eng.update_process_node(nid, {"x": 200.0, "y": 80.0})
    assert updated["x"] == 200.0
    assert updated["y"] == 80.0

def test_from_dict_old_data_without_x_y_defaults_zero():
    from process_intelligence_engine.project.manifest import ProcessNode
    n = ProcessNode.from_dict({"process_node_id": "1", "display_name": "A", "node_type": "aoi"})
    assert n.x == 0.0
    assert n.y == 0.0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && .venv/bin/python -m pytest tests/test_manifest_nodes.py -q`
Expected: FAIL（`AttributeError: 'dict' object has no attribute 'x'` 或 default 缺失）

- [ ] **Step 3: 實作最小修改**

在 `manifest.py::ProcessNode`（line 111 附近 `rework_policy` 之後）加入：

```python
    x: float = 0.0
    y: float = 0.0
```

並修改 `create_process_node`：

```python
    def create_process_node(self, display_name: str, node_type: str,
                            sequence_or_edges: list[dict] | None = None,
                            input_data_sources: list[str] | None = None,
                            rework_policy: str = "default",
                            x: float = 0.0, y: float = 0.0) -> dict:
        self._ensure_project()
        manifest = self._load()
        node = ProcessNode(
            process_node_id=str(uuid.uuid4()),
            display_name=display_name,
            node_type=node_type,
            sequence_or_edges=sequence_or_edges or [],
            input_data_sources=input_data_sources or [],
            rework_policy=rework_policy,
            x=x, y=y,
            active=True,
            created_at=self._now(),
        )
        manifest.process_nodes.append(node)
        self._save()
        return node.to_dict()
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && .venv/bin/python -m pytest tests/test_manifest_nodes.py -q`
Expected: 4 passed

- [ ] **Step 5: 跑完整引擎測試確認無回歸**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: 既有測試全綠（250+ passed）

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/project/manifest.py engine/tests/test_manifest_nodes.py
git commit -m "feat(project): add x/y position fields to ProcessNode (backward-compatible)"
```

---

## Task 2: 引擎節點資料映射欄位測試（規格 §11A）

引擎 `ProcessNode` 已有 `input_data_sources / output_data_sources / in_control_parameters / out_quality_outputs / machine_mapping`，但無測試。確認 `update_process_node` 可寫入。

- [ ] **Step 1: 於 `test_manifest_nodes.py` 補測試**

```python
def test_node_data_mapping_fields_update():
    eng = _engine()
    node = eng.create_process_node("A", "aoi")
    nid = node["process_node_id"]
    updated = eng.update_process_node(nid, {
        "input_data_sources": ["ds1", "ds2"],
        "output_data_sources": ["ds3"],
        "in_control_parameters": ["temp", "speed"],
        "out_quality_outputs": ["width", "height"],
        "machine_mapping": ["M1"],
    })
    assert updated["input_data_sources"] == ["ds1", "ds2"]
    assert updated["output_data_sources"] == ["ds3"]
    assert updated["in_control_parameters"] == ["temp", "speed"]
    assert updated["out_quality_outputs"] == ["width", "height"]
    assert updated["machine_mapping"] == ["M1"]
```

- [ ] **Step 2: 跑測試通過**

Run: `cd engine && .venv/bin/python -m pytest tests/test_manifest_nodes.py -q`
Expected: 5 passed（不需改實作，本就支援）

- [ ] **Step 3: Commit**

```bash
git add engine/tests/test_manifest_nodes.py
git commit -m "test(project): node data mapping fields (input/output/params/quality/machine)"
```

---

## Task 3: 前端 ProcessNode 型別加 x/y

**Files:**
- Modify: `src/lib/engine.ts:1137-1150`

- [ ] **Step 1: 在 `interface ProcessNode` 的 `node_type` 後加 x/y**

```ts
export interface ProcessNode {
  process_node_id: string
  display_name: string
  node_type: string
  x?: number
  y?: number
  sequence_or_edges: Array<{ from: string; to: string; condition?: string }>
  input_data_sources: string[]
  output_data_sources: string[]
  in_control_parameters: string[]
  out_quality_outputs: string[]
  machine_mapping: string[]
  rework_policy: 'default' | 'rework' | 'scrap' | 'hold'
  active: boolean
  created_at: string
}
```

- [ ] **Step 2: typecheck**

Run: `npx tsc --noEmit`
Expected: 無錯誤

- [ ] **Step 3: Commit**

```bash
git add src/lib/engine.ts
git commit -m "feat(flow): add x/y to ProcessNode type"
```

---

## Task 4: 前端原理圖核心 — 世界座標 + 視口(pan/zoom) + 修復 bug

**Files:**
- Modify: `src/features/process-flow/ProcessFlow.tsx`（主要改寫）

**說明：** 將渲染移至 `<g transform={translate(panX,panY) scale(zoom)}>`。節點座標一律用「世界座標」；互動時用螢幕點做逆變換。初始載入後 `fitView()` 讓所有節點落在可見區（含負座標 → 用 offset 平移，不重排節點），修復「負座標節點被裁出畫布」。

- [ ] **Step 1: 新增 state 與工具函式（在 component 頂部）**

在 `export default function ProcessFlow()` 內、`const selectedNode = ...` 附近加入：

```ts
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)
  const [viewportSize, setViewportSize] = useState({ w: 900, h: 500 })

  // reverse-transform: screen -> world
  const toWorld = (sx: number, sy: number) => ({
    x: (sx - pan.x) / zoom,
    y: (sy - pan.y) / zoom,
  })

  const worldBounds = useMemo(() => {
    const pts = graph.nodes.map(n => ({
      x: n.x ?? 0, y: n.y ?? 0,
      w: NODE_WIDTH, h: NODE_HEIGHT,
    }))
    if (pts.length === 0) return { minX: 0, minY: 0, maxX: 600, maxY: 300 }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const p of pts) {
      minX = Math.min(minX, p.x); minY = Math.min(minY, p.y)
      maxX = Math.max(maxX, p.x + p.w); maxY = Math.max(maxY, p.y + p.h)
    }
    return { minX, minY, maxX, maxY }
  }, [graph.nodes])

  const fitView = () => {
    const pad = 40
    const { minX, minY, maxX, maxY } = worldBounds
    const bw = maxX - minX || 1, bh = maxY - minY || 1
    const z = Math.min(
      (viewportSize.w - 2 * pad) / bw,
      (viewportSize.h - 2 * pad) / bh,
      1.5,
    )
    setZoom(Math.max(0.5, z))
    setPan({
      x: (viewportSize.w - bw * z) / 2 - minX * z,
      y: (viewportSize.h - bh * z) / 2 - minY * z,
    })
  }
```

- [ ] **Step 2: 測量容器尺寸（useEffect on mount + resize）**

在既有 `useEffect(() => { void loadData() }, [])` 之後加入：

```ts
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const measure = () => setViewportSize({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
```

（`ResizeObserver` 可在 `window` 型別中直接使用；若 TS 無定義，於檔案頂部加 `/// <reference lib="dom" />` 或宣告：`declare class ResizeObserver {...}`。建議直接使用瀏覽器內建型別，React 18 專案通常已有。）

- [ ] **Step 3: 載入完成後 fitView**

在 `loadData` 的 `setGraph(g)` 之後呼叫 `fitView()`：

```ts
      const [g, v] = await Promise.all([getFlowGraph(), validateFlowGraph()])
      setGraph(g)
      setValidation(v)
      fitView()
```

（`fitView` 在 `graph.nodes` 更新前讀到舊 bounds 一次；為確保拿到新 nodes，可改用 `useEffect(() => { fitView() }, [graph.nodes.length])` 並僅在初次載入時觸發一次，避免每次變動都重排視口。實作時用一個 `didInitialFit` ref 旗標。）

```ts
  const didInitialFit = useRef(false)
  useEffect(() => {
    if (!didInitialFit.current && graph.nodes.length > 0) {
      didInitialFit.current = true
      fitView()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph.nodes.length])
```

並**移除** Step 3 中 loadData 內的 `fitView()`，避免重複。

- [ ] **Step 4: 覆寫 SVG 渲染為 viewport 包裝**

將 `<svg width={...} height={...}>` 改為：

```tsx
            <div ref={containerRef} style={{ width: '100%', height: 500, overflow: 'hidden' }}>
            <svg
              width={viewportSize.w}
              height={viewportSize.h}
              style={{ background: '#FAFAFA', display: 'block', touchAction: 'none' }}
              onPointerDown={handleBackgroundPointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onWheel={handleWheel}
            >
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                  <path d="M0,0 L8,3 L0,6 Z" fill="#8c8c8c" />
                </marker>
              </defs>
              <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
                {/* 原有 edges + nodes 內容照舊，但座標都是世界座標 */}
              </g>
              {/* minimap 疊層（Task 6） */}
            </svg>
            </div>
```

**重要：** 原有 `nodeCenters` / `layout` / `computeLayout` 依賴——本 Task 起**不再使用 `computeLayout` 自動計算座標**，改為讀每節點的 `n.x / n.y`（世界座標）。因此：
- 移除 `const { layout, maxX, maxY } = computeLayout(...)` 這行與 `computeLayout` 的使用（保留函式供 Task 8 自動佈局呼叫）。
- `nodeCenters` 改為由 `graph.nodes` 產生：`center.x = (n.x ?? 0) + NODE_WIDTH/2`、`center.y = (n.y ?? 0) + NODE_HEIGHT/2`。
- 邊的繪製：`from = nodeCenters.get(e.from)`、`to = nodeCenters.get(e.to)`，不變。
- 節點渲染：`pos = { x: node.x ?? 0, y: node.y ?? 0 }`（取代 `layout.get(...)`）。

- [ ] **Step 5: 新增互動 handler（平移用，節點拖曳/port 連線在後續 Task）**

```ts
  const panDrag = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null)

  const handleBackgroundPointerDown = (e: React.PointerEvent) => {
    const t = e.target as Element
    if (t.closest('[data-node]') || t.closest('[data-port]')) return  // 節點/port 優先
    panDrag.current = { sx: e.clientX, sy: e.clientY, px: pan.x, py: pan.y }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (panDrag.current) {
      const dx = e.clientX - panDrag.current.sx
      const dy = e.clientY - panDrag.current.sy
      setPan({ x: panDrag.current.px + dx, y: panDrag.current.py + dy })
    }
  }

  const handlePointerUp = () => { panDrag.current = null }

  const handleWheel = (e: React.WheelEvent) => {
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
    const sx = e.clientX - rect.left
    const sy = e.clientY - rect.top
    const factor = e.deltaY < 0 ? 1.1 : 0.9
    const newZoom = Math.min(2, Math.max(0.5, zoom * factor))
    // 以游標為縮放錨點
    setPan({
      x: sx - (sx - pan.x) * (newZoom / zoom),
      y: sy - (sy - pan.y) * (newZoom / zoom),
    })
    setZoom(newZoom)
  }
```

- [ ] **Step 6: 節點/port 元素加 data 屬性**

節點 `<g>` 加 `data-node={node.process_node_id}`、`data-node-id` 供判別；port `circle` 加 `data-port`（此階段先避免背景平移作用其上，port 連線 Task 7 實作）。

- [ ] **Step 7: 驗證 bug 已修復（手動）**

Run: `npm run dev`
手動驗證：清空後新增兩個未連線節點 → 兩者都應顯示在畫布內（fitView 平移補償負座標），不會有節點被裁出畫布或無法拉回。背景拖曳可平移、滾輪可縮放。

- [ ] **Step 8: typecheck + build**

Run: `npx tsc --noEmit && npm run build`
Expected: 乾淨

- [ ] **Step 9: Commit**

```bash
git add src/features/process-flow/ProcessFlow.tsx
git commit -m "feat(flow): world/viewport transform with pan/zoom + fitView; fix nodes pushed off-canvas"
```

---

## Task 5: 節點拖曳 + 位置持久化

**Files:**
- Modify: `src/features/process-flow/ProcessFlow.tsx`

- [ ] **Step 1: 新增拖曳 state 與 handler**

在 `panDrag` 附近加入：

```ts
  const [dragging, setDragging] = useState<{ id: string; startX: number; startY: number; origX: number; origY: number } | null>(null)

  const startNodeDrag = (e: React.PointerEvent, node: FlowNode) => {
    e.stopPropagation()
    setDragging({
      id: node.process_node_id,
      startX: e.clientX, startY: e.clientY,
      origX: node.x ?? 0, origY: node.y ?? 0,
    })
    ;(e.target as Element).closest('g')?.setPointerCapture?.(e.pointerId)
  }
```

**座標來源**：為取得 SVG 螢幕位置，用一個穩定 ref：

```ts
  const svgRef = useRef<SVGSVGElement>(null)
  const svgRectLeft = () => svgRef.current?.getBoundingClientRect().left ?? 0
  const svgRectTop = () => svgRef.current?.getBoundingClientRect().top ?? 0
```

將 `<svg ...>` 加上 `ref={svgRef}`。

- [ ] **Step 2: 於 handlePointerMove / handlePointerUp 加入節點拖曳分支**

```ts
  const handlePointerMove = (e: React.PointerEvent) => {
    if (dragging) {
      const dx = (e.clientX - dragging.startX) / zoom
      const dy = (e.clientY - dragging.startY) / zoom
      setGraph(prev => ({
        ...prev,
        nodes: prev.nodes.map(n =>
          n.process_node_id === dragging.id
            ? { ...n, x: Math.round(dragging.origX + dx), y: Math.round(dragging.origY + dy) }
            : n,
        ),
      }))
      return
    }
    if (panDrag.current) { /* 原有平移 */ }
  }

  const handlePointerUp = (e: React.PointerEvent) => {
    if (dragging) {
      void persistNodePosition()
      setDragging(null)
      panDrag.current = null
      return
    }
    panDrag.current = null
  }

  const persistNodePosition = async () => {
    if (!dragging) return
    const node = graph.nodes.find(n => n.process_node_id === dragging.id)
    if (!node) return
    const original = { x: dragging.origX, y: dragging.origY }
    try {
      await updateProcessNode(node.process_node_id, { x: node.x, y: node.y })
    } catch {
      // rollback 到原位置
      setGraph(prev => ({
        ...prev,
        nodes: prev.nodes.map(n =>
          n.process_node_id === node.process_node_id ? { ...n, ...original } : n,
        ),
      }))
      messageApi.error(t('processFlow.saveError'))
    }
  }
```

- [ ] **Step 3: 節點 `<g>` 綁定拖曳起始**

在節點 `<g onPointerDown>`：

```tsx
                  <g
                    key={node.process_node_id}
                    data-node={node.process_node_id}
                    onClick={() => { if (!dragging) setSelectedNodeId(node.process_node_id) }}
                    onPointerDown={(e) => startNodeDrag(e, node)}
                    style={{ cursor: 'grab' }}
                  >
```

（`data-node` 已在 Task 4 加入。）

- [ ] **Step 4: 手動驗證**

Run: `npm run dev`
驗證：拖曳節點即時移動；放開後位置持久化（重新載入 `loadData` 仍保持）；拖曳失敗（可模擬）回滾到原位。

- [ ] **Step 5: typecheck + build + commit**

```bash
npx tsc --noEmit && npm run build
git add src/features/process-flow/ProcessFlow.tsx
git commit -m "feat(flow): draggable nodes with persistable position (rollback on failure)"
```

---

## Task 6: 迷你地圖 + 縮放按鈕工具列

**Files:**
- Modify: `src/features/process-flow/ProcessFlow.tsx`

- [ ] **Step 1: 工具列新增縮放/自動佈局按鈕**

在既有 `refresh` 按鈕後加入：

```tsx
          <Button.Group size="small">
            <Button icon={<ZoomInOutlined />} onClick={() => setZoom(z => Math.min(2, z * 1.25))} />
            <Button onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</Button>
            <Button icon={<ZoomOutOutlined />} onClick={() => setZoom(z => Math.max(0.5, z * 0.8))} />
            <Button icon={<FullscreenOutlined />} onClick={() => fitView()} />
          </Button.Group>
          <Button icon={<ApartmentOutlined />} onClick={() => { void handleAutoLayout() }}>
            {t('processFlow.autoLayout')}
          </Button>
```

import 加入 `ZoomInOutlined, ZoomOutOutlined, FullscreenOutlined, ApartmentOutlined`。

- [ ] **Step 2: 實作 handleAutoLayout（自動佈局）+ 重算後 fit**

```ts
  const handleAutoLayout = async () => {
    try {
      const { layout: newLayout } = computeLayout(graph.nodes, graph.edges)
      const updated = graph.nodes.map(n => {
        const p = newLayout.get(n.process_node_id)
        return p ? { ...n, x: p.x, y: p.y } : n
      })
      setGraph(prev => ({ ...prev, nodes: updated }))
      for (const u of updated) {
        await updateProcessNode(u.process_node_id, { x: u.x, y: u.y })
      }
      // 依新世界座標 fitView
      const padding = 40
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
      for (const u of updated) {
        minX = Math.min(minX, u.x ?? 0); minY = Math.min(minY, u.y ?? 0)
        maxX = Math.max(maxX, (u.x ?? 0) + NODE_WIDTH); maxY = Math.max(maxY, (u.y ?? 0) + NODE_HEIGHT)
      }
      const bw = (maxX - minX) || 1, bh = (maxY - minY) || 1
      const z = Math.min((viewportSize.w - 2 * padding) / bw, (viewportSize.h - 2 * padding) / bh, 1.5)
      setZoom(Math.max(0.5, z))
      setPan({ x: (viewportSize.w - bw * z) / 2 - minX * z, y: (viewportSize.h - bh * z) / 2 - minY * z })
      messageApi.success(t('processFlow.autoLayoutDone'))
    } catch {
      messageApi.error(t('processFlow.autoLayoutError'))
    }
  }
```

**注意：** `computeLayout` **在 Task 4 已改為不使用**。此處為了自動佈局仍需要它。`fx` 因此需確保 `computeLayout` 仍在檔內（保留原函式即可，勿刪除）。你可直接保留原始 `computeLayout`。

- [ ] **Step 3: 迷你地圖疊層（放 `</svg>` 之前、SVG 子元素末尾）**

```tsx
              <g transform={`translate(${viewportSize.w - 150}, ${viewportSize.h - 110})`} opacity={0.95}>
                <rect x={0} y={0} width={140} height={100} rx={4} fill="#ffffff" stroke="#ddd" />
                <g transform={`translate(${8},${8}) scale(${miniScale})`}>
                  {graph.nodes.map(n => {
                    const mx = 124 / (worldBounds.maxX - worldBounds.minX || 1)
                    const my = 84 / (worldBounds.maxY - worldBounds.minY || 1)
                    return (
                      <rect key={n.process_node_id}
                        x={(n.x ?? 0) - worldBounds.minX} y={(n.y ?? 0) - worldBounds.minY}
                        width={NODE_WIDTH * mx} height={NODE_HEIGHT * my}
                        fill={NODE_COLORS[n.node_type] || NODE_COLORS.default} rx={1} />
                    )
                  })}
                </g>
              </g>
```

`miniScale` 為縮影比例（min(bw, bh) 對映 124x84）。為簡潔，改以單位縮放加載：直接對最大包圍框計算單一 `miniScale`：

```ts
  const miniScale = Math.min(
    124 / (worldBounds.maxX - worldBounds.minX || 1),
    84 / (worldBounds.maxY - worldBounds.minY || 1),
  )
```

（minimap 的縮影用 `worldBounds.minX/minY` 平移 + `miniScale` 縮放，節點矩形用 `width={NODE_WIDTH*miniScale}` 等高。依此調整 Step 3 的示意，確保座標正確。）

**作用：** 顯示全圖縮影與目前視野比例，快速掌握整體結構。

- [ ] **Step 4: 手動驗證 + typecheck + build + commit**

```bash
npm run dev   # 手動驗證 zoom 按鈕 / 自動佈局 / minimap
npx tsc --noEmit && npm run build
git add src/features/process-flow/ProcessFlow.tsx
git commit -m "feat(flow): zoom controls, auto-layout button, minimap overlay"
```

---

## Task 7: Port 拖曳建立連線

**Files:**
- Modify: `src/features/process-flow/ProcessFlow.tsx`

- [ ] **Step 1: 新增連線草稿 state 與 handler**

```ts
  const [connectDraft, setConnectDraft] = useState<{ fromId: string; sx: number; sy: number } | null>(null)
  const [connectCursor, setConnectCursor] = useState<{ x: number; y: number } | null>(null)
  const [hoverTarget, setHoverTarget] = useState<{ id: string; port: 'in' | 'out' } | null>(null)

  const startConnect = (e: React.PointerEvent, fromId: string) => {
    e.stopPropagation()
    const w = toWorld(e.clientX - svgRectLeft(), e.clientY - svgRectTop())
    setConnectDraft({ fromId, sx: w.x, sy: w.y })
    setConnectCursor({ x: w.x, y: w.y })
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
  }
```

- [ ] **Step 2: 於 move/up 加入連線邏輯**

在 `handlePointerMove` 開頭（若無 dragging）加入：

```ts
    if (connectDraft) {
      const w = toWorld(e.clientX - svgRectLeft(), e.clientY - svgRectTop())
      setConnectCursor({ x: w.x, y: w.y })
      // 偵測 hover 目標 port
      const el = document.elementFromPoint(e.clientX, e.clientY) as Element | null
      const portEl = el?.closest?.('[data-port]') as HTMLElement | null
      if (portEl && portEl.dataset.nodeId && portEl.dataset.nodeId !== connectDraft.fromId) {
        setHoverTarget({ id: portEl.dataset.nodeId, port: portEl.dataset.port as 'in' | 'out' })
      } else {
        setHoverTarget(null)
      }
      return
    }
```

`handlePointerUp` 開頭加入：

```ts
    if (connectDraft) {
      if (hoverTarget && hoverTarget.id !== connectDraft.fromId) {
        void handleConnect(connectDraft.fromId, hoverTarget.id)
      }
      setConnectDraft(null); setConnectCursor(null); setHoverTarget(null)
      return
    }
```

- [ ] **Step 3: 渲染臨時連線草稿（在 edges 之後）**

```tsx
              {connectDraft && connectCursor && (() => {
                const from = nodeCenters.get(connectDraft.fromId)
                if (!from) return null
                return (
                  <path d={svga(from.x + NODE_WIDTH/2, from.y, connectCursor.x, connectCursor.y)}
                    fill="none" stroke="#1677ff" strokeWidth={2} strokeDasharray="4 2"
                    markerEnd="url(#arrow)" opacity={0.7} />
                )
              })()}
```

- [ ] **Step 4: port 圓點加 data 屬性與 pointer handler**

左/右 port `circle`：

```tsx
                    <circle data-port data-node-id={node.process_node_id} data-port="out"
                      cx={pos.x + NODE_WIDTH} cy={pos.y + NODE_HEIGHT / 2} r={5}
                      fill={portColor} stroke="#fff" strokeWidth={1.5}
                      onPointerDown={(e) => startConnect(e, node.process_node_id)}
                      onPointerUp={(e) => e.stopPropagation()}
                      style={{ cursor: 'crosshair' }}
                    />
                    <circle data-port data-node-id={node.process_node_id} data-port="in"
                      cx={pos.x} cy={pos.y + NODE_HEIGHT / 2} r={5}
                      fill={portColor} stroke="#fff" strokeWidth={1.5}
                      onPointerDown={(e) => startConnect(e, node.process_node_id)}
                      onPointerUp={(e) => e.stopPropagation()}
                      style={{ cursor: 'crosshair' }}
                    />
```

**注意：** 用 `data-port="out"`/`"in"` 標記。目標偵測以對端 port 為主；為簡化，連到任一對端 port 皆建立邊 `from→to`（方向由源 port 決定），`handleConnect` 已處理去重。

- [ ] **Step 5: 手動驗證 + typecheck + build + commit**

```bash
npm run dev
# 從節點 A 右 port 拖到節點 B → 出現邊；放開空白 → 取消
npx tsc --noEmit && npm run build
git add src/features/process-flow/ProcessFlow.tsx
git commit -m "feat(flow): drag from port to connect nodes"
```

---

## Task 8: 節點資料映射面板（規格 §11A）

**Files:**
- Modify: `src/features/process-flow/ProcessFlow.tsx`

- [ ] **Step 1: 載入已註冊資料集以供選擇**

```ts
  const [datasets, setDatasets] = useState<Array<{ value: string; label: string }>>([])
  useEffect(() => {
    void getDatasets().then(regs => setDatasets(
      regs.map(r => ({ value: r.dataset_id, label: r.source_file || r.dataset_id })),
    )).catch(() => {})
  }, [])
```

import 加入 `getDatasets` 與 `type DatasetRegistration`（engine.ts）。

- [ ] **Step 2: 屬性面板新增資料映射區（在「Connect to」區塊之前）**

```tsx
              <div style={{ marginTop: 12, fontSize: 12, fontWeight: 600 }}>
                {t('processFlow.dataMapping')}
              </div>
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.inputDataSources')}</span>
              <Select mode="multiple" allowClear style={{ width: '100%' }}
                placeholder={t('processFlow.selectDataSources')}
                options={datasets}
                value={selectedNode.input_data_sources || []}
                onChange={vals => void saveMapping('input_data_sources', vals)}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.outputDataSources')}</span>
              <Select mode="multiple" allowClear style={{ width: '100%' }}
                placeholder={t('processFlow.selectDataSources')}
                options={datasets}
                value={selectedNode.output_data_sources || []}
                onChange={vals => void saveMapping('output_data_sources', vals)}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.controlParameters')}</span>
              <Select mode="tags" style={{ width: '100%' }}
                placeholder={t('processFlow.typeOrSelect')}
                value={selectedNode.in_control_parameters || []}
                onChange={vals => void saveMapping('in_control_parameters', vals)}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.qualityOutputs')}</span>
              <Select mode="tags" style={{ width: '100%' }}
                placeholder={t('processFlow.typeOrSelect')}
                value={selectedNode.out_quality_outputs || []}
                onChange={vals => void saveMapping('out_quality_outputs', vals)}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.machineMapping')}</span>
              <Select mode="tags" style={{ width: '100%' }}
                placeholder={t('processFlow.typeOrSelect')}
                value={selectedNode.machine_mapping || []}
                onChange={vals => void saveMapping('machine_mapping', vals)}
              />
```

- [ ] **Step 3: 實作 saveMapping**

```ts
  const saveMapping = async (field: string, vals: string[]) => {
    if (!selectedNode) return
    try {
      await updateProcessNode(selectedNode.process_node_id, { [field]: vals } as Record<string, unknown>)
      setGraph(prev => ({
        ...prev,
        nodes: prev.nodes.map(n =>
          n.process_node_id === selectedNode.process_node_id ? { ...n, [field]: vals } : n,
        ),
      }))
    } catch {
      messageApi.error(t('processFlow.saveError'))
    }
  }
```

- [ ] **Step 4: 手動驗證 + typecheck + build + commit**

```bash
npm run dev   # 選節點 → 設定資料映射 → 重載確認保持
npx tsc --noEmit && npm run build
git add src/features/process-flow/ProcessFlow.tsx
git commit -m "feat(flow): node data mapping panel (input/output sources, control params, quality outputs, machine)"
```

---

## Task 9: i18n 三語 keys

**Files:**
- Modify: `src/i18n/en.json`, `src/i18n/zh-TW.json`, `src/i18n/es-MX.json`

- [ ] **Step 1: en.json `processFlow` 新增**

在 `processFlow` 物件內加入（保留既有 keys）：

```json
{
  "autoLayout": "Auto Layout",
  "autoLayoutDone": "Layout applied",
  "autoLayoutError": "Failed to apply layout",
  "saveError": "Failed to save changes",
  "dataMapping": "Data Mapping",
  "inputDataSources": "Input Data Sources",
  "outputDataSources": "Output Data Sources",
  "selectDataSources": "Select data sources",
  "controlParameters": "Control Parameters",
  "qualityOutputs": "Quality Outputs",
  "machineMapping": "Machine Mapping",
  "typeOrSelect": "Type or select",
  "zoomIn": "Zoom in",
  "zoomOut": "Zoom out",
  "zoomReset": "Reset zoom",
  "zoomFit": "Fit to view"
}
```

- [ ] **Step 2: zh-TW.json `processFlow` 新增**

```json
{
  "autoLayout": "自動排程",
  "autoLayoutDone": "已套用排版",
  "autoLayoutError": "排版失敗",
  "saveError": "儲存失敗",
  "dataMapping": "資料映射",
  "inputDataSources": "輸入資料來源",
  "outputDataSources": "輸出資料來源",
  "selectDataSources": "選擇資料來源",
  "controlParameters": "控制參數",
  "qualityOutputs": "品質輸出",
  "machineMapping": "機台對應",
  "typeOrSelect": "輸入或選擇",
  "zoomIn": "放大",
  "zoomOut": "縮小",
  "zoomReset": "重設縮放",
  "zoomFit": "適合視窗"
}
```

- [ ] **Step 3: es-MX.json `processFlow` 新增**

```json
{
  "autoLayout": "Auto distribución",
  "autoLayoutDone": "Distribución aplicada",
  "autoLayoutError": "No se pudo aplicar la distribución",
  "saveError": "No se pudo guardar",
  "dataMapping": "Asignación de datos",
  "inputDataSources": "Orígenes de datos de entrada",
  "outputDataSources": "Orígenes de datos de salida",
  "selectDataSources": "Seleccionar orígenes de datos",
  "controlParameters": "Parámetros de control",
  "qualityOutputs": "Salidas de calidad",
  "machineMapping": "Asignación de máquina",
  "typeOrSelect": "Escribir o seleccionar",
  "zoomIn": "Acercar",
  "zoomOut": "Alejar",
  "zoomReset": "Restablecer zoom",
  "zoomFit": "Ajustar a la vista"
}
```

- [ ] **Step 4: 驗證 + commit**

Run: `npx tsc --noEmit && npm run build`
Expected: 乾淨（i18n JSON 不需 TS 型別）

```bash
git add src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "i18n(flow): auto-layout, zoom, and data-mapping keys (en/zh-TW/es-MX)"
```

---

## Task 10: 最終整合驗證

**Files:** 無（僅驗證）

- [ ] **Step 1: 引擎完整測試**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: 全部通過（250+ passed, 1 skipped）

- [ ] **Step 2: 前端型別 + build**

Run: `cd <repo-root> && npx tsc --noEmit && npm run build`
Expected: 乾淨

- [ ] **Step 3: 手動 E2E（npm run dev，需先重新匯入資料以套用引擎欄位）**

依序驗證清單：
1. 新增兩個未連線節點 → 兩者皆在畫布內（bug 修復生效）。
2. 拖曳節點 → 放開 → 重新載入（切 Tab 回流程圖）位置保持。
3. 背景拖曳平移；滾輪縮放；+ / − / % / 適合視窗按鈕。
4. minimap 顯示全圖縮影。
5. 從節點 A port 拖到節點 B → 出現邊；放開空白 → 取消。
6. 自動排程 → 層次分佈重排並保持。
7. 選節點 → 設定輸入/輸出資料來源、控制參數、品質輸出、機台 → 重載保持。
8. 環狀/孤立節點警示意圖仍正常（既有 validateFlowGraph）。

- [ ] **Step 4: 更新 PROGRESS.md + TASK.md**

依 `PROGRESS.md` 結尾追加本功能完成記錄；TASK.md 加 Phase 11k。

- [ ] **Step 5: Commit**

```bash
git add PROGRESS.md TASK.md
git commit -m "docs: record process flow editor completion"
```

---

## 附錄：需要的前端新增 import（彙總到 ProcessFlow.tsx）

```ts
import { useEffect, useMemo, useRef, useState } from 'react'
import { ZoomInOutlined, ZoomOutOutlined, FullscreenOutlined, ApartmentOutlined } from '@ant-design/icons'
import { getDatasets } from '../../lib/engine'
```

（其餘 `getFlowGraph / validateFlowGraph / createProcessNode / updateProcessNode / deleteProcessNode / FlowGraph / FlowNode / FlowEdge / FlowValidation` 已在既有 import。）
