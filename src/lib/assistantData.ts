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

export function buildDataImportContext(opts: {
  fields: FieldAssignment[]
  spec: SpecConfiguration | null
  rowCount: number | null
  columnCount: number | null
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
  return lines.join('\n')
}

export function buildExplorationContext(opts: {
  fits: DistributionFitResult[] | null
  series: ColumnSeries | null
  tsFeatures: TimeSeriesFeatures | null
  grrResult: GrrResult | null
}): string {
  const parts: string[] = []
  if (opts.fits && opts.fits.length) {
    const top = opts.fits[0]
    parts.push(
      `Distribution fit for column: best fit "${top.name}", AIC=${num(top.aic)}, BIC=${num(top.bic)}, ` +
        `KS p-value=${num(top.ks_p_value, 4)}, skewness=${num(top.skewness)}, kurtosis=${num(top.kurtosis)}.`,
    )
  }
  if (opts.series) {
    parts.push(
      `Trend for column "${opts.series.column}": ${opts.series.values.length} data points, ` +
        `numeric=${opts.series.numeric ? 'yes' : 'no'}.`,
    )
  }
  if (opts.tsFeatures) {
    parts.push(
      `Time-series features computed: ${opts.tsFeatures.feature_columns.length} features across ${opts.tsFeatures.n_rows} rows.`,
    )
  }
  if (opts.grrResult) {
    parts.push(
      `GRR (Gage R&R): %GRR=${pct(opts.grrResult.pct_grr)}, %part=${pct(opts.grrResult.pct_part)}, ` +
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
  }
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
  if (cap) {
    lines.push(
      `Capability: Cp=${num(cap.cp)}, Cpk=${num(cap.cpk)}, Pp=${num(cap.pp)}, Ppk=${num(cap.ppk)}, mean=${num(cap.mean)}.`,
    )
  }
  if (result.suggestions && result.suggestions.length > 0) {
    lines.push(`Suggestions: ${result.suggestions.map(s => s.message).join('; ')}.`)
  }
  if (cl.i_ucl !== null || cl.i_center !== null) {
    lines.push(
      `Control limits (I-chart, if present): center=${num(cl.i_center)}, UCL=${num(cl.i_ucl)}, LCL=${num(cl.i_lcl)}.`,
    )
  }
  return lines.join('\n')
}

export function buildMonteCarloContext(result: MonteCarloResult | null): string {
  if (!result) return ''
  const p = result.percentiles
  const top = (result.anomaly_rankings || []).slice(0, 5)
  const lines = [
    `Monte Carlo (${result.n_simulations} simulations): NG probability=${pct(result.ng_probability)}, ` +
      `NG count=${result.ng_count}, output mean=${num(result.output_mean)}, std=${num(result.output_std)}, median=${num(result.output_median)}.`,
    `Percentiles: p1=${num(p.p1)}, p5=${num(p.p5)}, p50=${num(p.p50)}, p95=${num(p.p95)}, p99=${num(p.p99)}.`,
  ]
  if (top.length) {
    lines.push(`Top anomaly risk contributors: ${top.map((a) => `${a.name} (${pct(a.ng_contribution)})`).join(', ')}.`)
  }
  if (result.capability && result.capability.pp != null && result.capability.ppk != null && result.capability.sigma_overall != null) {
    lines.push(
      `Predicted capability (simulation): Pp=${num(result.capability.pp)}, Ppk=${num(result.capability.ppk)}, sigma_overall=${num(result.capability.sigma_overall)}.`,
    )
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
