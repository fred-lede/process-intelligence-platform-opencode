# AI 助手領域知識增強 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance AI assistant domain knowledge for SPC, Monte Carlo, and Exploration pages.

**Architecture:** Update `assistantGuide.ts` TAB_GUIDES with detailed domain knowledge, enhance `assistantData.ts` context builders for richer data summaries.

**Tech Stack:** TypeScript, React, i18next.

**Spec:** `docs/superpowers/specs/2026-09-05-ai-assistant-domain-knowledge-design.md`

---

### Task 1: Enhance SPC assistant guide

**Files:**
- Modify: `src/lib/assistantGuide.ts`

- [ ] **Step 1: Replace SPC guide body with enhanced domain knowledge**

Replace the existing `spc` entry (lines 174-181) with:

```typescript
spc: {
  name: 'SPC Control',
  body: `This page performs Statistical Process Control (SPC) to monitor process stability and capability.

## Chart Type Selection Guide:
- **I-MR (Individuals & Moving Range)**: Use when measuring individual items (subgroup size = 1). Most common for destructive testing or slow processes.
- **X-bar + R**: Use for subgroups of size 2-10 with stable variation. Shows average and range trends.
- **X-bar + S**: Use for subgroups ≥11 or when variation differences are large. More sensitive than R chart.
- **EWMA (Exponentially Weighted Moving Average)**: Use to detect small shifts (<1.5σ). More sensitive than I-MR for gradual drift.
- **CUSUM (Cumulative Sum)**: Use for detecting persistent small offsets. Best for process optimization where small shifts matter.

## Capability Index Interpretation:
- **Cp/Cpk ≥ 1.33**: Process capability is GOOD (green). Meet most industry standards.
- **1.0 ≤ Cp/Cpk < 1.33**: Marginal (orange). Monitor closely, prepare improvement plan.
- **Cp/Cpk < 1.0**: POOR (red). Process cannot consistently meet specs. Immediate action needed.
- **Cp vs Cpk**: Cp measures potential capability (spread only). Cpk measures actual performance (spread + centering). Large gap between Cp and Cpk indicates off-center process.

## Western Electric Rule Interpretation:
- **Rule 1** (1 point beyond 3σ): Immediate out-of-control. Investigate special cause.
- **Rule 2** (2 of 3 points beyond 2σ): Trend starting. Monitor closely.
- **Rule 3** (4 of 5 points beyond 1σ): Shift developing. Check for material/tool changes.
- **Rule 4** (8 consecutive points same side): Process shift detected. Investigate mean change.
- **Rule 5** (6 points trending): Drift detected. Check tool wear, temperature, etc.
- **Rule 6** (15 points within ±1σ): Reduced variation. May indicate stratification or measurement issue.
- **Rule 7** (14 points alternating)**: Systematic variation. Check for alternating causes.

## Optimization Suggestions:
- **Low capability (Cpk < 1.0)**: Reduce process variation or adjust target to center between specs.
- **Shift detected (Rule 4)**: Check raw material lots, machine parameters, operator changes.
- **Trend detected (Rule 5)**: Inspect tool wear, calibration drift, environmental conditions.
- **EWMA/CUSUM violations**: Small persistent shift. Immediate adjustment may prevent NG.

## How to Use:
1. Select chart type appropriate for your data structure
2. Choose the output column to analyze
3. Set spec limits (LSL/USL) if available
4. Click Analyze and interpret the control chart
5. Check violations table for out-of-control signals
6. Review capability indices for process performance
7. Read optimization suggestions for action items`,
},
```

- [ ] **Step 2: Verify TypeScript compilation**

Run: `npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add src/lib/assistantGuide.ts
git commit -m "feat(assistant): enhance SPC domain knowledge in AI guide"
```

---

### Task 2: Enhance Monte Carlo assistant guide

**Files:**
- Modify: `src/lib/assistantGuide.ts`

- [ ] **Step 1: Replace MC guide body with enhanced domain knowledge**

Replace the existing `monteCarlo` entry (lines 132-138) with:

```typescript
monteCarlo: {
  name: 'Monte Carlo',
  body: `This page runs Monte Carlo risk simulation to predict process performance under uncertainty.

