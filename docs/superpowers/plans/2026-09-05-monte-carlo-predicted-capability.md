# Monte Carlo Predicted Capability (Pp/Ppk) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add simulation-based predicted capability indices (Pp/Ppk) to the Monte Carlo page, computed in the engine by reusing `compute_capability`.

**Architecture:** `run_monte_carlo` already computes `output_values`, `output_mean`, `output_std` and receives `lsl`/`usl`. Add a `capability` key to its return dict via `spc.compute_capability(output_values, lsl, usl, subgroup_size=1)` (with subgroup_size=1, σ_within = overall σ → Pp/Ppk semantics). Frontend shows a Predicted Capability card reusing `SPCCapability` type; AI assistant context gains one line.

**Tech Stack:** Python 3.11 engine (pytest), React 18 + antd v5, TypeScript, plotly, i18next (en/zh-TW/es-MX).

**Spec:** `docs/superpowers/specs/2026-09-05-monte-carlo-predicted-capability-design.md`

---

### Task 1: Engine capability field (TDD)

**Files:**
- Modify: `engine/src/process_intelligence_engine/monte_carlo.py`
- Test: `engine/tests/test_main_monte_carlo.py`

- [ ] **Step 1: Write the failing tests** — append to `engine/tests/test_main_monte_carlo.py` (after the existing `test_monte_carlo_run_basic`, file ends with other tests):

```python
def test_monte_carlo_run_capability_pp_ppk(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("monte_carlo/run", {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 500,
        "seed": 42,
        "enable_anomalies": False,
        "lsl": 50.0,
        "usl": 200.0,
    })
    cap = result["result"]["capability"]
    mean = result["result"]["output_mean"]
    std = result["result"]["output_std"]
    assert cap["pp"] == pytest.approx((200.0 - 50.0) / (6 * std), rel=1e-5)
    assert cap["ppk"] == pytest.approx(
        min((200.0 - mean) / (3 * std), (mean - 50.0) / (3 * std)), rel=1e-5
    )
    assert cap["sigma_overall"] == pytest.approx(std, rel=1e-5)


def test_monte_carlo_run_capability_none_without_spec(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("monte_carlo/run", {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 500,
        "seed": 42,
        "enable_anomalies": False,
    })
    cap = result["result"]["capability"]
    assert cap["pp"] is None and cap["ppk"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_main_monte_carlo.py::test_monte_carlo_run_capability_pp_ppk tests/test_main_monte_carlo.py::test_monte_carlo_run_capability_none_without_spec -v`
Expected: FAIL with `KeyError: 'capability'`

- [ ] **Step 3: Implement** — in `engine/src/process_intelligence_engine/monte_carlo.py`:

Add import next to the existing `.copula` import (line 12):

```python
from .spc import compute_capability
```

Add one entry to the return dict (monte_carlo.py:375-392), after `"violations": violations,`:

```python
        "capability": compute_capability(output_values, lsl=lsl, usl=usl, subgroup_size=1),
```

Note: `run_monte_carlo` already receives `lsl`/`usl` as parameters; `output_values` is the full simulated np.ndarray (already used at :390). `spc.py` imports only `math`/`typing`/`numpy` — no circular import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/test_main_monte_carlo.py -q`
Expected: all Monte Carlo tests PASS (existing 8 + 2 new)
Then: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: **304 passed, 1 skipped** (baseline + 2)

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/monte_carlo.py engine/tests/test_main_monte_carlo.py
git commit -m "feat(engine): monte carlo predicted capability (Pp/Ppk) via compute_capability"
```

---

### Task 2: Frontend — type, capability card, AI context, i18n

**Files:**
- Modify: `src/lib/engine.ts`
- Modify: `src/features/monte-carlo/MonteCarlo.tsx`
- Modify: `src/lib/assistantData.ts`
- Modify: `src/i18n/en.json`, `src/i18n/zh-TW.json`, `src/i18n/es-MX.json`

- [ ] **Step 1: Add capability to `MonteCarloResult`** — in `src/lib/engine.ts`, in `MonteCarloResult` (engine.ts:780-794), add after `multi_anomaly_ng: number`:

```ts
  capability?: SPCCapability | null
```

(`SPCCapability` already exists at engine.ts:649 with fields `cp/cpk/pp/ppk/sigma_within/sigma_overall/mean/n_subgroups/total_observations` — matches `compute_capability` output exactly.)

- [ ] **Step 2: Add i18n keys (three locales, key-set parity)**

In `src/i18n/en.json` monteCarlo section (en.json:471-502), after `"nodeFilterCleared": "Clear node filter"` add:

```json
    ,
    "predictedCapability": "Predicted Capability (simulation)",
    "pp": "Pp",
    "ppk": "Ppk",
    "sigmaOverall": "σ overall"
```

In `src/i18n/zh-TW.json` monteCarlo section (zh-TW.json:471), after the matching `nodeFilterCleared` entry add:

```json
    ,
    "predictedCapability": "預測能力指數（模擬）",
    "pp": "Pp",
    "ppk": "Ppk",
    "sigmaOverall": "σ 整體"
```

In `src/i18n/es-MX.json` monteCarlo section (es-MX.json:473), after the matching `nodeFilterCleared` entry add:

