import { create } from 'zustand'

interface AIStoreState {
  refreshKey: number
  refreshHealth: () => void
}

export const useAIStore = create<AIStoreState>((set) => ({
  refreshKey: 0,
  refreshHealth: () => set((s) => ({ refreshKey: s.refreshKey + 1 })),
}))
