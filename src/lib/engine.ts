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
  mean?: number
  std?: number
  min?: number
  max?: number
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

// --- Phase 3b-8: Validation Analysis ---------------------------------------

export interface CVResult {
  fold: number
  r2: number
  rmse: number
}

export interface ValidationResult {
  cv_results: CVResult[]
  mean_metrics: { mean_r2: number; mean_rmse: number }
  residuals: number[]
  stats: { mean: number; std: number; skewness: number; kurtosis: number }
  normality_test: { statistic: number; p_value: number; is_normal: boolean }
  recommendations: { type: string; reason: string; factors?: string[]; method?: string }[]
}

export async function analyzeValidation(params: {
  model_id: string
  dataset_id: string
  k?: number
}): Promise<ValidationResult> {
  return engineCall<ValidationResult>('modeling/validation/analyze', params as unknown as Record<string, unknown>)
}

// --- Phase 4: Full Validation -----------------------------------------------

export interface ExperimentRecommendation {
  type: string
  priority: 'high' | 'medium' | 'low'
  factors: string[]
  settings: Record<string, number>[]
  reason: string
}

export interface FullValidationResult {
  models: Array<{
    model_id: string
    model_type: string
    cv_metrics: { mean_r2: number; mean_rmse: number }
    residual_normal: boolean
    score: number
  }>
  best_model_id: string
  ranking: string[]
  residual_analysis: {
    qq_data: { theoretical_quantiles: number[]; sample_quantiles: number[] }
    residuals_vs_predicted: { predicted: number[]; residuals: number[] }
    durbin_watson: { statistic: number; interpretation: string }
  }
  interaction_analysis: {
    factors: string[]
    matrix: number[][]
    significant_pairs: Array<{ i: string; j: string; strength: number }>
  }
  experiment_recommendations: {
    recommendations: ExperimentRecommendation[]
    summary: string
  }
}

export async function runFullValidation(params: {
  dataset_id: string
  model_ids?: string[]
  k?: number
}): Promise<FullValidationResult> {
  return engineCall<FullValidationResult>('modeling/validation/full', params as unknown as Record<string, unknown>)
}

// --- Phase 5: Report Generation ----------------------------------------------

export interface ReportParams {
  project_name: string
  operator: string
  dataset_id: string
  model_ids?: string[]
  format: 'html' | 'pdf' | 'excel'
}

export interface ReportResult {
  format: string
  content: string  // HTML content as string
  content_base64?: string  // Binary content as hex string
}

export async function generateReport(params: ReportParams): Promise<ReportResult> {
  return engineCall<ReportResult>('report/generate', params as unknown as Record<string, unknown>)
}

// --- Phase 6: Auth & Audit -----------------------------------------------

export type UserRole = 'admin' | 'engineer' | 'viewer'

export interface AuthResult {
  success: boolean
  username?: string
  role?: UserRole
  error?: string
}

export interface UserRecord {
  username: string
  role: UserRole
  created_at: string
  is_active: boolean
}

export interface AuditEntry {
  id: string
  timestamp: string
  username: string
  action: string
  target: string
  details: Record<string, unknown>
}

export async function login(username: string, password: string): Promise<AuthResult> {
  return engineCall<AuthResult>('auth/login', { username, password })
}

export async function logout(): Promise<AuthResult> {
  return engineCall<AuthResult>('auth/logout', {})
}

export async function registerUser(username: string, role: UserRole): Promise<AuthResult> {
  return engineCall<AuthResult>('auth/register', { username, role })
}

export async function getCurrentUser(): Promise<{ username: string | null; role: UserRole | null }> {
  return engineCall<{ username: string | null; role: UserRole | null }>('auth/current', {})
}

export async function getAuditLog(limit: number = 100): Promise<{ log: AuditEntry[] }> {
  return engineCall<{ log: AuditEntry[] }>('audit/log', { limit })
}

export async function listUsers(): Promise<{ users: UserRecord[] }> {
  return engineCall<{ users: UserRecord[] }>('users/list', {})
}

// --- Phase 7: Ollama AI Assistant ------------------------------------------

export interface AIChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface AIChatResult {
  success: boolean
  response?: string
  error?: string
}

export interface AIModelsResult {
  success: boolean
  models?: string[]
  error?: string
}

export interface AIHealthResult {
  healthy: boolean
}

export async function aiChat(messages: AIChatMessage[], model?: string): Promise<AIChatResult> {
  return engineCall<AIChatResult>('ai/chat', { messages, model })
}

export async function listAIModels(): Promise<AIModelsResult> {
  return engineCall<AIModelsResult>('ai/models', {})
}

export async function checkAIHealth(): Promise<AIHealthResult> {
  return engineCall<AIHealthResult>('ai/health', {})
}

// --- Phase 7: AI Provider Settings ------------------------------------------

export type AIProviderType = 'ollama' | 'openai' | 'azure' | 'custom'

export interface AIProviderConfig {
  provider: AIProviderType
  base_url: string
  api_key: string
  model: string
  enabled: boolean
}

export interface SettingsGetResult {
  config: AIProviderConfig
}

