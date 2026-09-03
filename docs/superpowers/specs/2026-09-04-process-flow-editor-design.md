# 製程流程圖完整編輯器 — 設計文件

日期：2026-09-04
狀態：審閱中

## 1. 背景與問題

`src/features/process-flow/ProcessFlow.tsx` 的流程圖顯示區有一個 bug：

**建立第二個節點時，第一個節點被擠到畫布外，且無法拉回。**

### 1.1 根因（已完成調查）

`computeLayout()` 以 `(0,0)` 為中心產生節點座標：

```python
startY = -(count - 1) * V_GAP / 2   # layer 內第 0 個節點的 y
```

- 單一節點（count=1）：`startY = 0`，節點居中，正常顯示。
- 兩個孤立節點（count=2）：同一 layer，`startY = -40`，節點落在 `y=-40` 與 `y=+40`。SVG viewport 從 `(0,0)` 開始繪製，`y<0` 的節點（上半部）被裁切到畫布之外。
- 此外 **完全沒有拖曳／平移能力**：節點座標全由 `computeLayout` 決定，使用者沒有任何操作可改變節點位置，因此「拉不回來」。

### 1.2 觸發情境

- 新增一個**未連線**的孤立節點（兩個節點都屬 layer 0）→ 負 y 座標 → 出畫布。
- 連線節點較不易觸發（新增節點接到既有節點時會落到新的 layer，x=200…），但仍可能因多節點垂直分布超過單一 viewport 而看不全。

---

## 2. 目標

把流程圖擴充為**完整的圖形化編輯器**，並修復座標出畫布的根本問題。採「手動優先 + 一鍵自動佈局」模式。

## 3. 範圍

| 能力 | 說明 |
|------|------|
| A. Bug 修復 | 修正負座標節點被裁到畫布外 |
| B. 節點拖曳 + 位置持久化 | 節點可拖曳，位置存引擎，重載不變 |
| C. 畫布平移 / 縮放 + 迷你地圖 | pan / zoom / minimap |
| D. Port 拖曳連線 | 從 port 圓點拖到目標 port 建立連線 |
| E. 一鍵自動佈局 | 拓扑分層重排，覆蓋手動位置 |

**非目標（YAGNI）：** 不引入 React Flow 套件（維持自建 SVG、零新依賴）；不做節點群組折疊／多選框選；不做 undo/redo 歷史。

---

## 4. 技術方案

維持自建 SVG（`ProcessFlow.tsx`），以增量方式加入互動能力。**零新依賴**。

### 4.1 Core：座標系與視口（fix A + C 的基礎）

引入「世界座標（world）」與「畫布偏移 + 縮放（viewport）」兩層：

```
<svg>  ── viewport 尺寸（容器大小，CSS 100%）
  <g transform={`translate(${panX} ${panY}) scale(${zoom})`}>  ── 世界座標
    節點 / 邊 / port（原有 NODE_WIDTH/NODE_HEIGHT）
  </g>
  minimap（固定角落，獨立於 transform）
</svg>
```

- `zoom`：初始 `1`，範圍 `0.5 ~ 2`。
- `panX/panY`：畫布偏移。
- 所有節點/邊使用**世界座標**繪製；互動（滑鼠座標）需做「螢幕→世界」逆變換。

**初始 fit**：載入 + 手動節點後，計算所有節點的世界座標包圍框，設定 `panX/panY` 使其在 viewport 內顯示（含邊距）。若世界座標有負值，也一律先加偏移將「最小座標」放到邊距位置——這是修復負座標出畫布的關鍵（adapt 而非強制重排，保留手動位置）。

### 4.2 節點拖曳 + 持久化（B）

- 節點 `onPointerDown` 開始拖曳時：記錄起點、節點的原座標、正在拖曳的節點 id。
- `onPointerMove`：更新該節點的世界座標（`x = origX + (dx/zoom)`）。
- `onPointerUp`：停止拖曳；**若位置有變**，呼叫 `updateProcessNode(nodeId, { x, y })` 持久化到引擎；失敗則 rollback 到原座標並顯示錯誤訊息。
- identifier：使用 `pointerId` 與 `setPointerCapture` 避免與其他元素（pan）衝突。

