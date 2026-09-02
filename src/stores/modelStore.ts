import { create } from 'zustand'
import type { ModelFitDTO, ModelType, ModelStatus } from '../lib/engine'
import { fitModel, listModels, transitionModel } from '../lib/engine'

export interface ModelStore {
  models: ModelFitDTO[]
  fitting: boolean
  transitioning: boolean
  error: string | null
  selectedModelId: string | null

  loadModels: () => Promise<void>
  fit: (params: {
    dataset_id: string
    model_type: ModelType
    target: string
    inputs: string[]
  }) => Promise<ModelFitDTO | null>
  transition: (modelId: string, status: ModelStatus) => Promise<void>
  selectModel: (modelId: string | null) => void
  clearError: () => void
}

export const useModelStore = create<ModelStore>((set) => ({
  models: [],
  fitting: false,
  transitioning: false,
  error: null,
  selectedModelId: null,

  loadModels: async () => {
    set({ error: null })
    try {
      const result = await listModels()
      set({ models: result.models, error: null })
    } catch (err) {
      set({ error: String(err) })
    }
  },

  fit: async (params) => {
    set({ fitting: true, error: null })
    try {
      const result = await fitModel(params)
      set((s) => ({ models: [...s.models, result], fitting: false }))
      return result
    } catch (err) {
      set({ fitting: false, error: String(err) })
      return null
    }
  },

  transition: async (modelId, status) => {
    set({ transitioning: true, error: null })
    try {
      const updated = await transitionModel(modelId, status)
      set((s) => ({
        models: s.models.map((m) => (m.model_id === modelId ? updated : m)),
        transitioning: false,
      }))
    } catch (err) {
      set({ transitioning: false, error: String(err) })
    }
  },

  selectModel: (modelId) => set({ selectedModelId: modelId }),
  clearError: () => set({ error: null }),
}))
