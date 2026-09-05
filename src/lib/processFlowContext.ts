import { useProcessFlowNavStore, type ProcessNodeContext } from '../stores/processFlowNavStore'
import { getFlowGraph, type FlowNode } from './engine'

export interface NodeContextResult {
  context: ProcessNodeContext | undefined
  node: FlowNode | null
  dataSourceLoaded: boolean
}

export function consumeNodeContext(): ProcessNodeContext | undefined {
  return useProcessFlowNavStore.getState().consume()
}

export async function findNodeById(nodeId: string): Promise<FlowNode | null> {
  try {
    const graph = await getFlowGraph()
    return graph.nodes.find((n) => n.process_node_id === nodeId) ?? null
  } catch {
    return null
  }
}

export function dataSourceLoaded(dataSourceIds: string[] | undefined, currentDatasetId: string | undefined): boolean {
  if (!dataSourceIds || dataSourceIds.length === 0) return true
  return dataSourceIds.includes(currentDatasetId ?? '')
}