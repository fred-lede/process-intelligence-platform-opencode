import type {
  SPCAnalysisResult,
  MonteCarloResult,
  DistributionFitResult,
  ColumnSeries,
  TimeSeriesFeatures,
  GrrResult,
  InteractionResult,
  SHAPResult,
  ExtrapolationResult,
  ValidationResult,
  FullValidationResult,
  ModelInfo,
  ExperimentRecord,
  DoeStatisticsResult,
} from './engine'
import type { FieldAssignment, SpecConfiguration } from '../stores/dataPipelineStore'

function num(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return 'N/A'
  return String(Number(n.toFixed(digits)))
}

function pct(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return 'N/A'
  return `${(n * 100).toFixed(digits)}%`
}

function pctValue(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return 'N/A'
  return `${n.toFixed(digits)}%`
}

function recommendationLabel(key: string): string {
  const labels: Record<string, string> = {
    recReplicate: 'replicate center points to estimate pure error',
    recNewFactor: 'consider adding missing input factors',
    recRangeExpansion: 'consider expanding the factor range',
  }
  return labels[key] ?? key.replace(/^modelCenter\./, '')
}

export function buildDataImportContext(opts: {
  fields: FieldAssignment[]
  spec: SpecConfiguration | null
  rowCount: number | null
  columnCount: number | null
  readiness?: { status: string; columns: Array<{ column: string; role: string; status: string; best_distribution: string | null; issues: Array<{ message: string }> }> }
  quality?: { issues: Array<{ check: string; column: string | null; severity: string; message: string }> }
}): string {
  if (!opts.fields.length && opts.rowCount === null) return ''
  const inputs = opts.fields.filter((f) => f.role === 'input').map((f) => f.originalName)
  const outputs = opts.fields.filter((f) => f.role === 'output').map((f) => f.originalName)
  const lines = [
    `Imported dataset: ${opts.rowCount ?? 'N/A'} rows x ${opts.columnCount ?? 'N/A'} columns.`,
    `Input fields: ${inputs.join(', ') || 'none'}.`,
    `Output fields: ${outputs.join(', ') || 'none'}.`,
  ]
  if (opts.spec) {
    lines.push(
      `Spec: output="${opts.spec.outputField}", LSL=${opts.spec.lsl ?? 'N/A'}, USL=${opts.spec.usl ?? 'N/A'}, target=${opts.spec.target ?? 'N/A'}.`,
    )
  }
  if (opts.readiness) {
    lines.push(`Pre-model readiness: status=${opts.readiness.status}; ${opts.readiness.columns.map(c => `${c.role} ${c.column}: ${c.status}, best_distribution=${c.best_distribution ?? 'N/A'}, issues=${c.issues.length}`).join('; ')}.`)
  }
  if (opts.quality) {
    lines.push(`Data quality report: ${opts.quality.issues.length} issue(s): ${opts.quality.issues.map(i => `${i.severity}:${i.check}${i.column ? ` (${i.column})` : ''}`).join('; ') || 'none'}.`)
  }
  return lines.join('\n')
}