export interface SettingsUpdateResult {
  success: boolean
  config: AIProviderConfig
}

export interface SettingsTestResult {
  success: boolean
  error?: string
}

export async function getSettings(): Promise<SettingsGetResult> {
  return engineCall<SettingsGetResult>('settings/get', {})
}

export async function updateSettings(config: Partial<AIProviderConfig>): Promise<SettingsUpdateResult> {
  return engineCall<SettingsUpdateResult>('settings/update', { config })
}

export async function testConnection(): Promise<SettingsTestResult> {
  return engineCall<SettingsTestResult>('settings/test_connection', {})
}

// --- Phase 8: SPC Control Charts --------------------------------------------

export interface SPCCapability {
  cp: number | null
  cpk: number | null
  pp: number | null
  ppk: number | null
  sigma_within: number | null
  sigma_overall: number | null
  mean: number
  n_subgroups: number
  total_observations: number
}

export interface SPCViolation {
  rule: number
  point_idx: number
  description: string
}

export interface SPCCtrlLimits {
  chart_type: string
  i_center?: number
  i_ucl?: number
  i_lcl?: number
  mr_center?: number
  mr_ucl?: number
  mr_lcl?: number
  sigma_estimate?: number
  x_center?: number
  x_ucl?: number
  x_lcl?: number
  r_center?: number
  r_ucl?: number
  r_lcl?: number
  s_center?: number
  s_ucl?: number
  s_lcl?: number
  sigma_within?: number
  subgroup_size?: number
  n_subgroups?: number
}

export interface SPCAnalysisResult {
  success: boolean
  chart_type: string
  x_values?: number[]
  mr_values?: number[]
  xbar_values?: number[]
  r_values?: number[]
  s_values?: number[]
  subgroups?: number[][]
  control_limits: SPCCtrlLimits
  violations: SPCViolation[]
  capability: SPCCapability | null
}

export interface SPCCapabilityResult {
  success: boolean
  capability: SPCCapability
}

export async function analyzeSPC(params: {
  dataset_id: string
  column: string
  chart_type?: 'i-mr' | 'xbar-r' | 'xbar-s'
  subgroup_size?: number
  lsl?: number
  usl?: number
}): Promise<SPCAnalysisResult> {
  return engineCall<SPCAnalysisResult>('spc/analyze', params)
}

export async function getSPCCapability(params: {
  dataset_id: string
  column: string
  lsl?: number
  usl?: number
  subgroup_size?: number
}): Promise<SPCCapabilityResult> {
  return engineCall<SPCCapabilityResult>('spc/capability', params)
}

// --- Phase 9: Monte Carlo Simulation ----------------------------------------

export interface MonteCarloHistogram {
  bins: number[]
  counts: number[]
}

export interface MonteCarloCDFData {
  x: number[]
  y: number[]
}

export interface MonteCarloBoxplotData {
  normal: number[]
  single_anomaly: number[]
  multi_anomaly: number[]
}

export interface MonteCarloAnomalyRanking {
  anomaly_id: string
  name: string
  ng_contribution: number
  probability: number
}

export interface MonteCarloPercentiles {
  p1: number
  p5: number
  p50: number
  p95: number
  p99: number
}

export interface MonteCarloResult {
  n_simulations: number
  seed: number
  ng_count: number
  ng_probability: number
  output_mean: number
  output_std: number
  output_median: number
  percentiles: MonteCarloPercentiles
  histogram: MonteCarloHistogram
  cdf_data: MonteCarloCDFData
  boxplot_data: MonteCarloBoxplotData
  anomaly_rankings: MonteCarloAnomalyRanking[]
  multi_anomaly_ng: number
}

export interface MonteCarloAnalysisResult {
  success: boolean
  result: MonteCarloResult
}

export interface MonteCarloParams {
  dataset_id: string
  model_id: string
  n_simulations?: number
  seed?: number
  enable_anomalies?: boolean
  anomalies?: Array<{
    anomaly_id: string
    name: string
    target_input: string
    direction: 'above' | 'below'
    occurrence_probability: number
    magnitude_distribution: Record<string, unknown>
  }>
  lsl?: number
  usl?: number
}

export async function analyzeMonteCarlo(params: MonteCarloParams): Promise<MonteCarloAnalysisResult> {
  return engineCall<MonteCarloAnalysisResult>('monte_carlo/run', params as unknown as Record<string, unknown>)
}

// --- Phase 10: Interactive Prediction (What-if) --------------------------------

export interface PredictionResult {
  success: boolean
  predicted: number
  equation: string
  inputs: string[]
  model_type: string
}

export interface ModelInfo {
  success: boolean
  model_type: string
  inputs: string[]
  coefficients: Record<string, number>
  equation: string
  n_train: number
  target: string
}

export interface InputRange {
  min: number
  max: number
  mean: number
  std: number
}

export async function predictOutput(params: {
  model_id: string
  input_values: Record<string, number>
}): Promise<PredictionResult> {
  return engineCall<PredictionResult>('prediction/predict', params)
}

export async function getModelInfo(params: {
  model_id: string
}): Promise<ModelInfo> {
  return engineCall<ModelInfo>('prediction/model_info', params)
}