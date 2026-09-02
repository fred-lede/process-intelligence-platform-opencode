import { invoke } from '@tauri-apps/api/core'

/**
 * Frontend API layer for the Python analysis engine.
 *
 * All calls go through Tauri IPC to the Rust core, which forwards them
 * to the Python engine subprocess.
 */

export interface EngineHealth {
  status: string
  engine: string
  version: string
}

/** Check whether the engine process is alive and responsive. */
export async function enginePing(): Promise<{ pong: boolean; version: string }> {
  return invoke<{ pong: boolean; version: string }>('engine_ping')
}

/** Read engine health status. */
export async function engineHealth(): Promise<EngineHealth> {
  return invoke<EngineHealth>('engine_health')
}

/**
 * Generic RPC call to the engine. The engine must be running (started by
 * the Rust core during app setup).
 */
export async function engineCall<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  return invoke<T>('engine_call', { method, params })
}

// --- Data pipeline API ----------------------------------------------------

export interface ColumnStats {
  numeric: boolean
  non_null_count: number
  unique_count: number
}

export interface ImportResult {
  dataset_id: string
  file_path: string
  format: string
  encoding: string
  delimiter: string | null
  columns: string[]
  raw_preview: (string | null)[][]
  row_count: number
  column_count: number
  stats: {
    row_count: number
    column_count: number
    column_stats: Record<string, ColumnStats>
  }
}

export type FieldRole =
  | 'identifier'
  | 'input'
  | 'output'
  | 'quality_label'
  | 'category'
  | 'timestamp'
  | 'metadata'
  | 'sensitive'
  | 'excluded'

export interface DetectedField {
  name: string
  role: FieldRole
  data_type: string
  confidence: number
  reason: string[]
}

export type QualitySeverity = 'info' | 'warning' | 'critical'

export interface QualityIssue {
  check: string
  column: string | null
  severity: QualitySeverity
  message: string
  detail: Record<string, unknown>
}

export interface QualityReport {
  row_count: number
  column_count: number
  issues: QualityIssue[]
}

export interface DistributionFitResult {
  name: string
  params: Record<string, number>
  aic: number
  bic: number
  ks_statistic: number
  ks_p_value: number
  loglik: number
  skewness: number | null
  kurtosis: number | null
  histogram: { counts: number[]; edges: number[] }
  pdf: { x: number[]; y: number[] }
}

export interface ColumnSeries {
  column: string
  values: (number | string | null)[]
  numeric: boolean
}

/** Import an Excel/CSV file. */
export async function importDataFile(file_path: string): Promise<ImportResult> {
  return engineCall<ImportResult>('data/import', { file_path })
}

/** Detect roles/data types. If `dataset_id` is given, values are drawn
 *  from the registered dataset; otherwise from `columns`. */
export async function detectFields(
  columns: { name: string; values: unknown[] }[],
  dataset_id?: string,
): Promise<{ fields: DetectedField[] }> {
  if (dataset_id) {
    return engineCall('data/detect_fields', { dataset_id })
  }
  return engineCall('data/detect_fields', { columns })
}

/** Run quality checks on a registered dataset. */
export async function runQualityChecks(params: {
  dataset_id: string
  categorical_columns?: string[]
  quality_columns?: string[]
  datetime_columns?: string[]
  batch_columns?: string[]
}): Promise<QualityReport> {
  return engineCall<QualityReport>('data/quality', params as unknown as Record<string, unknown>)
}

/** Fit distributions for a numeric column of a registered dataset. */
export async function fitDistribution(
  dataset_id: string,
  column: string,
  topN = 3,
): Promise<{ fits: DistributionFitResult[] }> {
  return engineCall('data/distribution', { dataset_id, column, top_n: topN })
}

/** Fetch a column's raw values from the registered dataset (for charts). */
export async function getColumnSeries(
  dataset_id: string,
  column: string,
): Promise<ColumnSeries> {
  return engineCall<ColumnSeries>('data/series', { dataset_id, column })
}

// --- Phase 2: Anomaly scenarios & analysis package ------------------------

export interface ControlLimits {
  lcl: number | null
  ucl: number | null
}

export type AnomalyDirection = 'above' | 'below' | 'run' | 'deviation'

export interface AnomalyScenario {
  anomaly_id: string
  name: string
  type: 'spec' | 'control' | 'engineering'
  target_input: string
  direction: AnomalyDirection
  threshold: number | null
  target: number | null
  tolerance: number | null
  occurrence_probability: number
  magnitude_distribution: Record<string, unknown> | null
  duration_distribution: Record<string, unknown> | null
  correlation_group: string | null
  source: string
  confidence: number
  user_confirmed: boolean
  detail: Record<string, unknown>
}

