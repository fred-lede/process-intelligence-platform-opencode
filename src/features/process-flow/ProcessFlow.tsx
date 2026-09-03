import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Card, Button, Space, Alert, Tag, Input, Select,
  Form, message, Modal, Typography,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  CheckOutlined,
  WarningOutlined,
  ArrowRightOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  ApartmentOutlined,
} from '@ant-design/icons'
import {
  getFlowGraph,
  validateFlowGraph,
  createProcessNode,
  updateProcessNode,
  deleteProcessNode,
  getDatasets,
  type FlowGraph,
  type FlowNode,
  type FlowEdge,
  type FlowValidation,
} from '../../lib/engine'

const NODE_COLORS: Record<string, string> = {
  default: '#1677ff',
  laser_marking: '#722ed1',
  smt_printer: '#13c2c2',
  pick_place: '#fa8c16',
  reflow: '#eb2f96',
  aoi: '#2d8cf0',
  xray: '#52c41a',
  ict: '#faad14',
  pressfit: '#1890ff',
  fatp: '#73d13d',
  avl: '#eb8f45',
  final_test: '#8c52ff',
}

const NODE_WIDTH = 140
const NODE_HEIGHT = 52
const H_GAP = 200
const V_GAP = 80

export function computeLayout(nodes: FlowNode[], edges: FlowEdge[]) {
  const nodeMap = new Map(nodes.map(n => [n.process_node_id, n]))
  const adj = new Map<string, string[]>()
  const inDeg = new Map<string, number>()
  for (const n of nodes) {
    adj.set(n.process_node_id, [])
    inDeg.set(n.process_node_id, 0)
  }
  for (const e of edges) {
    if (nodeMap.has(e.from) && nodeMap.has(e.to)) {
      adj.get(e.from)!.push(e.to)
      inDeg.set(e.to, (inDeg.get(e.to) || 0) + 1)
    }
  }

  const layers: Map<string, number> = new Map()
  const queue: string[] = []
  for (const n of nodes) {
    if ((inDeg.get(n.process_node_id) || 0) === 0) {
      queue.push(n.process_node_id)
      layers.set(n.process_node_id, 0)
    }
  }
  while (queue.length > 0) {
    const cur = queue.shift()!
    for (const nb of adj.get(cur) || []) {
      layers.set(nb, Math.max(layers.get(nb) ?? 0, (layers.get(cur) ?? 0) + 1))
      const newDeg = (inDeg.get(nb) || 1) - 1
      inDeg.set(nb, newDeg)
      if (newDeg <= 0) queue.push(nb)
    }
  }
  // Any remaining (cycle) nodes get layer 0
  for (const n of nodes) {
    if (!layers.has(n.process_node_id)) layers.set(n.process_node_id, 0)
  }

  const layerGroups = new Map<number, string[]>()
  for (const n of nodes) {
    const l = layers.get(n.process_node_id) ?? 0
    if (!layerGroups.has(l)) layerGroups.set(l, [])
    layerGroups.get(l)!.push(n.process_node_id)
  }

  const layout = new Map<string, { x: number; y: number }>()
  let maxX = 0
  for (const [layer, ids] of layerGroups) {
    const count = ids.length
    const totalH = (count - 1) * V_GAP
    const startY = -totalH / 2
    for (let i = 0; i < count; i++) {
      layout.set(ids[i], {
        x: layer * H_GAP,
        y: startY + i * V_GAP,
      })
    }
    maxX = Math.max(maxX, layer * H_GAP + NODE_WIDTH)
  }
  return { layout, maxX, maxY: Math.max(...Array.from(layout.values()).map(p => p.y)) + NODE_HEIGHT / 2 }
}

