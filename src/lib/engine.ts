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
  input_columns?: string[]
  output_columns?: string[]
  input_ranges?: Record<string, [number | null, number | null]>
  spec?: Record<string, { lsl?: number | null; usl?: number | null; target?: number | null }>
}): Promise<QualityReport> {
  return engineCall<QualityReport>('data/quality', params as unknown as Record<string, unknown>)
}

/** A single registered data asset (an imported dataset in the engine registry). */
export interface DataAsset {
  dataset_id: string
  file_path: string
  format: string
  encoding: string
  delimiter: string | null
  row_count: number
  column_count: number
}

/** List all data assets registered in the in-memory import registry. */
export async function getDataAssets(): Promise<{ datasets: DataAsset[] }> {
  return engineCall<{ datasets: DataAsset[] }>('data/datasets', {})
}

/** Fit distributions for a numeric column of a registered dataset. */
export async function fitDistribution(
  dataset_id: string,
  column: string,
  topN = 3,
  filters?: { filter_column?: string; filter_value?: string },
): Promise<{ fits: DistributionFitResult[] }> {
  return engineCall('data/distribution', {
    dataset_id,
    column,
    top_n: topN,
    ...(filters?.filter_column && filters.filter_value
      ? { filter_column: filters.filter_column, filter_value: filters.filter_value }
      : {}),
  })
}