## How It Works:
1. Samples input variables from their distributions (Normal, Gamma, Lognormal, or Empirical)
2. Optionally injects anomaly scenarios (shifted inputs)
3. Predicts output using the fitted model
4. Computes NG (non-conforming) probability and percentiles

## NG Probability Interpretation:
- **< 0.1%**: EXCELLENT. Process is highly capable.
- **0.1% - 1%**: ACCEPTABLE. Typical for well-controlled processes.
- **1% - 5%**: WARNING. Consider process improvement.
- **> 5%**: HIGH RISK. Immediate action needed to reduce variation or tighten specs.

## Percentile Guide:
- **P1/P99**: Extreme bounds (0.1% to 99.9% of output)
- **P5/P95**: Normal operating range (5% to 95%)
- **P50**: Median (most likely output value)
- Use percentiles to set realistic expectations and safety margins.

## Predicted Capability (Pp/Ppk):
- Computed from simulated output distribution
- Similar interpretation to SPC capability indices
- Pp/Ppk from simulation shows EXPECTED performance, not current
- Useful for comparing design alternatives before production

## Anomaly Risk Ranking:
- Shows which input anomalies contribute most to NG
- Prioritize mitigation efforts on high-contribution anomalies
- NG contribution = how much that anomaly increases NG probability

## How to Use:
1. Select a fitted model from Model Center
2. Set simulation count (10,000+ recommended)
3. Enable anomaly scenarios if you want worst-case analysis
4. Run simulation and interpret NG probability
5. Check percentiles for output range expectations
6. Review anomaly rankings to prioritize improvements`,
},
```

- [ ] **Step 2: Verify TypeScript compilation**

Run: `npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add src/lib/assistantGuide.ts
git commit -m "feat(assistant): enhance Monte Carlo domain knowledge in AI guide"
```

---

### Task 3: Enhance Exploration assistant guide

**Files:**
- Modify: `src/lib/assistantGuide.ts`

- [ ] **Step 1: Replace Exploration guide body with enhanced domain knowledge**

Replace the existing `exploration` entry (lines 97-103) with:

```typescript
exploration: {
  name: 'Exploration',
  body: `This page performs exploratory data analysis with three tabs: Distribution, Trend, and Time Series.

## Distribution Tab:
- Shows histograms and fit results for each numeric column
- Best-fit distribution selected by lowest AIC/BIC and KS test
- **Interpretation**:
  - Normal distribution: Process likely in control, centered
  - Skewed distribution: Check for mixture, truncation, or natural bounds
  - Multiple peaks: May indicate multiple process conditions or material lots
- Key metrics: mean, std, skewness (asymmetry), kurtosis (tail weight)

## Trend Tab:
- Plots values over time/order to detect drift or shifts
- **Look for**:
  - Gradual drift: Tool wear, temperature drift, chemical degradation
  - Sudden shift: Material change, machine adjustment, operator change
  - Cycles: Daily/weekly patterns, maintenance schedules

## Time Series Features:
- **Lag autocorrelation**: Measures similarity between adjacent points
- **Rolling statistics**: Moving average/std to visualize local trends
- **Drift**: Rate of change over time
- **Consecutive exceedance**: How long process stays out of spec

## GRR (Gage R&R):
- Measures measurement system variation
- **%GRR < 10%**: ACCEPTABLE. Measurement system is adequate.
- **10% ≤ %GRR < 30%**: MARGINAL. May be acceptable depending on application.
- **%GRR ≥ 30%**: UNACCEPTABLE. Improve measurement system (calibration, fixture, operator training).
- Components: EV (equipment/repeatability), AV (appraiser/replica), GRR (combined)

## How to Use:
1. Start with Distribution tab to understand data characteristics
2. Check Trend tab for stability over time
3. Use Time Series features for deeper pattern analysis
4. Run GRR if measurement variation is a concern
5. Use findings to inform model building in Model Center`,
},
```

- [ ] **Step 2: Verify TypeScript compilation**

Run: `npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add src/lib/assistantGuide.ts
git commit -m "feat(assistant): enhance Exploration domain knowledge in AI guide"
```

---

### Task 4: Enhance assistantData context builders

**Files:**
- Modify: `src/lib/assistantData.ts`

- [ ] **Step 1: Enhance buildSpcContext with structured summary**

Update `buildSpcContext` function to include capability assessment and action items:

```typescript
export function buildSpcContext(result: SPCAnalysisResult | null): string {
  if (!result || !result.success) return ''
  const cl = result.control_limits
  const cap = result.capability
  const lines = [
    `SPC chart: ${result.chart_type}. Violations: ${result.violations.length} (${result.violations.map((v) => v.rule).join(', ') || 'none'}).`,
  ]
  if (cap) {
    const cpkStatus = cap.cpk == null ? 'N/A' : cap.cpk >= 1.33 ? 'GOOD' : cap.cpk >= 1.0 ? 'MARGINAL' : 'POOR'
    lines.push(
      `Capability: Cp=${num(cap.cp)}, Cpk=${num(cap.cpk)}, Pp=${num(cap.pp)}, Ppk=${num(cap.ppk)}. ` +
        `Cpk status: ${cpkStatus}.`,
    )
  }
  if (result.suggestions && result.suggestions.length > 0) {
    const urgent = result.suggestions.filter(s => s.severity === 'error')
    const warning = result.suggestions.filter(s => s.severity === 'warning')
    if (urgent.length) {
      lines.push(`URGENT: ${urgent.map(s => s.message).join('; ')}.`)
    }
    if (warning.length) {
      lines.push(`WARNING: ${warning.map(s => s.message).join('; ')}.`)
    }
  }
  if (cl.i_ucl !== null || cl.i_center !== null) {
    lines.push(
      `Control limits: center=${num(cl.i_center)}, UCL=${num(cl.i_ucl)}, LCL=${num(cl.i_lcl)}.`,
    )
  }
  return lines.join('\n')
}
```

- [ ] **Step 2: Enhance buildMonteCarloContext**

Update `buildMonteCarloContext` to include risk assessment:

```typescript
export function buildMonteCarloContext(result: MonteCarloResult | null): string {
  if (!result) return ''
  const p = result.percentiles
  const top = (result.anomaly_rankings || []).slice(0, 5)
  
  // Risk assessment
  const ngProb = result.ng_probability
  let riskLevel = 'LOW'
  if (ngProb > 0.05) riskLevel = 'HIGH'
  else if (ngProb > 0.01) riskLevel = 'MEDIUM'
  else if (ngProb > 0.001) riskLevel = 'MODERATE'
  
  const lines = [
    `Monte Carlo (${result.n_simulations} simulations): NG probability=${pct(result.ng_probability)} [${riskLevel} risk].`,
    `Output: mean=${num(result.output_mean)}, std=${num(result.output_std)}, median=${num(result.output_median)}.`,
    `Percentiles: P1=${num(p.p1)}, P5=${num(p.p5)}, P50=${num(p.p50)}, P95=${num(p.p95)}, P99=${num(p.p99)}.`,
  ]
  if (top.length) {
    lines.push(`Top risk drivers: ${top.map((a) => `${a.name} (${pct(a.ng_contribution)})`).join(', ')}.`)
  }
  if (result.capability && result.capability.pp != null && result.capability.ppk != null) {
    const ppkStatus = result.capability.ppk >= 1.33 ? 'GOOD' : result.capability.ppk >= 1.0 ? 'MARGINAL' : 'POOR'
    lines.push(
      `Predicted capability: Pp=${num(result.capability.pp)}, Ppk=${num(result.capability.ppk)} [${ppkStatus}].`,
    )
  }
  return lines.join('\n')
}
```

- [ ] **Step 3: Verify TypeScript compilation**

Run: `npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add src/lib/assistantData.ts
git commit -m "feat(assistant): enhance SPC/MC context builders with risk assessment"
```

---

### Task 5: Docs + verification + push

**Files:**
- Modify: `PROGRESS.md`, `TASK.md`

- [ ] **Step 1: Update docs**

- `PROGRESS.md`: append entry for AI assistant enhancement
- `TASK.md`: add DONE entry

- [ ] **Step 2: Final verification**

```bash
npx tsc --noEmit
npm run build 2>&1 | tail -2
```

- [ ] **Step 3: Commit + push**

```bash
git add PROGRESS.md TASK.md
git commit -m "docs: AI assistant domain knowledge enhancement"
git push
```

---

## Self-review

- Spec coverage: all three pages (SPC, MC, Exploration) enhanced
- No breaking changes to existing functionality
- Context builders provide more structured, actionable summaries