export interface AnalysisPackage {
  version: number
  dataset_id: string
  data: {
    source_file: string
    row_count: number
    column_count: number
    field_roles: Record<string, string>
    confirmed_field_count: number
  }
  spec: Record<string, unknown>
  anomalies: AnomalyScenario[]
  complete: boolean
  missing_requirements: string[]
}

/** Detect spec/control/engineering anomaly scenarios over a dataset. */
export async function detectAnomalies(params: {
  dataset_id: string
  spec?: { output_field?: string; lsl?: number | null; usl?: number | null; target?: number | null }
  control_limits?: Record<string, ControlLimits>
  engineering_scenarios?: { name: string; target_input: string; direction: string; target: number; tolerance: number }[]
  runs_length?: number
}): Promise<{ scenarios: AnomalyScenario[] }> {
  return engineCall('analysis/detect_anomalies', params as unknown as Record<string, unknown>)
}

/** Build the confirmable analysis data package. */
export async function buildAnalysisPackage(params: {
  dataset_id: string
  field_roles: Record<string, string>
  spec: Record<string, unknown>
  anomalies: AnomalyScenario[]
  confirmed_roles: string[]
}): Promise<AnalysisPackage> {
  return engineCall<AnalysisPackage>('analysis/package', params as unknown as Record<string, unknown>)
}

// --- Phase 3: Modeling ----------------------------------------------------

export type ModelType =
  | 'doe_linear'
  | 'doe_quadratic'
  | 'random_forest'
  | 'residual_hybrid'

export type ModelStatus =
  | 'draft'
  | 'pending_validation'
  | 'validated'
  | 'approved'
  | 'retired'

export interface ModelMetrics {
  rmse: number
  mse: number
  mae: number
  r2: number
  adj_r2: number
}

export interface ModelFitDTO {
  model_id: string
  model_type: ModelType
  target: string
  inputs: string[]
  status: ModelStatus
  created_at: string
  version: number
  metrics: ModelMetrics
  coefficients: Record<string, number> | null
  equation: string
  n_train: number
  n_test: number
}

export async function fitModel(params: {
  dataset_id: string
  model_type: ModelType
  target: string
  inputs: string[]
}): Promise<ModelFitDTO> {
  return engineCall<ModelFitDTO>('modeling/fit', params as unknown as Record<string, unknown>)
}

export async function listModels(): Promise<{ models: ModelFitDTO[] }> {
  return engineCall<{ models: ModelFitDTO[] }>('modeling/list', {})
}

export async function transitionModel(
  model_id: string,
  status: ModelStatus,
): Promise<ModelFitDTO> {
  return engineCall<ModelFitDTO>('modeling/transition', { model_id, status })
}

// --- Phase 3b: DOE Design Library ----------------------------------------

export interface DOEFactor {
  name: string
  low: number
  high: number
}

export interface DOEDesignResult {
  design_type: string
  n_runs: number
  runs: Record<string, number>[]
  coded_runs: Record<string, number>[]
}

export async function generateDOEDesign(params: {
  factors: DOEFactor[]
  design_type: string
  params?: Record<string, unknown>
}): Promise<DOEDesignResult> {
  return engineCall<DOEDesignResult>('modeling/doe/generate', params as unknown as Record<string, unknown>)
}

// --- Phase 3b: Interaction Analysis --------------------------------------

export interface InteractionResult {
  factors: string[]
  matrix: number[][]
  significant_pairs: { i: string; j: string; strength: number; significant: boolean }[]
}

export async function computeInteractions(params: {
  model_id: string
  dataset_id: string
  threshold?: number
}): Promise<InteractionResult> {
  return engineCall<InteractionResult>('modeling/interactions/compute', params as unknown as Record<string, unknown>)
}

// --- Phase 3b: SHAP Analysis -----------------------------------------------

export interface SHAPResult {
  expected_value: number
  feature_importance: { name: string; importance: number }[]
  shap_values: number[][]
}

export async function computeSHAP(params: {
  model_id: string
  dataset_id: string
  nsamples?: number
}): Promise<SHAPResult> {
  return engineCall<SHAPResult>('modeling/shap/explain', params as unknown as Record<string, unknown>)
}

// --- Phase 3b-7: Extrapolation Risk ----------------------------------------

export interface ExtrapolationResult {
  risk_scores: number[]
  factor_risks: Record<string, { min: number; max: number; risk: number }>
  max_risk: number
  is_extrapolation: boolean
}

export async function checkExtrapolation(params: {
  dataset_id: string
  prediction_points: Record<string, number>[]
}): Promise<ExtrapolationResult> {
  return engineCall<ExtrapolationResult>('modeling/extrapolation/check', params as unknown as Record<string, unknown>)
}