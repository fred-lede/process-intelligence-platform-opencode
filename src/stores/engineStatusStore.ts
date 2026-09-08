import { create } from 'zustand'

interface EngineActivityState {
  assistantBusy: boolean
  setAssistantBusy: (busy: boolean) => void
}

export const useEngineActivityStore = create<EngineActivityState>((set) => ({
  assistantBusy: false,
  setAssistantBusy: (assistantBusy) => set({ assistantBusy }),
}))