export default function ProcessFlow() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()
  const [graph, setGraph] = useState<FlowGraph>({ nodes: [], edges: [] })
  const [validation, setValidation] = useState<FlowValidation | null>(null)
  const [loading, setLoading] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [form] = Form.useForm()

  const selectedNode = graph.nodes.find(n => n.process_node_id === selectedNodeId) || null
  const [datasets, setDatasets] = useState<Array<{ value: string; label: string }>>([])
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [viewportSize, setViewportSize] = useState({ w: 900, h: 500 })
  const didInitialFit = useRef(false)
  const panDrag = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null)
  const [dragging, setDragging] = useState<{ id: string; startX: number; startY: number; origX: number; origY: number } | null>(null)
  const [connectDraft, setConnectDraft] = useState<{ fromId: string; sx: number; sy: number } | null>(null)
  const [connectCursor, setConnectCursor] = useState<{ x: number; y: number } | null>(null)
  const [hoverTarget, setHoverTarget] = useState<{ id: string; port: 'in' | 'out' } | null>(null)

  const clientToWorld = (clientX: number, clientY: number) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    const sx = clientX - rect.left
    const sy = clientY - rect.top
    return { x: (sx - pan.x) / zoom, y: (sy - pan.y) / zoom }
  }

  const startConnect = (e: React.PointerEvent, fromId: string) => {
    e.stopPropagation()
    const w = clientToWorld(e.clientX, e.clientY)
    setConnectDraft({ fromId, sx: w.x, sy: w.y })
    setConnectCursor({ x: w.x, y: w.y })
    setHoverTarget(null)
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
  }

  const startNodeDrag = (e: React.PointerEvent, node: FlowNode) => {
    e.stopPropagation()
    setDragging({
      id: node.process_node_id,
      startX: e.clientX, startY: e.clientY,
      origX: node.x ?? 0, origY: node.y ?? 0,
    })
    ;(e.target as Element).closest('g')?.setPointerCapture?.(e.pointerId)
  }

  const persistNodePosition = async () => {
    if (!dragging) return
    const node = graph.nodes.find(n => n.process_node_id === dragging.id)
    if (!node) return
    const original = { x: dragging.origX, y: dragging.origY }
    try {
      await updateProcessNode(node.process_node_id, { x: node.x, y: node.y })
    } catch {
      setGraph(prev => ({
        ...prev,
        nodes: prev.nodes.map(n =>
          n.process_node_id === node.process_node_id ? { ...n, ...original } : n,
        ),
      }))
      messageApi.error('Failed to save position')
    }
  }

  useEffect(() => { void loadData() }, [])

  useEffect(() => {
    void getDatasets().then(regs => setDatasets(
      regs.map(r => ({ value: r.dataset_id, label: r.source_file || r.dataset_id })),
    )).catch(() => {})
  }, [])

  const worldBounds = useMemo(() => {
    const pts = graph.nodes.map(n => ({
      x: n.x ?? 0, y: n.y ?? 0, w: NODE_WIDTH, h: NODE_HEIGHT,
    }))
    if (pts.length === 0) return { minX: 0, minY: 0, maxX: 600, maxY: 300 }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const p of pts) {
      minX = Math.min(minX, p.x); minY = Math.min(minY, p.y)
      maxX = Math.max(maxX, p.x + p.w); maxY = Math.max(maxY, p.y + p.h)
    }
    return { minX, minY, maxX, maxY }
  }, [graph.nodes])

  const miniW = 140, miniH = 96
  const miniScale = Math.min(
    (miniW - 12) / (worldBounds.maxX - worldBounds.minX || 1),
    (miniH - 12) / (worldBounds.maxY - worldBounds.minY || 1),
  )

  const fitView = () => {
    const pad = 40
    const { minX, minY, maxX, maxY } = worldBounds
    const bw = maxX - minX || 1, bh = maxY - minY || 1
    const z = Math.min(
      (viewportSize.w - 2 * pad) / bw,
      (viewportSize.h - 2 * pad) / bh,
      1.5,
    )
    setZoom(Math.max(0.5, z))
    setPan({
      x: (viewportSize.w - bw * z) / 2 - minX * z,
      y: (viewportSize.h - bh * z) / 2 - minY * z,
    })
  }

  const loadData = async () => {
    setLoading(true)
    try {
      const [g, v] = await Promise.all([getFlowGraph(), validateFlowGraph()])
      setGraph(g)
      setValidation(v)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  const handleAdd = async () => {
    try {
      const values = await form.validateFields()
      await createProcessNode({
        display_name: values.display_name,
        node_type: values.node_type,
        sequence_or_edges: [],
        rework_policy: values.rework_policy || 'default',
      })
      setAddModalOpen(false)
      form.resetFields()
      await loadData()
      messageApi.success(t('processFlow.added'))
    } catch {
      messageApi.error(t('processFlow.addError'))
    }
  }

  const handleDelete = async (nodeId: string) => {
    try {
      await deleteProcessNode(nodeId)
      if (selectedNodeId === nodeId) setSelectedNodeId(null)
      await loadData()
      messageApi.success(t('processFlow.deleted'))
    } catch {
      messageApi.error(t('processFlow.deleteError'))
    }
  }

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const measure = () => setViewportSize({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (!didInitialFit.current && graph.nodes.length > 0) {
      didInitialFit.current = true
      fitView()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph.nodes.length])

  const handleBackgroundPointerDown = (e: React.PointerEvent) => {
    const t = e.target as Element
    if (t.closest('[data-node]') || t.closest('[data-port]')) return
    panDrag.current = { sx: e.clientX, sy: e.clientY, px: pan.x, py: pan.y }
    ;(e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId)
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (connectDraft) {
      const w = clientToWorld(e.clientX, e.clientY)
      setConnectCursor({ x: w.x, y: w.y })
      const el = document.elementFromPoint(e.clientX, e.clientY) as Element | null
      const portEl = el?.closest?.('[data-port]') as HTMLElement | null
      if (portEl && portEl.dataset.nodeId && portEl.dataset.nodeId !== connectDraft.fromId) {
        setHoverTarget({ id: portEl.dataset.nodeId, port: (portEl.dataset.port as 'in' | 'out') || 'in' })
      } else {
        setHoverTarget(null)
      }
      return
    }
    if (dragging) {
      const dx = (e.clientX - dragging.startX) / zoom
      const dy = (e.clientY - dragging.startY) / zoom
      setGraph(prev => ({
        ...prev,
        nodes: prev.nodes.map(n =>
          n.process_node_id === dragging.id
            ? { ...n, x: Math.round(dragging.origX + dx), y: Math.round(dragging.origY + dy) }
            : n,
        ),
      }))
      return
    }
    if (panDrag.current) {
      const dx = e.clientX - panDrag.current.sx
      const dy = e.clientY - panDrag.current.sy
      setPan({ x: panDrag.current.px + dx, y: panDrag.current.py + dy })
    }
  }

  const handlePointerUp = (_e: React.PointerEvent) => {
    if (connectDraft) {
      if (hoverTarget && hoverTarget.id !== connectDraft.fromId) {
        void handleConnect(connectDraft.fromId, hoverTarget.id)
      }
      setConnectDraft(null); setConnectCursor(null); setHoverTarget(null)
      return
    }
    if (dragging) {
      void persistNodePosition()
      setDragging(null)
      panDrag.current = null
      return
    }
    panDrag.current = null
  }

  const handleWheel = (e: React.WheelEvent) => {
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
    const sx = e.clientX - rect.left
    const sy = e.clientY - rect.top
    const factor = e.deltaY < 0 ? 1.1 : 0.9
    const newZoom = Math.min(2, Math.max(0.5, zoom * factor))
    setPan({
      x: sx - (sx - pan.x) * (newZoom / zoom),
      y: sy - (sy - pan.y) * (newZoom / zoom),
    })
    setZoom(newZoom)
  }

  const handleConnect = async (fromId: string, toId: string, condition?: string) => {
    if (fromId === toId) return
    const node = graph.nodes.find(n => n.process_node_id === fromId)
    if (!node) return
    const edges = [...(node.sequence_or_edges || [])]
    // Remove existing edge to same target
    const filtered = edges.filter((e: FlowEdge) => e.to !== toId)
    const edge: FlowEdge = { from: fromId, to: toId, condition: condition || '' }
    filtered.push(edge)
    try {
      await updateProcessNode(fromId, { sequence_or_edges: filtered })
      await loadData()
    } catch {
      messageApi.error(t('processFlow.connectError'))
    }
  }

  const handleDisconnect = async (fromId: string, toId: string) => {
    const node = graph.nodes.find(n => n.process_node_id === fromId)
    if (!node) return
    const edges = (node.sequence_or_edges || []).filter(e => e.to !== toId)
    try {
      await updateProcessNode(fromId, { sequence_or_edges: edges })
      await loadData()
    } catch {
      messageApi.error(t('processFlow.disconnectError'))
    }
  }

  const saveMapping = async (field: string, vals: string[]) => {
    if (!selectedNode) return
    try {
      await updateProcessNode(selectedNode.process_node_id, { [field]: vals } as Record<string, unknown>)
      setGraph(prev => ({
        ...prev,
        nodes: prev.nodes.map(n =>
          n.process_node_id === selectedNode.process_node_id ? { ...n, [field]: vals } : n,
        ),
      }))
    } catch {
      messageApi.error(t('processFlow.saveError'))
    }
  }

  const handleAutoLayout = async () => {
    try {
      const { layout: newLayout } = computeLayout(graph.nodes, graph.edges)
      const updated = graph.nodes.map(n => {
        const p = newLayout.get(n.process_node_id)
        return p ? { ...n, x: p.x, y: p.y } : n
      })
      setGraph(prev => ({ ...prev, nodes: updated }))
      for (const u of updated) {
        await updateProcessNode(u.process_node_id, { x: u.x, y: u.y })
      }
      const padding = 40
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
      for (const u of updated) {
        minX = Math.min(minX, u.x ?? 0); minY = Math.min(minY, u.y ?? 0)
        maxX = Math.max(maxX, (u.x ?? 0) + NODE_WIDTH); maxY = Math.max(maxY, (u.y ?? 0) + NODE_HEIGHT)
      }
      const bw = (maxX - minX) || 1, bh = (maxY - minY) || 1
      const z = Math.min((viewportSize.w - 2 * padding) / bw, (viewportSize.h - 2 * padding) / bh, 1.5)
      setZoom(Math.max(0.5, z))
      setPan({ x: (viewportSize.w - bw * z) / 2 - minX * z, y: (viewportSize.h - bh * z) / 2 - minY * z })
      messageApi.success('Layout applied')
    } catch {
      messageApi.error('Failed to apply layout')
    }
  }

  const portColor = '#1677ff'
  const svga = (cx: number, cy: number, tx: number, ty: number) => {
    const dx = tx - cx
    const cx1 = cx + dx * 0.5
    const cy1 = cy
    const cx2 = tx - dx * 0.5
    const cy2 = ty
    return `M${cx},${cy} C${cx1},${cy1} ${cx2},${cy2} ${tx},${ty}`
  }

  const nodeCenters = new Map<string, { x: number; y: number }>()
  for (const node of graph.nodes) {
    nodeCenters.set(node.process_node_id, {
      x: (node.x ?? 0) + NODE_WIDTH / 2,
      y: (node.y ?? 0) + NODE_HEIGHT / 2,
    })
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      {contextHolder}

      {/* Toolbar */}
      <Card size="small" style={{ marginBottom: 0 }}>
        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModalOpen(true)}>
            {t('processFlow.addNode')}
          </Button>
          <Button icon={<CheckOutlined />} onClick={() => { void loadData() }} loading={loading}>
            {t('processFlow.refresh')}
          </Button>
          <Space.Compact>
            <Button icon={<ZoomInOutlined />} onClick={() => setZoom(z => Math.min(2, z * 1.25))} />
            <Button onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</Button>
            <Button icon={<ZoomOutOutlined />} onClick={() => setZoom(z => Math.max(0.5, z * 0.8))} />
            <Button icon={<FullscreenOutlined />} onClick={() => fitView()} title={t('processFlow.zoomFit')} />
          </Space.Compact>
          <Button icon={<ApartmentOutlined />} onClick={() => { void handleAutoLayout() }}>
            {t('processFlow.autoLayout')}
          </Button>
          {validation && (
            <Space>
              {validation.valid
                ? <Tag color="success">{t('processFlow.valid')}</Tag>
                : <Tag color="error">{t('processFlow.invalid')}</Tag>
              }
              {validation && validation.warnings.map((w: string, i: number) => (
                <Tag key={i} color="warning" icon={<WarningOutlined />}>{w}</Tag>
              ))}
            </Space>
          )}
        </Space>
      </Card>

      {/* Diagram + Panel */}
      <Space style={{ width: '100%' }} size={16}>
        {/* SVG Diagram */}
        <Card
          size="small"
          title={t('processFlow.diagram')}
          style={{ flex: 1, minHeight: 400 }}
          bodyStyle={{ padding: 0, overflow: 'hidden' }}
        >
          {graph.nodes.length === 0 ? (
            <Alert
              type="info"
              showIcon
              message={t('processFlow.noNodes')}
              description={t('processFlow.noNodesDesc')}
              style={{ margin: 24 }}
            />
          ) : (
            <div ref={containerRef} style={{ width: '100%', height: 500, overflow: 'hidden' }}>
              <svg
                ref={svgRef}
                width={viewportSize.w}
                height={viewportSize.h}
                style={{ background: '#FAFAFA', display: 'block', touchAction: 'none' }}
                onPointerDown={handleBackgroundPointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onWheel={handleWheel}
              >
                <defs>
                  <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                    <path d="M0,0 L8,3 L0,6 Z" fill="#8c8c8c" />
                  </marker>
                </defs>
                <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
              {/* Edges */}
              {graph.edges.map((e, i) => {
                const from = nodeCenters.get(e.from)
                const to = nodeCenters.get(e.to)
                if (!from || !to) return null
                const fromRight = true
                const toLeft = false
                const sx = fromRight ? from.x + NODE_WIDTH / 2 : from.x - NODE_WIDTH / 2
                const sy = from.y
                const ex = toLeft ? to.x - NODE_WIDTH / 2 : to.x + NODE_WIDTH / 2
                const ey = to.y
                return (
                  <g key={i}>
                    <path
                      d={svga(sx, sy, ex, ey)}
                      fill="none"
                      stroke="#8c8c8c"
                      strokeWidth={1.5}
                      markerEnd="url(#arrow)"
                    />
                    {e.condition && (
                      <text x={(sx + ex) / 2} y={(sy + ey) / 2 - 6}
                        fontSize={10} fill="#8c8c8c" textAnchor="middle">
                        {e.condition}
                      </text>
                    )}
                  </g>
                )
              })}
              {connectDraft && connectCursor && (() => {
                const from = nodeCenters.get(connectDraft.fromId)
                if (!from) return null
                return (
                  <path
                    d={svga(from.x + NODE_WIDTH / 2, from.y, connectCursor.x, connectCursor.y)}
                    fill="none" stroke="#1677ff" strokeWidth={2} strokeDasharray="4 2"
                    markerEnd="url(#arrow)" opacity={0.7}
                  />
                )
              })()}
              {/* Nodes */}
              {graph.nodes.map(node => {
                const pos = { x: node.x ?? 0, y: node.y ?? 0 }
                const isSelected = selectedNodeId === node.process_node_id
                const color = NODE_COLORS[node.node_type] || NODE_COLORS.default
                return (
                  <g
                    key={node.process_node_id}
                    data-node={node.process_node_id}
                    onClick={() => { if (!dragging) setSelectedNodeId(node.process_node_id) }}
                    onPointerDown={(e) => startNodeDrag(e, node)}
                    style={{ cursor: 'grab' }}
                  >
                    {/* Selection ring */}
                    {isSelected && (
                      <rect
                        x={pos.x - 3} y={pos.y - 3}
                        width={NODE_WIDTH + 6} height={NODE_HEIGHT + 6}
                        rx={8} ry={8}
                        fill="none" stroke={portColor} strokeWidth={2}
                        strokeDasharray="4 2"
                      />
                    )}
                    {/* Node body */}
                    <rect
                      x={pos.x} y={pos.y}
                      width={NODE_WIDTH} height={NODE_HEIGHT}
                      rx={6} ry={6}
                      fill="#fff"
                      stroke={color}
                      strokeWidth={isSelected ? 2 : 1.5}
                    />
                    {/* Color bar */}
                    <rect
                      x={pos.x} y={pos.y}
                      width={4} height={NODE_HEIGHT}
                      rx={2} ry={2}
                      fill={color}
                    />
                    {/* Label */}
                    <text
                      x={pos.x + NODE_WIDTH / 2} y={pos.y + 22}
                      textAnchor="middle" fontSize={12} fontWeight={600} fill="#1f2937">
                      {node.display_name}
                    </text>
                    <text
                      x={pos.x + NODE_WIDTH / 2} y={pos.y + 38}
                      textAnchor="middle" fontSize={10} fill="#8c8c8c">
                      {node.node_type}
                    </text>
                    {/* Connect ports */}
                    <circle data-node-id={node.process_node_id} data-port="out"
                      cx={pos.x + NODE_WIDTH} cy={pos.y + NODE_HEIGHT / 2} r={5}
                      fill={portColor} stroke="#fff" strokeWidth={1.5}
                      onPointerDown={(e) => startConnect(e, node.process_node_id)}
                      onPointerUp={(e) => e.stopPropagation()}
                      style={{ cursor: 'crosshair' }}
                    />
                    <circle data-node-id={node.process_node_id} data-port="in"
                      cx={pos.x} cy={pos.y + NODE_HEIGHT / 2} r={5}
                      fill={portColor} stroke="#fff" strokeWidth={1.5}
                      onPointerDown={(e) => startConnect(e, node.process_node_id)}
                      onPointerUp={(e) => e.stopPropagation()}
                      style={{ cursor: 'crosshair' }}
                    />
                  </g>
                )
              })}
                </g>
                {graph.nodes.length > 0 && (() => {
                  const visibleX = -pan.x / zoom
                  const visibleY = -pan.y / zoom
                  return (
                    <g transform={`translate(${viewportSize.w - miniW - 12}, ${viewportSize.h - miniH - 12})`} opacity={0.95}>
                      <rect x={0} y={0} width={miniW} height={miniH} rx={6} fill="#ffffff" stroke="#d9d9d9" />
                      <g transform={`translate(6,6) scale(${miniScale})`}>
                        {graph.nodes.map(n => (
                          <rect
                            key={n.process_node_id}
                            x={(n.x ?? 0) - worldBounds.minX}
                            y={(n.y ?? 0) - worldBounds.minY}
                            width={NODE_WIDTH}
                            height={NODE_HEIGHT}
                            rx={2}
                            fill={NODE_COLORS[n.node_type] || NODE_COLORS.default}
                          />
                        ))}
                      </g>
                      <rect
                        x={6 + (visibleX - worldBounds.minX) * miniScale}
                        y={6 + (visibleY - worldBounds.minY) * miniScale}
                        width={(viewportSize.w / zoom) * miniScale}
                        height={(viewportSize.h / zoom) * miniScale}
                        fill="none" stroke="#1677ff" strokeWidth={1.5}
                      />
                    </g>
                  )
                })()}
              </svg>
            </div>
          )}
        </Card>

        {/* Properties Panel */}
        <Card
          size="small"
          title={t('processFlow.properties')}
          style={{ width: 280, flexShrink: 0 }}
        >
          {selectedNode ? (
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <Typography.Text strong>{selectedNode.display_name}</Typography.Text>
              <Tag color="blue">{selectedNode.node_type}</Tag>
              <div style={{ fontSize: 12, color: '#6b7280' }}>
                {t('processFlow.reworkPolicy')}: {selectedNode.rework_policy}
              </div>
              {(selectedNode.sequence_or_edges || []).length > 0 && (
                <div style={{ fontSize: 12 }}>
                  <strong>{t('processFlow.outputs')}:</strong>
                  <div style={{ marginTop: 4 }}>
                    {selectedNode.sequence_or_edges.map((e, i) => {
                      const target = graph.nodes.find(n => n.process_node_id === e.to)
                      return (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                          <ArrowRightOutlined style={{ fontSize: 10, color: '#8c8c8c' }} />
                          <span style={{ fontSize: 11 }}>{target?.display_name || e.to}</span>
                          {e.condition && (
                            <Tag style={{ fontSize: 9, marginLeft: 4 }}>{e.condition}</Tag>
                          )}
                          <Button
                            type="text"
                            size="small"
                            icon={<DeleteOutlined />}
                            style={{ marginLeft: 'auto', padding: '0 2px' }}
                            onClick={() => { void handleDisconnect(selectedNode.process_node_id, e.to) }}
                          />
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
              <div style={{ marginTop: 12, fontSize: 12, fontWeight: 600 }}>
                {t('processFlow.dataMapping')}
              </div>
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.inputDataSources')}</span>
              <Select mode="multiple" allowClear style={{ width: '100%' }}
                placeholder={t('processFlow.selectDataSources')}
                options={datasets}
                value={selectedNode.input_data_sources || []}
                onChange={vals => void saveMapping('input_data_sources', vals as string[])}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.outputDataSources')}</span>
              <Select mode="multiple" allowClear style={{ width: '100%' }}
                placeholder={t('processFlow.selectDataSources')}
                options={datasets}
                value={selectedNode.output_data_sources || []}
                onChange={vals => void saveMapping('output_data_sources', vals as string[])}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.controlParameters')}</span>
              <Select mode="tags" style={{ width: '100%' }}
                placeholder={t('processFlow.typeOrSelect')}
                value={selectedNode.in_control_parameters || []}
                onChange={vals => void saveMapping('in_control_parameters', vals as string[])}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.qualityOutputs')}</span>
              <Select mode="tags" style={{ width: '100%' }}
                placeholder={t('processFlow.typeOrSelect')}
                value={selectedNode.out_quality_outputs || []}
                onChange={vals => void saveMapping('out_quality_outputs', vals as string[])}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>{t('processFlow.machineMapping')}</span>
              <Select mode="tags" style={{ width: '100%' }}
                placeholder={t('processFlow.typeOrSelect')}
                value={selectedNode.machine_mapping || []}
                onChange={vals => void saveMapping('machine_mapping', vals as string[])}
              />
              {/* Connect to node selector */}
              <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
                {t('processFlow.connectTo')}:
              </div>
              <Select
                mode="multiple"
                placeholder={t('processFlow.selectNodes')}
                options={graph.nodes
                  .filter(n => n.process_node_id !== selectedNode.process_node_id)
                  .map(n => ({ value: n.process_node_id, label: n.display_name }))
                }
                style={{ width: '100%' }}
                onChange={vals => {
                  const current = new Set((selectedNode.sequence_or_edges || []).map(e => e.to))
                  for (const id of current) {
                    if (!vals.includes(id)) void handleDisconnect(selectedNode.process_node_id, id)
                  }
                  for (const id of vals) {
                    if (!current.has(id)) void handleConnect(selectedNode.process_node_id, id)
                  }
                }}
              />
              <Button
                danger
                size="small"
                icon={<DeleteOutlined />}
                style={{ marginTop: 8 }}
                onClick={() => {
                  Modal.confirm({
                    title: t('processFlow.confirmDelete'),
                    onOk: () => { void handleDelete(selectedNode.process_node_id) },
                  })
                }}
              >
                {t('processFlow.deleteNode')}
              </Button>
            </Space>
          ) : (
            <Alert
              type="info"
              showIcon
              message={t('processFlow.selectNode')}
              description={t('processFlow.selectNodeDesc')}
            />
          )}
        </Card>
      </Space>

      {/* Add Node Modal */}
      <Modal
        title={t('processFlow.addNode')}
        open={addModalOpen}
        onOk={handleAdd}
        onCancel={() => setAddModalOpen(false)}
        okText={t('processFlow.add')}
        cancelText={t('common.cancel')}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="display_name" label={t('processFlow.nodeName')} rules={[{ required: true }]}>
            <Input placeholder={t('processFlow.nodeNamePlaceholder')} />
          </Form.Item>
          <Form.Item name="node_type" label={t('processFlow.nodeType')} rules={[{ required: true }]}>
            <Input placeholder={t('processFlow.nodeTypePlaceholder')} />
          </Form.Item>
          <Form.Item name="rework_policy" label={t('processFlow.reworkPolicy')} initialValue="default">
            <Select options={[
              { value: 'default', label: 'Default' },
              { value: 'rework', label: 'Rework' },
              { value: 'scrap', label: 'Scrap' },
              { value: 'hold', label: 'Hold' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