```json
    ,
    "predictedCapability": "Capacidad prevista (simulación)",
    "pp": "Pp",
    "ppk": "Ppk",
    "sigmaOverall": "σ general"
```

Note: the `nodeFilterCleared` line in each file ends with `"` (no trailing comma) — insert `,` before the new keys. After editing, verify parity:

Run: `python3 -c "import json; ks=[set(json.load(open('src/i18n/%s.json'%f))['monteCarlo']) for f in ('en','zh-TW','es-MX')]; print('parity ok:', ks[0]==ks[1]==ks[2], 'count:', len(ks[0]))"`
Expected: `parity ok: True count: 34`

- [ ] **Step 3: Render the Predicted Capability card** — in `src/features/monte-carlo/MonteCarlo.tsx`:

(a) Add `Statistic` to the existing antd import (line 3):

```tsx
import { Card, Select, Space, Button, Alert, Form, Input, Switch, Typography, Table, Tag, Row, Col, Statistic } from 'antd'
```

(b) Add a color helper right after the `cdfTrace` block (after line 119):

```tsx
const capColor = (val: number) => (val >= 1.33 ? '#52c41a' : val >= 1.0 ? '#fa8c16' : '#ff4d4f')
```

(c) Insert the card between the percentiles `</Row>` (line 233) and the `outputDistribution` Card (line 235):

```tsx
          {result.capability && result.capability.pp != null && result.capability.ppk != null && (
            <Card title={t('monteCarlo.predictedCapability')} size="small">
              <Row gutter={16}>
                <Col span={6}>
                  <Statistic
                    title={t('monteCarlo.pp')}
                    value={result.capability.pp}
                    precision={2}
                    valueStyle={{ color: capColor(result.capability.pp) }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={t('monteCarlo.ppk')}
                    value={result.capability.ppk}
                    precision={2}
                    valueStyle={{ color: capColor(result.capability.ppk) }}
                  />
                </Col>
                <Col span={12}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('monteCarlo.sigmaOverall')}: {result.capability.sigma_overall.toFixed(3)}
                  </Typography.Text>
                </Col>
              </Row>
            </Card>
          )}
```

- [ ] **Step 4: Add capability to AI assistant context** — in `src/lib/assistantData.ts` `buildMonteCarloContext` (assistantData.ts:157-170), after the `top` contributor block (after line 168, before `return lines.join('\n')`):

```ts
  if (result.capability && result.capability.pp != null && result.capability.ppk != null) {
    lines.push(
      `Predicted capability (simulation): Pp=${num(result.capability.pp)}, Ppk=${num(result.capability.ppk)}, sigma_overall=${num(result.capability.sigma_overall)}.`,
    )
  }
```

- [ ] **Step 5: Verify frontend**

Run: `npx tsc --noEmit`
Expected: exit 0, no output
Run: `npm run build 2>&1 | tail -2`
Expected: `✓ built in ...s` (chunk warning is pre-existing)

- [ ] **Step 6: Commit**

```bash
git add src/lib/engine.ts src/features/monte-carlo/MonteCarlo.tsx src/lib/assistantData.ts src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(monte-carlo): predicted capability (Pp/Ppk) card, AI context, i18n"
```

---

### Task 3: Docs + final verification + push

**Files:**
- Modify: `PROGRESS.md`, `TASK.md`, `README.md`

- [ ] **Step 1: Update docs**

- `PROGRESS.md`: append a 2026-09-05 entry under the FAI section describing the predicted capability feature (engine `capability` field reusing `compute_capability`, Pp/Ppk card, worker thresholds ≥1.33/≥1.0 mirrored from SPC, i18n +4 keys ×3, engine 306 passed 1 skipped after Task 1).
- `TASK.md`: add a DONE entry summarizing Task 1/2/3 with commit hashes.
- `README.md`: add a bullet to the Monte Carlo feature area (Phase 9) noting predicted Pp/Ppk. Only if README lists MC features.

- [ ] **Step 2: Final verification**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: **306 passed, 1 skipped**
Run: `npx tsc --noEmit` then `npm run build 2>&1 | tail -2`
Expected: tsc exit 0; `✓ built in ...s`
Run: `git status --short`
Expected: only intended files (do NOT commit `engine/.coverage`, `src-tauri/icons/`)

- [ ] **Step 3: Commit + push**

```bash
git add PROGRESS.md TASK.md README.md
git commit -m "docs: monte carlo predicted capability (Pp/Ppk)"
git push
```

---

## Self-review notes

- Spec coverage: engine capability ✔ (Task 1), frontend card ✔ (Task 2), AI context ✔ (Task 2 Step 4), i18n ✔ (Task 2 Step 2), verification ✔ (Task 3). Excluded items (Cp/Cpk, IPC change, 4σ grading) stay out.
- Type consistency: `capability?: SPCCapability | null` matches `compute_capability` return keys exactly (cp/cpk/pp/ppk/sigma_within/sigma_overall/mean/n_subgroups/total_observations). `pytest.approx(rel=1e-5)` used because `compute_capability` rounds to 6 decimals while `output_std` is unrounded.
- No placeholders; all code blocks complete for both implementation and tests.