/** Fetch a column's raw values from the registered dataset (for charts). */
export async function getColumnSeries(
  dataset_id: string,
  column: string,
  filters?: { filter_column?: string; filter_value?: string },
): Promise<ColumnSeries> {
  return engineCall<ColumnSeries>('data/series', {
    dataset_id,
    column,
    ...(filters?.filter_column && filters.filter_value
      ? { filter_column: filters.filter_column, filter_value: filters.filter_value }
      : {}),
  })
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
  | 'logistic_regression'
  | 'weibull_regression'
  | 'xgboost'
  | 'lightgbm'

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

export interface DoeCoefficientStat {
  name: string
  coef: number
  std_err: number
  t_stat: number
  p_value: number
  ci_lower: number
  ci_upper: number
  significant: boolean
}

export interface DoeAnovaResult {
  f_stat: number
  p_value: number
  significant: boolean
  df_reg: number
  df_res: number
  label: 'highly_significant' | 'significant' | 'marginally_significant' | 'not_significant'
}

export interface DoeStatisticsResult {
  model_type: string
  n_obs: number
  n_predictors: number
  r2: number | null
  adj_r2: number | null
  anova: DoeAnovaResult | null
  coefficients: DoeCoefficientStat[]
  sig_count: number
  total_terms: number
  fit_level: 'excellent' | 'good' | 'moderate' | 'marginal' | 'poor' | null
  note?: string
}

export interface DoeStatisticsParams {
  model_id: string
  dataset_id: string
}

export interface DoeStatisticsApiResponse {
  success: boolean
  statistics: DoeStatisticsResult
}

export interface ModelFitDTO {
  model_id: string
  model_type: ModelType
  target: string
  inputs: string[]
  selected_inputs?: string[]
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
  n_estimators?: number
  max_depth?: number
  min_samples_leaf?: number
  learning_rate?: number
  auto_select_features?: boolean
  importance_threshold?: number
  max_features?: number
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

export async function deleteModel(
  model_id: string,
): Promise<{ success: boolean; model_id: string }> {
  return engineCall<{ success: boolean; model_id: string }>('modeling/delete', { model_id })
}

export async function computeDOEStatistics(
  params: DoeStatisticsParams,
): Promise<DoeStatisticsApiResponse> {
  return engineCall<DoeStatisticsApiResponse>('modeling/stats', params as unknown as Record<string, unknown>)
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
  credibility: {
    data_coverage: number
    predictive_acc: number
    statistical_stability: number
    engineering_reasonable: number
    validation_degree: number
    extrapolation_risk: number
    composite: number
    level: 'production_ready' | 'engineering_reference' | 'exploratory' | 'needs_more_data' | 'not_recommended'
  }
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
  credibility: Record<string, {
    data_coverage: number
    predictive_acc: number
    statistical_stability: number
    engineering_reasonable: number
    validation_degree: number
    extrapolation_risk: number
    composite: number
    level: string
  }>
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
  spec?: Record<string, unknown> | null
  lsl?: number | null
  usl?: number | null
  runs_length?: number
  n_simulations?: number
  seed?: number
  enable_anomalies?: boolean
  spc_columns?: string[]
}

export async function suggestSpecLimits(params: {
  dataset_id: string
  column: string
}): Promise<{ success: boolean; column: string; mean: number; std: number; lsl: number; usl: number }> {
  return engineCall('spec/suggest', params as unknown as Record<string, unknown>)
}

export interface ReportResult {
  format: string
  content: string  // HTML content as string
  content_base64?: string  // Binary content as hex string
}

export async function generateReport(params: ReportParams): Promise<ReportResult> {
  return engineCall<ReportResult>('report/generate', params as unknown as Record<string, unknown>)
}

export interface ReportRecord {
  report_id: string
  project_name: string
  operator: string
  format: string
  timestamp: string
}

export async function listReports(): Promise<{ reports: ReportRecord[] }> {
  return engineCall<{ reports: ReportRecord[] }>('report/list', {})
}

// --- Phase 6: Auth & Audit -----------------------------------------------

export type UserRole = 'admin' | 'engineer' | 'reviewer' | 'viewer'

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
  lightgbm_device?: 'auto' | 'cpu' | 'gpu'
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

export interface SPCSuggestion {
  severity: 'error' | 'warning' | 'info'
  type: string
  message: string
}

export interface SPCBatchResult {
  results: Record<string, SPCAnalysisResult>
  columns: string[]
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
  z_values?: number[]
  c_plus?: number[]
  c_minus?: number[]
  ewma_lambda?: number
  ewma_L?: number
  cusum_k?: number
  cusum_H?: number
  ucl?: number
  lcl?: number
  cl?: number
  suggestions?: SPCSuggestion[]
  outlier_indices?: number[]
  change_points?: number[]
  outlier_stats?: Record<string, number>
}

export interface SPCCapabilityResult {
  success: boolean
  capability: SPCCapability
}

function flattenControlLimits(res: SPCAnalysisResult): SPCAnalysisResult {
  const raw = res.control_limits as unknown as Record<string, Record<string, number | undefined>>
  const flat: SPCCtrlLimits = { chart_type: res.chart_type }
  const isImr = res.chart_type === 'i-mr'
  for (const [group, vals] of Object.entries(raw)) {
    if (!vals || typeof vals !== 'object') continue
    const prefix = group === 'x' ? (isImr ? 'i' : 'x') : group
    if (vals.ucl !== undefined) (flat as any)[`${prefix}_ucl`] = vals.ucl
    if (vals.lcl !== undefined) (flat as any)[`${prefix}_lcl`] = vals.lcl
    if (vals.cl !== undefined) (flat as any)[`${prefix}_center`] = vals.cl
  }
  return { ...res, control_limits: flat }
}

export async function analyzeSPC(params: {
  dataset_id: string
  column: string
  chart_type?: 'i-mr' | 'xbar-r' | 'xbar-s' | 'ewma' | 'cusum'
  subgroup_size?: number
  lsl?: number
  usl?: number
  ewma_lambda?: number
  ewma_L?: number
  cusum_k?: number
  cusum_H?: number
  filter_column?: string
  filter_value?: string
  control_limits?: { lcl: number | null; ucl: number | null }
}): Promise<SPCAnalysisResult> {
  const res = await engineCall<SPCAnalysisResult>('spc/analyze', params)
  return flattenControlLimits(res)
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

export async function analyzeSPCBatch(params: {
  dataset_id: string
  columns: string[]
  chart_type?: string
  subgroup_size?: number
  lsl?: number
  usl?: number
  ewma_lambda?: number
  ewma_L?: number
  cusum_k?: number
  cusum_H?: number
}): Promise<SPCBatchResult> {
  return engineCall<SPCBatchResult>('spc/batch_analyze', params as unknown as Record<string, unknown>)
}

export interface MultiDatasetSPCEntry {
  dataset_id: string
  column: string
  source_file?: string
  n_points?: number
  result: SPCAnalysisResult
}

export interface MultiDatasetSPCResult {
  results: MultiDatasetSPCEntry[]
  count: number
}

export async function analyzeSPCMultiDataset(params: {
  entries: Array<{ dataset_id: string; column: string }>
  chart_type?: string
  lsl?: number
  usl?: number
}): Promise<MultiDatasetSPCResult> {
  return engineCall<MultiDatasetSPCResult>('spc/multi_dataset_analyze', params as unknown as Record<string, unknown>)
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
  capability?: SPCCapability | null
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
  filter_column?: string
  filter_value?: string
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

// --- Phase 11: Validation Lab -----------------------------------------------

export interface ExperimentRecord {
  experiment_id: string
  model_id: string
  planned_inputs: Record<string, number>
  actual_inputs: Record<string, number>
  predicted_output: number
  actual_output: number
  prediction_error: number
  result: 'pass' | 'fail' | 'inconclusive' | 'unknown'
  operator: string
  notes: string
  timestamp: string
}

export interface RecordExperimentParams {
  model_id: string
  planned_inputs: Record<string, number>
  actual_inputs: Record<string, number>
  predicted_output: number
  actual_output: number
  result: 'pass' | 'fail' | 'inconclusive' | 'unknown'
  operator: string
  notes?: string
}

export async function recordExperiment(params: RecordExperimentParams): Promise<{ experiment_id: string; prediction_error: number; result: string }> {
  return engineCall<{ experiment_id: string; prediction_error: number; result: string }>('experiment/record', params as unknown as Record<string, unknown>)
}

export async function listExperiments(params: { model_id?: string } = {}): Promise<{ experiments: ExperimentRecord[] }> {
  return engineCall<{ experiments: ExperimentRecord[] }>('experiment/list', params as unknown as Record<string, unknown>)
}

export async function getExperiment(experiment_id: string): Promise<ExperimentRecord> {
  return engineCall<ExperimentRecord>('experiment/get', { experiment_id })
}

// --- Phase 11b: What-if Scenario Save/Load ----------------------------------

export interface PredictionScenario {
  scenario_id: string
  name: string
  model_id: string
  input_values: Record<string, number>
  predicted_output: number
  operator: string
  notes: string
  timestamp: string
}

export interface SaveScenarioParams {
  name: string
  model_id: string
  input_values: Record<string, number>
  predicted_output: number
  operator: string
  notes?: string
}

export async function saveScenario(params: SaveScenarioParams): Promise<{ scenario_id: string; name: string }> {
  return engineCall<{ scenario_id: string; name: string }>('prediction/scenario/save', params as unknown as Record<string, unknown>)
}

export async function listScenarios(params: { model_id?: string } = {}): Promise<{ scenarios: PredictionScenario[] }> {
  return engineCall<{ scenarios: PredictionScenario[] }>('prediction/scenario/list', params as unknown as Record<string, unknown>)
}

export async function deleteScenario(scenario_id: string): Promise<{ deleted: boolean }> {
  return engineCall<{ deleted: boolean }>('prediction/scenario/delete', { scenario_id })
}

// --- Phase 11b: Time Series Features --------------------------------------

export interface TimeSeriesFeatures {
  feature_columns: string[]
  n_rows: number
  n_features: number
  preview: Record<string, unknown>[]
}

export interface ConsecutiveExceedance {
  column: string
  direction: string
  threshold: number
  n_exceedance_runs: number
  max_consecutive: number
  mean_run_length: number
  run_lengths: number[]
}

export interface TimeSeriesParams {
  dataset_id?: string
  columns?: string[]
  rows?: (string | null)[][]
  time_column: string
  value_columns: string[]
  window_sizes?: number[]
  filter_column?: string
  filter_value?: string
}

export interface ConsecutiveExceedanceParams {
  dataset_id?: string
  columns?: string[]
  rows?: (string | null)[][]
  value_column: string
  threshold: number
  direction?: 'above' | 'below'
}

export async function getTimeSeriesFeatures(params: TimeSeriesParams): Promise<TimeSeriesFeatures> {
  return engineCall<TimeSeriesFeatures>('features/time_series', params as unknown as Record<string, unknown>)
}

export async function getConsecutiveExceedance(params: ConsecutiveExceedanceParams): Promise<ConsecutiveExceedance> {
  return engineCall<ConsecutiveExceedance>('features/consecutive_exceedance', params as unknown as Record<string, unknown>)
}

// --- Phase 11b: Approval Workflow ------------------------------------------

export type ApprovalAction = 'submit_for_review' | 'approve' | 'reject'
export type ApprovalResourceType = 'model' | 'report'

export interface ApprovalRecord {
  record_id: string
  resource_type: ApprovalResourceType
  resource_id: string
  action: ApprovalAction
  reviewer: string
  reviewer_role: string
  comments: string
  timestamp: string
}

export interface ApprovalStatus {
  status: 'draft' | 'pending_review' | 'approved' | 'rejected' | 'retired'
}

export interface SubmitForReviewParams {
  resource_type: ApprovalResourceType
  resource_id: string
  reviewer: string
  reviewer_role: string
  comments?: string
}

export interface ApproveParams {
  resource_type: ApprovalResourceType
  resource_id: string
  reviewer: string
  reviewer_role: string
  comments?: string
}

export interface RejectParams {
  resource_type: ApprovalResourceType
  resource_id: string
  reviewer: string
  reviewer_role: string
  comments?: string
}

export interface ListApprovalRecordsParams {
  resource_type?: ApprovalResourceType
  resource_id?: string
}

export async function submitForReview(params: SubmitForReviewParams): Promise<{ record_id: string; new_status: string }> {
  return engineCall<{ record_id: string; new_status: string }>('approval/submit', params as unknown as Record<string, unknown>)
}

export async function approveResource(params: ApproveParams): Promise<{ record_id: string; new_status: string }> {
  return engineCall<{ record_id: string; new_status: string }>('approval/approve', params as unknown as Record<string, unknown>)
}

export async function rejectResource(params: RejectParams): Promise<{ record_id: string; new_status: string }> {
  return engineCall<{ record_id: string; new_status: string }>('approval/reject', params as unknown as Record<string, unknown>)
}

export async function getApprovalStatus(params: { resource_type: ApprovalResourceType; resource_id: string }): Promise<ApprovalStatus> {
  return engineCall<ApprovalStatus>('approval/status', params as unknown as Record<string, unknown>)
}

export async function listApprovalRecords(params: ListApprovalRecordsParams = {}): Promise<{ records: ApprovalRecord[] }> {
  return engineCall<{ records: ApprovalRecord[] }>('approval/records', params as unknown as Record<string, unknown>)
}

// --- Phase 11c: Copula Joint Probability -----------------------------------

export interface CopulaResult {
  mode: 'independent' | 'gaussian_copula' | 'direct'
  joint_probabilities: Record<string, number>
  pair_correlations?: Array<{
    anomaly_a: string
    anomaly_b: string
    joint_probability: number
    independent_expected: number
    correlation: number
  }>
  warning?: string
}

export interface CopulaParams {
  anomalies: Array<{
    anomaly_id: string
    occurrence_probability: number
    correlation_matrix?: number[][]
  }>
  correlation_matrix?: number[][]
  direct_joints?: Record<string, number>
  seed?: number
  n_samples?: number
}

export async function computeCopula(params: CopulaParams): Promise<CopulaResult> {
  return engineCall<CopulaResult>('copula/joint', params as unknown as Record<string, unknown>)
}

// --- Phase 11e: Gage R&R (Measurement System Analysis) ----------------------

export interface GrrResult {
  method: string
  n_parts: number
  n_operators: number
  n_reps: number
  repeatability_std: number
  reproducibility_std: number
  grr_std: number
  part_variation_std: number
  total_variation_std: number
  pct_grr: number
  pct_part: number
  verdict: 'acceptable' | 'marginal' | 'unacceptable'
  verdict_reason: string
  operator_means: Record<string, number[]>
  part_means: Record<string, number[]>
  operator_part_means: Record<string, Record<string, number>>
  warnings: string[]
}

export interface GrrParams {
  dataset_id?: string
  columns?: string[]
  rows?: (string | null)[][]
  measurement_column: string
  part_column: string
  operator_column: string
  filter_column?: string
  filter_value?: string
}

export async function analyzeGRR(params: GrrParams): Promise<GrrResult> {
  return engineCall<GrrResult>('data/grr', params as unknown as Record<string, unknown>)
}

// --- Phase 11g: Cloud Upload De-identification (spec 11A, 24) ----------------

export interface UploadPreview {
  dataset_id: string
  row_count: number
  total_columns: number
  transmitted_columns: string[]
  masked_columns: string[]
  excluded_columns: string[]
  mask_strategies: Record<string, string>
  noise_config: Record<string, { std: number; method: string }>
  upload_hash: string
  timestamp: string
}

export interface CloudPreviewParams {
  dataset_id: string
  sensitive_columns?: string[]
  excluded_columns?: string[]
  strategy_overrides?: Record<string, string>
  noise_std?: number
  seed?: number
}

export interface CloudUploadResult {
  record_id: string
  upload_hash: string
  row_count: number
  columns_uploaded: string[]
  masked_columns: string[]
  excluded_columns: string[]
}

export interface CloudUploadParams {
  dataset_id: string
  sensitive_columns?: string[]
  excluded_columns?: string[]
  strategy_overrides?: Record<string, string>
  noise_std?: number
  seed?: number
  operator: string
  provider: string
  model_version: string
  purpose: string
}

export interface UploadRecord {
  record_id: string
  operator: string
  provider: string
  model_version: string
  dataset_id: string
  row_count: number
  columns_uploaded: string[]
  mask_rules: Record<string, string>
  noise_rules: Record<string, { std: number; method: string }>
  upload_hash: string
  purpose: string
  timestamp: string
}

export async function previewCloudUpload(params: CloudPreviewParams): Promise<UploadPreview> {
  return engineCall<UploadPreview>('cloud/preview', params as unknown as Record<string, unknown>)
}

export async function confirmCloudUpload(params: CloudUploadParams): Promise<CloudUploadResult> {
  return engineCall<CloudUploadResult>('cloud/upload', params as unknown as Record<string, unknown>)
}

export async function listCloudUploadRecords(params: { dataset_id?: string; operator?: string } = {}): Promise<{ records: UploadRecord[] }> {
  return engineCall<{ records: UploadRecord[] }>('cloud/records', params as unknown as Record<string, unknown>)
}

// --- Phase 11h: Project Manifest & Filesystem (spec 11A) -------------------

export interface ProcessGroup {
  process_group_id: string
  display_name: string
  directory_name: string
  description: string
  input_templates: string[]
  output_templates: string[]
  quality_label_templates: string[]
  unit_profile: Record<string, string>
  active: boolean
  created_at: string
}

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

export interface DatasetRegistration {
  dataset_id: string
  source_path: string
  source_file: string
  format: string
  row_count: number
  column_count: number
  time_range?: { start: string; end: string }
  partition_keys: string[]
  schema_version: string
  checksum: string
  quality_status: 'unknown' | 'good' | 'degraded' | 'poor'
  sensitive_columns: string[]
  cloud_transfer_policy: 'off' | 'preview' | 'approved'
  registered_at: string
}

export interface ProjectManifest {
  project_id: string
  project_name: string
  operator: string
  version: string
  created_at: string
  updated_at: string
  project_root: string
  source_data_dirs: string[]
  process_groups: ProcessGroup[]
  process_nodes: ProcessNode[]
  dataset_count: number
  model_count: number
  settings: Record<string, unknown>
}

export interface ProjectDirs {
  source_data: string
  registry: string
  curated_data: string
  analysis_data: string
  models: string
  simulations: string
  experiments: string
  reports: string
  audit: string
}

export interface ScanResult {
  path: string
  name: string
  size_bytes: number
  format: string
}

export interface ProjectSourceDir {
  path: string
  name: string
  exists: boolean
  file_count: number
}

// Manifest
export async function getProjectManifest(): Promise<ProjectManifest> {
  return engineCall<ProjectManifest>('project/manifest', {})
}

export async function createProject(params: { root: string; name?: string; operator?: string }): Promise<{ project_id: string; project_name: string; project_root: string; created_at: string }> {
  return engineCall<{ project_id: string; project_name: string; project_root: string; created_at: string }>('project/create', params as unknown as Record<string, unknown>)
}

export async function openProject(root: string): Promise<{ project_id: string; project_name: string; project_root: string; datasets: number; process_groups: number }> {
  return engineCall<{ project_id: string; project_name: string; project_root: string; datasets: number; process_groups: number }>('project/open', { root })
}

export async function updateProjectSettings(updates: Record<string, unknown>): Promise<Record<string, unknown>> {
  return engineCall<Record<string, unknown>>('project/settings', { updates })
}

// Directories
export async function getProjectDirs(): Promise<ProjectDirs> {
  return engineCall<ProjectDirs>('project/dirs', {})
}

export async function listSourceDirs(): Promise<ProjectSourceDir[]> {
  const r = await engineCall<{ dirs: ProjectSourceDir[] }>('project/source-dirs', {})
  return r.dirs
}

export async function addSourceDir(params: { directory_name: string; absolute_path: string }): Promise<{ added: boolean; path: string; target: string }> {
  return engineCall<{ added: boolean; path: string; target: string }>('project/source-dirs', { action: 'add', ...params } as unknown as Record<string, unknown>)
}

export async function scanSourceDir(directory_path: string): Promise<ScanResult[]> {
  const r = await engineCall<{ files: ScanResult[] }>('project/scan', { directory_path })
  return r.files
}

// Process groups
export async function getProcessGroups(): Promise<ProcessGroup[]> {
  const r = await engineCall<{ process_groups: ProcessGroup[] }>('project/process-groups', {})
  return r.process_groups
}

export async function createProcessGroup(params: {
  display_name: string
  directory_name: string
  description?: string
  input_templates?: string[]
  output_templates?: string[]
  quality_label_templates?: string[]
  unit_profile?: Record<string, string>
}): Promise<ProcessGroup> {
  return engineCall<ProcessGroup>('project/process-group/create', params as unknown as Record<string, unknown>)
}

export async function updateProcessGroup(group_id: string, updates: Record<string, unknown>): Promise<ProcessGroup> {
  return engineCall<ProcessGroup>('project/process-group/update', { process_group_id: group_id, updates } as unknown as Record<string, unknown>)
}

export async function deleteProcessGroup(group_id: string): Promise<{ deleted: boolean }> {
  return engineCall<{ deleted: boolean }>('project/process-group/delete', { process_group_id: group_id })
}

export async function getProcessGroupTemplates(): Promise<Array<{ name: string; description: string }>> {
  const r = await engineCall<{ templates: Array<{ name: string; description: string }> }>('project/process-group-templates', {})
  return r.templates
}

// Process nodes
export async function getProcessNodes(): Promise<ProcessNode[]> {
  const r = await engineCall<{ process_nodes: ProcessNode[] }>('project/process-nodes', {})
  return r.process_nodes
}

export async function createProcessNode(params: {
  display_name: string
  node_type: string
  sequence_or_edges?: Array<{ from: string; to: string; condition?: string }>
  input_data_sources?: string[]
  rework_policy?: string
}): Promise<ProcessNode> {
  return engineCall<ProcessNode>('project/process-node/create', params as unknown as Record<string, unknown>)
}

export async function updateProcessNode(node_id: string, updates: Record<string, unknown>): Promise<ProcessNode> {
  return engineCall<ProcessNode>('project/process-node/update', { process_node_id: node_id, updates } as unknown as Record<string, unknown>)
}

export async function deleteProcessNode(node_id: string): Promise<{ deleted: boolean }> {
  return engineCall<{ deleted: boolean }>('project/process-node/delete', { process_node_id: node_id })
}

// Datasets
export async function getDatasets(): Promise<DatasetRegistration[]> {
  const r = await engineCall<{ datasets: DatasetRegistration[] }>('project/datasets', {})
  return r.datasets
}

export async function registerDataset(params: {
  source_path: string
  dataset_id?: string
  format?: string
  row_count?: number
  column_count?: number
  partition_keys?: string[]
  time_range?: { start: string; end: string }
  quality_status?: string
}): Promise<DatasetRegistration> {
  return engineCall<DatasetRegistration>('project/dataset/register', params as unknown as Record<string, unknown>)
}

export async function updateDataset(dataset_id: string, updates: Record<string, unknown>): Promise<DatasetRegistration | null> {
  return engineCall<DatasetRegistration | null>('project/dataset/update', { dataset_id, updates } as unknown as Record<string, unknown>)
}

// --- Phase 11i: Process Flow Diagram (spec 11A) ----------------------------

export interface FlowEdge {
  from: string
  to: string
  condition?: string
}

export interface FlowNode extends ProcessNode {}

export interface FlowGraph {
  nodes: FlowNode[]
  edges: FlowEdge[]
  association_keys: string[]
}

export interface FlowValidation {
  warnings: string[]
  errors: string[]
  valid: boolean
  node_count: number
  edge_count: number
}

export async function getFlowGraph(): Promise<FlowGraph> {
  return engineCall<FlowGraph>('project/flow-graph', {})
}

export async function setAssociationKeys(keys: string[]): Promise<{ association_keys: string[] }> {
  return engineCall<{ association_keys: string[] }>('project/flow-graph', {
    set_association_keys: keys,
  } as unknown as Record<string, unknown>)
}

export async function validateFlowGraph(): Promise<FlowValidation> {
  return engineCall<FlowValidation>('project/flow-validate', {})
}