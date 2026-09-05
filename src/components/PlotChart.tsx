import { Suspense, lazy } from 'react'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const PlotLazy = lazy(() => import('react-plotly.js'))

export default function PlotChart(props: any) {
  return (
    <Suspense fallback={null}>
      <PlotLazy {...props} />
    </Suspense>
  )
}
