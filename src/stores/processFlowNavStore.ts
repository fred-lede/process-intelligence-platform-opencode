import { create } from 'zustand'
import type { AppTab } from '../types'

export interface ProcessNodeContext {
  nodeId: string
  displayName: string
  field?: string
  dataSourceIds?: string[]
}

interface ProcessFlowNavState {
  pending: { targetTab: AppTab; context: ProcessNodeContext } | null
  navigate: (targetTab: AppTab, context: ProcessNodeContext) => void
  consume: () => ProcessNodeContext | undefined
}

export const useProcessFlowNavStore = create<ProcessFlowNavState>((set) => ({
  pending: null,
  navigate: (targetTab, context) => set({ pending: { targetTab, context } }),
  consume: () => {
    let ctx: ProcessNodeContext | undefined
    set((s) => {
      ctx = s.pending?.context
      return { pending: null }
    })
    return ctx
  },
}))