export function buildExplorationContext(opts: {
  fits: DistributionFitResult[] | null
  series: ColumnSeries | null
  tsFeatures: TimeSeriesFeatures | null
  grrResult: GrrResult | null
  filterColumn?: string
  filterValue?: string
  trendControlLimits?: { ucl?: number; lcl?: number }
  timeSeriesColumn?: string
  timeSeriesTimeColumn?: string
  grrMeasurementColumn?: string
  grrPartColumn?: string
  grrOperatorColumn?: string
}): string {
  const parts: string[] = []
  if (opts.filterColumn) parts.push(`Filter: ${opts.filterColumn}=${opts.filterValue ?? ''}; analyzed rows=${opts.series?.values.length ?? 'N/A'}.`)
  if (opts.fits && opts.fits.length) {
    const top = opts.fits[0]
    parts.push(
      `Distribution fit for column: best fit "${top.name}", AIC=${num(top.aic)}, BIC=${num(top.bic)}, ` +
        `KS p-value=${num(top.ks_p_value, 4)}, skewness=${num(top.skewness)}, kurtosis=${num(top.kurtosis)}.`,
    )
  }
  if (opts.series) {
    const numeric = opts.series.values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
    const first = numeric[0]
    const last = numeric[numeric.length - 1]
    const min = numeric.length ? Math.min(...numeric) : null
    const max = numeric.length ? Math.max(...numeric) : null
    const direction = first != null && last != null ? (last > first ? 'increasing' : last < first ? 'decreasing' : 'flat') : 'unknown'
    parts.push(
      `Trend for column "${opts.series.column}": ${opts.series.values.length} data points, ` +
        `numeric=${opts.series.numeric ? 'yes' : 'no'}, min=${num(min)}, max=${num(max)}, ` +
        `first=${num(first)}, last=${num(last)}, direction=${direction}.`,
    )
    if (numeric.length >= 2) {
      let rising = 1
      let falling = 1
      let maxRising = 1
      let maxFalling = 1
      for (let i = 1; i < numeric.length; i += 1) {
        rising = numeric[i] > numeric[i - 1] ? rising + 1 : 1
        falling = numeric[i] < numeric[i - 1] ? falling + 1 : 1
        maxRising = Math.max(maxRising, rising)
        maxFalling = Math.max(maxFalling, falling)
      }
      parts.push(`Longest consecutive runs: rising=${maxRising} points, falling=${maxFalling} points.`)
    }
    if (opts.trendControlLimits) {
      const { ucl, lcl } = opts.trendControlLimits
      const violations = numeric.flatMap((value, index) => {
        if (ucl != null && value > ucl) return [`index ${index}=${num(value)} (above UCL by ${num(value - ucl)})`]
        if (lcl != null && value < lcl) return [`index ${index}=${num(value)} (below LCL by ${num(lcl - value)})`]
        return []
      })
      parts.push(`Statistical control limits: UCL=${num(ucl)}, LCL=${num(lcl)}.`)
      parts.push(violations.length ? `Control-limit violations (${violations.length}): ${violations.join('; ')}.` : 'Control-limit violations: none.')
    }
  }
  if (opts.tsFeatures) {
    const preview = opts.tsFeatures.preview
    const baseColumn = opts.timeSeriesColumn
    const baseValues = baseColumn
      ? preview.map((row) => row[baseColumn]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
      : []
    const timeValues = opts.timeSeriesTimeColumn
      ? preview.map((row) => row[opts.timeSeriesTimeColumn!]).filter((value) => value != null).map(String)
      : []
    const featureSummaries = opts.tsFeatures.feature_columns.slice(0, 12).map((column) => {
      const values = preview.map((row) => row[column]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
      return `${column}: n=${values.length}, min=${num(values.length ? Math.min(...values) : null)}, max=${num(values.length ? Math.max(...values) : null)}`
    })
    parts.push(
      `Time-series analysis for time column "${opts.timeSeriesTimeColumn ?? 'selected time column'}" and value column "${opts.timeSeriesColumn ?? 'selected value column'}": ` +
        `${opts.tsFeatures.feature_columns.length} features across ${opts.tsFeatures.n_rows} rows, ` +
        `preview=${preview.length} rows, valid values=${baseValues.length}, ` +
        `range=${timeValues.length ? `${timeValues[0]} to ${timeValues[timeValues.length - 1]}` : 'N/A'}, ` +
        `value min=${num(baseValues.length ? Math.min(...baseValues) : null)}, max=${num(baseValues.length ? Math.max(...baseValues) : null)}. ` +
        `Feature summaries: ${featureSummaries.join('; ')}.`,
    )
  }
  if (opts.grrResult) {
    parts.push(
      `GRR (Gage R&R) using measurement="${opts.grrMeasurementColumn ?? 'selected measurement column'}", ` +
        `part="${opts.grrPartColumn ?? 'selected part column'}", operator="${opts.grrOperatorColumn ?? 'selected operator column'}": ` +
        `%GRR=${pctValue(opts.grrResult.pct_grr)}, %part=${pctValue(opts.grrResult.pct_part)}, ` +
        `verdict=${opts.grrResult.verdict}. Reason: ${opts.grrResult.verdict_reason}.`,
    )
  }
  return parts.join('\n')
}

export function buildModelCenterContext(opts: {
  interactions: InteractionResult | null
  shapResult: SHAPResult | null
  extrapResult: ExtrapolationResult | null
  validationResult: ValidationResult | null
  fullValidation: FullValidationResult | null
  doeStats: DoeStatisticsResult | null
  sensitivity?: { items: Array<{ input: string; sensitivity: number; effect_size: number }> } | null
  governanceWarnings?: string[]
  recommendedInputs?: string[]
  readiness?: { status: string; columns: Array<{ column: string; role: string; status: string; best_distribution: string | null; issues: Array<unknown> }> }
}): string {
  const parts: string[] = []
  const interactions = opts.interactions
  if (interactions && interactions.significant_pairs.length) {
    parts.push(
      `Interactions: ${interactions.significant_pairs.length} significant pair(s): ` +
        interactions.significant_pairs
          .slice(0, 5)
          .map((p) => `"${p.i}" x "${p.j}"`)
          .join(', '),
    )
  }
  if (opts.shapResult) {
    const top = opts.shapResult.feature_importance
      .slice()
      .sort((a, b) => b.importance - a.importance)
      .slice(0, 5)
    parts.push(`SHAP importance (top): ${top.map((f) => `"${f.name}"=${num(f.importance)}`).join(', ')}.`)
  }
  if (opts.extrapResult) {
    parts.push(
      `Extrapolation: max risk=${num(opts.extrapResult.max_risk)}, is_extrapolation=${opts.extrapResult.is_extrapolation ? 'yes' : 'no'}.`,
    )
  }
  if (opts.validationResult) {
    const m = opts.validationResult.mean_metrics
    parts.push(
      `Cross-validation: mean R2=${num(m.mean_r2, 4)}, mean RMSE=${num(m.mean_rmse)}. ` +
        `Residual normality: ${opts.validationResult.normality_test.is_normal ? 'normal' : 'not normal'}. ` +
        `Credibility composite=${opts.validationResult.credibility.composite}/100, level=${opts.validationResult.credibility.level}.`,
    )
  }
  if (opts.doeStats) {
    if (opts.doeStats.anova) {
      const a = opts.doeStats.anova
      parts.push(
        `DOE statistics (n=${opts.doeStats.n_obs}): R²=${num(opts.doeStats.r2, 4)}, adjR²=${num(opts.doeStats.adj_r2, 4)}. ` +
          `ANOVA F=${num(a.f_stat, 2)}, p=${num(a.p_value, 6)} [${a.significant ? 'significant' : 'not significant'}]. ` +
          `${opts.doeStats.sig_count}/${opts.doeStats.total_terms} terms significant (p<0.05).`,
      )
    } else if (opts.doeStats.note) {
      parts.push(`DOE stats: ${opts.doeStats.note}`)
    }
  }
  if (opts.sensitivity?.items?.length) {
    parts.push(`Sensitivity (permutation RMSE) and standardized effect size: ${opts.sensitivity.items.slice(0, 5).map((item) => `"${item.input}" sensitivity=${num(item.sensitivity, 4)}, effect_size=${num(item.effect_size, 4)}`).join('; ')}.`)
  }
  if (opts.fullValidation && opts.fullValidation.models.length) {
    const ranking = opts.fullValidation.models
      .slice()
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
    parts.push(
      `Full validation best models: ${ranking
        .map((m) => `${m.model_type} (R2=${num(m.cv_metrics.mean_r2, 3)}, score=${num(m.score, 1)})`)
        .join(' | ')}.`,
    )
    const dw = opts.fullValidation.residual_analysis?.durbin_watson
    if (dw) parts.push(`Residual diagnostics: Durbin-Watson=${num(dw.statistic, 3)}, interpretation=${dw.interpretation}.`)
    const recs = opts.fullValidation.experiment_recommendations?.recommendations ?? []
    if (recs.length) parts.push(`Experiment recommendations: ${recs.map((r) => `${r.priority}: ${recommendationLabel(r.key)}${(r.factors ?? []).length ? ` [factors: ${(r.factors ?? []).join(', ')}]` : ''}`).join('; ')}.`)
  }
  if (opts.governanceWarnings?.length) parts.push(`Governance warnings: ${opts.governanceWarnings.join('; ')}.`)
  if (opts.recommendedInputs?.length) parts.push(`Recommended inputs: ${opts.recommendedInputs.join(', ')}.`)
  if (opts.readiness) parts.push(`Pre-model readiness: status=${opts.readiness.status}; ${opts.readiness.columns.map(c => `${c.role} ${c.column}: ${c.status}, distribution=${c.best_distribution ?? 'N/A'}, issues=${c.issues.length}`).join('; ')}.`)
  return parts.join('\n')
}

export function buildSpcContext(result: SPCAnalysisResult | null): string {
  if (!result || !result.success) return ''
  const cl = result.control_limits
  const cap = result.capability
  const lines = [
    `SPC chart: ${result.chart_type}. Violations found: ${result.violations.length} ` +
      `(${result.violations.map((v) => `rule ${v.rule}`).join(', ') || 'none'}).`,
  ]
  const grain = (result as SPCAnalysisResult & { grain?: { filter_column?: string; filter_value?: string; analyzed_row_count?: number } }).grain
  if (grain?.filter_column) lines.push(`Filter: ${grain.filter_column}=${grain.filter_value}; analyzed rows=${grain.analyzed_row_count}.`)
  if (cap) {
    const cpkStatus = cap.cpk === null ? 'N/A' : cap.cpk >= 1.33 ? 'GOOD' : cap.cpk >= 1.0 ? 'MARGINAL' : 'POOR'
    lines.push(
      `Capability: Cp=${num(cap.cp)}, Cpk=${num(cap.cpk)} (${cpkStatus}), Pp=${num(cap.pp)}, Ppk=${num(cap.ppk)}, mean=${num(cap.mean)}.`,
    )
  }
  if (result.suggestions && result.suggestions.length > 0) {
    const urgent = result.suggestions.filter((s) => s.severity === 'error')
    const warning = result.suggestions.filter((s) => s.severity === 'warning')
    if (urgent.length > 0) {
      lines.push(`URGENT: ${urgent.map((s) => s.message).join('; ')}.`)
    }
    if (warning.length > 0) {
      lines.push(`WARNING: ${warning.map((s) => s.message).join('; ')}.`)
    }
  }
  if (cl.i_ucl !== null || cl.i_center !== null) {
    lines.push(
      `Control limits (I-chart, if present): center=${num(cl.i_center)}, UCL=${num(cl.i_ucl)}, LCL=${num(cl.i_lcl)}.`,
    )
  }
  return lines.join('\n')
}

export function buildMonteCarloContext(result: MonteCarloResult | null, spec?: { lsl?: number | null; usl?: number | null; target?: number | null }): string {
  if (!result) return ''
  const p = result.percentiles
  const top = (result.anomaly_rankings || []).slice(0, 5)
  const riskLevel =
    result.ng_probability > 0.05 ? 'HIGH' : result.ng_probability > 0.01 ? 'MEDIUM' : result.ng_probability > 0.001 ? 'MODERATE' : 'LOW'
  const lines = [
    `Monte Carlo (${result.n_simulations} simulations): NG probability=${pct(result.ng_probability, 2)} (${riskLevel}), ` +
      `NG count=${result.ng_count}, output mean=${num(result.output_mean)}, std=${num(result.output_std)}, median=${num(result.output_median)}.`,
    `Percentiles: p1=${num(p.p1)}, p5=${num(p.p5)}, p50=${num(p.p50)}, p95=${num(p.p95)}, p99=${num(p.p99)}.`,
  ]
  if (spec?.lsl != null || spec?.usl != null || spec?.target != null) {
    lines.push(`Specification limits: LSL=${num(spec.lsl)}, USL=${num(spec.usl)}, Target=${num(spec.target)}.`)
  }
  lines.push(`Multi-anomaly NG count=${result.multi_anomaly_ng}.`)
  if (top.length) {
    lines.push(`Top anomaly risk contributors: ${top.map((a) => `${a.name} (${pct(a.ng_contribution)})`).join(', ')}.`)
  }
  if (result.capability && result.capability.pp != null && result.capability.ppk != null && result.capability.sigma_overall != null) {
    const ppkStatus = result.capability.ppk >= 1.33 ? 'GOOD' : result.capability.ppk >= 1.0 ? 'MARGINAL' : 'POOR'
    lines.push(
      `Predicted capability (simulation): Pp=${num(result.capability.pp)}, Ppk=${num(result.capability.ppk)} (${ppkStatus}), sigma_overall=${num(result.capability.sigma_overall)}.`,
    )
    if (result.capability.ppk < 0 && spec?.lsl != null) {
      lines.push(`Capability diagnosis: Ppk is negative; output center is below the lower specification limit (LSL=${num(spec.lsl)}), indicating centering/alignment is the primary issue.`)
    }
  }
  return lines.join('\n')
}

export function buildPredictionContext(opts: {
  modelInfo: ModelInfo | null
  inputValues: Record<string, number>
  predicted: number | null
}): string {
  if (!opts.modelInfo || opts.predicted === null) return ''
  const inputs = Object.entries(opts.inputValues)
    .map(([k, v]) => `${k}=${num(v)}`)
    .join(', ')
  return (
    `Prediction for model type "${opts.modelInfo.model_type}": predicted output=${num(opts.predicted)}. ` +
    `Target="${opts.modelInfo.target}". ` +
    `Inputs now at: ${inputs || 'defaults'}. Equation: ${opts.modelInfo.equation ?? 'N/A'}.`
  )
}

export function buildValidationContext(opts: {
  fullValidation: FullValidationResult | null
  experiments: ExperimentRecord[]
}): string {
  const parts: string[] = []
  const fv = opts.fullValidation
  if (fv && fv.models.length) {
    const best = fv.models.find((m) => m.model_id === fv.best_model_id)
    parts.push(
      `Full validation: ${fv.models.length} models compared. Best model id=${fv.best_model_id} ` +
        `(${best ? best.model_type : 'N/A'}).` +
        (fv.credibility
          ? ` Credibility: ${Object.entries(fv.credibility)
              .map(([id, c]) => `${id}=${c.composite} (${c.level})`)
              .slice(0, 3)
              .join(', ')}.`
          : ''),
    )
  }
  if (opts.experiments.length) {
    const pass = opts.experiments.filter((e) => e.result === 'pass').length
    const avgErr = opts.experiments.length
      ? opts.experiments.reduce((s, e) => s + Math.abs(e.prediction_error ?? 0), 0) / opts.experiments.length
      : 0
    parts.push(
      `Experiments recorded: ${opts.experiments.length} (${pass} passed). Average absolute prediction error=${num(avgErr)}.`,
    )
  }
  return parts.join('\n')
}

export function buildReportsContext(hasGenerated: boolean, kind: string): string {
  return hasGenerated ? `A report was generated (format: ${kind}).` : ''
}
