import { Suspense, lazy } from 'react'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const PlotLazy = lazy(() => import('react-plotly.js'))

export default function PlotChart(props: any) {
  return (
    <Suspense fallback={null}>
      <PlotLazy {...props} useResizeHandler style={{ width: '100%', ...(props.style ?? {}) }} layout={{ autosize: true, ...(props.layout ?? {}) }} />
    </Suspense>
  )
}