### 4.3 位置持久化（引擎，B）

`engine/src/process_intelligence_engine/project/manifest.py::ProcessNode` 加入：

```python
x: float = 0.0
y: float = 0.0
```

- `from_dict` 已用 `__dataclass_fields__` 過濾 → 舊 manifest 無 x/y 時自動用 default `0.0`，**向後相容**。
- `update_process_node` 已支援 `hasattr(n, k)` 任意欄位更新 → 前端傳 `{x, y}` 即可，**後端 update handler 免改**。
- `create_process_node` 可選擇性透傳初始 x/y（非必要，前端建立後可再更新）。

`src/lib/engine.ts::ProcessNode` 加入 `x/y` 型別。

### 4.4 畫布平移 / 縮放 + 迷你地圖（C）

- **平移**：SVG 背景（非節點/port 上）`onPointerDown` → 拖曳更新 `panX/panY`。
- **縮放**：`onWheel`，以游標世界座標為縮放錨點：
  ```
  newZoom = clamp(zoom * (deltaY<0 ? 1.1 : 0.9), 0.5, 2)
  pan = cursor - (cursor - pan) * (newZoom/zoom)
  ```
- 工具列按鈕：`+ / − / 重置 100%` + `適合視窗（fit）`。
- **迷你地圖**：`<svg>` 右下角疊層，`pointer-events` 容許；繪製所有節點縮影（縮小比例 = minimap 寬 / 世界包圍框寬），紅框表示目前 viewport 可見範圍；點擊/拖曳紅框中心 → 平移跳轉。

### 4.5 Port 拖曳連線（D）

- port 圓點 `onPointerDown` 開始連線草稿：記錄 `fromId`，建立一條「臨時邊」，終點跟隨滑鼠（世界座標）。
- `onPointerUp`：若落在某節點的左/右 port 熱點區 → 呼叫既有 `handleConnect(fromId, toId)`（已支援去重、條件）；否則取消草稿。
- 「連線至下拉選單」保留為輔助輸入。

### 4.6 一鍵自動佈局（E）

- 工具列新按鈕「自動排程」：呼叫既有 `computeLayout(nodes, edges)` 產生新世界座標（需將以 0 為中心的分層輸出整體平移至正座標），逐節點 `updateProcessNode({x,y})` 保存，然後 `fitView()`。
- 建立手動拖曳後不再自動重排（僅按下按鈕時觸發）。

---

## 5. 互動優先級/衝突處理

| 手勢 | 判定（優先序高→低） |
|------|---------------------|
| port 拖曳連線 | 起始於 circle（port） |
| 節點拖曳 | 起始於節點 rect/g |
| 畫布平移 | 起始於 SVG 空白背景 |

以 `event.target` 判定起始元素，避免同時觸發。

---

## 6. i18n

`processFlow`（en / zh-TW / es-MX）新增 keys：

```
autoLayout, zoomIn, zoomOut, zoomReset, zoomFit, minimap,
dragHint, dragToConnect
```

---

## 7. 測試

**引擎（pytest）**：
- `ProcessNode` 含 x/y 欄位、`from_dict` 對舊資料無 x/y 仍可載入（default 0.0）。
- `create/update_process_node` 可寫入/更新 x/y。

**前端（手動驗證 + tsc/build）**：
- 新增第二個節點不擠出畫布（bug 復現測試）。
- 節點拖曳後位置持久化、重載保持。
- pan/zoom/minimap 操作正常。
- port 拖曳可建立邊、放下空白取消。
- 自動佈局重排並覆蓋手動位置。
- `npx tsc --noEmit` + `npm run build` 乾淨。
- 引擎 `pytest` 全綠。

---

## 8. 對既有行為的影響

- 既有「連線至下拉選單」「刪除節點」「屬性面板」全部保留。
- 新增節點不再自動重排 → 需手動按「自動排程」或自行拖曳；這是預期行為（手動優先）。
- 引擎 `ProcessNode.to_dict()` 會多出 x/y，其餘 API 不變。
