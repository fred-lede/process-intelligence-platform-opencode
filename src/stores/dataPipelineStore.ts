import { create } from 'zustand'
import type { DetectedField, ImportResult, QualityReport, FieldRole, AnomalyScenario, AnalysisPackage, ControlLimits } from '../lib/engine'

export interface SpecConfiguration {
  outputField: string
  unit: string | null
  lsl: number | null
  usl: number | null
  target: number | null
  inputUnits: Record<string, string>
}

export type ConfirmStatus = 'notStarted' | 'pendingConfirm' | 'confirmed'

export interface FieldAssignment {
  originalName: string
  role: FieldRole
  dataType: string
  confidence: number
  confirmed: boolean
  notes?: string
}

/** Per-input control limits (manual override of auto 3σ). `null` = auto. */
export type ControlLimitsMap = Record<string, ControlLimits | null>

interface DataPipelineState {
  importResult: ImportResult | null
  fields: FieldAssignment[]
  quality: QualityReport | null
  spec: SpecConfiguration | null
  controlLimits: ControlLimitsMap
  anomalyScenarios: AnomalyScenario[]
  anomalyScenariosConfirmed: boolean
  analysisPackage: AnalysisPackage | null
  status: ConfirmStatus

  setImportResult: (result: ImportResult) => void
  setDetectedFields: (fields: DetectedField[]) => void
  setFields: (assignments: FieldAssignment[]) => void
  setQuality: (report: QualityReport) => void
  setSpec: (spec: SpecConfiguration) => void
  setControlLimit: (field: string, limits: ControlLimits | null) => void
  setAnomalyScenarios: (scenarios: AnomalyScenario[]) => void
  confirmAnomaly: (anomalyId: string) => void
  confirmAllAnomalies: () => void
  setAnalysisPackage: (pkg: AnalysisPackage) => void
  /** Bulk-restore analysis artifacts when opening a saved project, bypassing
   *  the reset semantics of the granular setters. */
  restoreAnalysis: (args: {
    anomalyScenarios: AnomalyScenario[]
    controlLimits: ControlLimitsMap
    analysisPackage: AnalysisPackage | null
  }) => void
  updateFieldRole: (originalName: string, role: FieldRole) => void
  confirmField: (originalName: string, confirmed?: boolean) => void
  confirmAllFields: () => void
  resetTo: (stage: 'import' | 'detect' | 'quality' | 'spec') => void
  resetAll: () => void
}

export const useDataPipelineStore = create<DataPipelineState>((set) => ({
  importResult: null,
  fields: [],
  quality: null,
  spec: null,
  controlLimits: {},
  anomalyScenarios: [],
  anomalyScenariosConfirmed: false,
  analysisPackage: null,
  status: 'notStarted',

  setImportResult: (result) =>
    set({
      importResult: result,
      status: 'pendingConfirm',
      fields: [],
      quality: null,
      spec: null,
      controlLimits: {},
      anomalyScenarios: [],
      anomalyScenariosConfirmed: false,
      analysisPackage: null,
    }),

  setDetectedFields: (detected) =>
    set({
      fields: detected.map((d) => ({
        originalName: d.name,
        role: d.role,
        dataType: d.data_type,
        confidence: d.confidence,
        confirmed: false,
      })),
      status: 'pendingConfirm',
    }),

  setFields: (assignments) =>
    set({ fields: assignments, status: 'confirmed' }),

  setQuality: (report) => set({ quality: report }),

  setSpec: (spec) =>
    set({ spec, controlLimits: {}, anomalyScenarios: [], anomalyScenariosConfirmed: false, analysisPackage: null }),

  setControlLimit: (field, limits) =>
    set((state) => ({
      controlLimits: { ...state.controlLimits, [field]: limits },
      anomalyScenarios: [],
      anomalyScenariosConfirmed: false,
      analysisPackage: null,
    })),

  setAnomalyScenarios: (scenarios) =>
    set({ anomalyScenarios: scenarios, anomalyScenariosConfirmed: false, analysisPackage: null }),

  confirmAnomaly: (anomalyId) =>
    set((state) => ({
      anomalyScenarios: state.anomalyScenarios.map((s) =>
        s.anomaly_id === anomalyId ? { ...s, user_confirmed: true } : s,
      ),
    })),

  confirmAllAnomalies: () =>
    set((state) => ({
      anomalyScenarios: state.anomalyScenarios.map((s) => ({ ...s, user_confirmed: true })),
      anomalyScenariosConfirmed: true,
    })),

  setAnalysisPackage: (pkg) => set({ analysisPackage: pkg }),

  restoreAnalysis: ({ anomalyScenarios, controlLimits, analysisPackage }) =>
    set({
      controlLimits,
      anomalyScenarios,
      anomalyScenariosConfirmed:
        anomalyScenarios.length > 0 && anomalyScenarios.every((s) => s.user_confirmed),
      analysisPackage,
    }),

  updateFieldRole: (originalName, role) =>
    set((state) => {
      const fields = state.fields.map((f) =>
        f.originalName === originalName ? { ...f, role } : f,
      )
      return { fields }
    }),

  confirmField: (originalName, confirmed = true) =>
    set((state) => {
      const fields = state.fields.map((f) =>
        f.originalName === originalName ? { ...f, confirmed } : f,
      )
      return { fields }
    }),

  confirmAllFields: () =>
    set((state) => ({
      fields: state.fields.map((f) => ({ ...f, confirmed: true })),
      status: 'confirmed',
    })),

  resetTo: (stage) =>
    set((state) => {
      if (stage === 'import') {
        return { importResult: null, fields: [], quality: null, status: 'notStarted' }
      }
      if (stage === 'detect') {
        return { fields: [], status: 'pendingConfirm' }
      }
      if (stage === 'quality') {
        return { quality: null }
      }
      if (stage === 'spec') {
        return { spec: null }
      }
      return state
    }),

  resetAll: () =>
    set({
      importResult: null,
      fields: [],
      quality: null,
      spec: null,
      controlLimits: {},
      anomalyScenarios: [],
      anomalyScenariosConfirmed: false,
      analysisPackage: null,
      status: 'notStarted',
    }),
}))