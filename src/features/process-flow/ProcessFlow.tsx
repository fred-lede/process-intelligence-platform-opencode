import { useEffect, useState } from 'react'
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
} from '@ant-design/icons'
import {
  getFlowGraph,
  validateFlowGraph,
  createProcessNode,
  updateProcessNode,
  deleteProcessNode,
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

function computeLayout(nodes: FlowNode[], edges: FlowEdge[]) {
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
  const { layout, maxX, maxY } = computeLayout(graph.nodes, graph.edges)

  useEffect(() => { void loadData() }, [])

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
  for (const [id, pos] of layout) {
    nodeCenters.set(id, { x: pos.x + NODE_WIDTH / 2, y: pos.y + NODE_HEIGHT / 2 })
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
          bodyStyle={{ padding: 0, overflow: 'auto' }}
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
            <svg
              width={Math.max(maxX + NODE_WIDTH + 80, 600)}
              height={Math.max(maxY * 2 + NODE_HEIGHT + 80, 300)}
              style={{ background: '#FAFAFA', display: 'block' }}
            >
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                  <path d="M0,0 L8,3 L0,6 Z" fill="#8c8c8c" />
                </marker>
              </defs>
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
              {/* Nodes */}
              {graph.nodes.map(node => {
                const pos = layout.get(node.process_node_id)
                if (!pos) return null
                const isSelected = selectedNodeId === node.process_node_id
                const color = NODE_COLORS[node.node_type] || NODE_COLORS.default
                return (
                  <g
                    key={node.process_node_id}
                    onClick={() => setSelectedNodeId(node.process_node_id)}
                    style={{ cursor: 'pointer' }}
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
                    <circle cx={pos.x + NODE_WIDTH} cy={pos.y + NODE_HEIGHT / 2} r={5}
                      fill={portColor} stroke="#fff" strokeWidth={1.5}
                      onClick={(e: React.MouseEvent) => { e.stopPropagation() }}
                      style={{ cursor: 'crosshair' }}
                    />
                    <circle cx={pos.x} cy={pos.y + NODE_HEIGHT / 2} r={5}
                      fill={portColor} stroke="#fff" strokeWidth={1.5}
                      onClick={(e: React.MouseEvent) => { e.stopPropagation() }}
                      style={{ cursor: 'crosshair' }}
                    />
                  </g>
                )
              })}
            </svg>
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
