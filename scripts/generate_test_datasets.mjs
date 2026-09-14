import fs from 'node:fs'

const dir = new URL('../data/', import.meta.url)
const headers = ['lot','serial_no','datetime','machine','operator','part','input_temperature','input_voltage','input_pressure','input_speed','input_load','output_thickness','result']
const timeSeriesHeaders = ['measurement_id','datetime','input_temperature','input_voltage','input_pressure','input_speed','input_load','output_thickness','result']
const row = (prefix, i, y) => [prefix, `${prefix}-${String(i + 1).padStart(3, '0')}`, `2026-09-${String(1 + Math.floor(i / 8)).padStart(2, '0')} ${String(8 + (i % 8)).padStart(2, '0')}:00:00`, `Line-${i % 2 ? 'B' : 'A'}`, `O-0${(i % 3) + 1}`, `P-0${(i % 5) + 1}`, (82 + 0.08 * i + 0.7 * Math.sin(i / 5)).toFixed(3), (11.5 + 0.018 * i + 0.06 * Math.sin(i / 4)).toFixed(3), (3.05 + 0.004 * i).toFixed(3), (116 + 0.12 * i).toFixed(3), (64 + 0.12 * i).toFixed(3), y.toFixed(4), y >= 1.60 && y <= 1.65 ? 'OK' : 'NG']
const writeRows = (name, columns, rows) => fs.writeFileSync(new URL(name, dir), [columns, ...rows].map(r => r.join(',')).join('\n') + '\n')
const write = (name, rows) => writeRows(name, headers, rows)
const deepTimeSeriesRows = (prefix, length) => {
  let previousThickness = 1.618
  return Array.from({ length }, (_, i) => {
    const daily = 2 * Math.PI * i / 24
    const weekly = 2 * Math.PI * i / 168
    const temperature = 84.5 + 0.0025 * i + 0.8 * Math.sin(daily) + 0.2 * Math.sin(weekly)
    const voltage = 12 + 0.08 * Math.cos(daily + 0.4) + 0.02 * Math.sin(2 * Math.PI * i / 72)
    const pressure = 3.18 + 0.035 * Math.sin(2 * Math.PI * i / 12) + 0.00005 * i
    const speed = 120 + 3 * Math.sin(daily - 0.6) + 0.6 * Math.cos(2 * Math.PI * i / 48)
    const load = 68 + 2.2 * Math.cos(daily) + 0.5 * Math.sin(weekly)
    const processSignal = 1.618 + 0.000008 * i
      + 0.0012 * (temperature - 84.5)
      + 0.012 * (voltage - 12)
      + 0.018 * (pressure - 3.18)
      + 0.00022 * (speed - 120)
      + 0.00018 * (load - 68)
      + 0.0005 * Math.sin(weekly)
    const thickness = 0.68 * previousThickness + 0.32 * processSignal + 0.00018 * Math.sin(i * 1.71)
    previousThickness = thickness
    return [
      `${prefix}-${String(i + 1).padStart(4, '0')}`,
      new Date(Date.UTC(2026, 9, 1, i)).toISOString(),
      temperature.toFixed(4), voltage.toFixed(4), pressure.toFixed(4),
      speed.toFixed(4), load.toFixed(4), thickness.toFixed(6),
      thickness >= 1.60 && thickness <= 1.65 ? 'OK' : 'NG',
    ]
  })
}
const x = i => (i - 39.5) / 39.5
write('test_dataset_linear.csv', Array.from({ length: 60 }, (_, i) => row('LIN', i, 1.62 + 0.008 * x(i) + 0.0015 * Math.sin(i))))
write('test_dataset_quadratic.csv', Array.from({ length: 80 }, (_, i) => row('QUAD', i, 1.62 + 0.001 + 0.014 * x(i) ** 2 + 0.004 * x(i) + 0.0005 * Math.sin(i))))
write('test_dataset_interaction.csv', Array.from({ length: 80 }, (_, i) => row('INT', i, 1.62 + 0.006 * x(i) + 0.004 * Math.sin(i / 3) * Math.cos(i / 5) + 0.0005 * Math.sin(i))))
write('test_dataset_timeseries.csv', Array.from({ length: 45 }, (_, i) => row('TS', i, 1.62 + 0.004 * Math.sin(i / 3) + 0.00008 * i + 0.0005 * Math.sin(i / 9))))
writeRows('test_dataset_timeseries_transformer.csv', timeSeriesHeaders, deepTimeSeriesRows('TRF', 288))
writeRows('test_dataset_timeseries_tft.csv', timeSeriesHeaders, deepTimeSeriesRows('TFT', 432))
const grr = []
let measurementIndex = 1
for (let p = 0; p < 5; p++) for (let o = 0; o < 3; o++) for (let r = 0; r < 3; r++) {
  const repeatNoise = r * 0.01
  grr.push([`M-${String(measurementIndex++).padStart(3, '0')}`, `P-${String(p + 1).padStart(3, '0')}`, 'GRR-01', 'MC-01', 'ST-01', 'coating', `2026-09-${String(1 + p).padStart(2, '0')} ${String(8 + o).padStart(2, '0')}:${String(r * 10).padStart(2, '0')}:00`, `SG-${p + 1}`, (84 + p * 0.6 + o * 0.03 + repeatNoise).toFixed(3), (11.8 + p * 0.08 + o * 0.005 + repeatNoise * 0.01).toFixed(3), (3.1 + p * 0.025 + o * 0.002 + repeatNoise * 0.01).toFixed(3), (118 + p * 0.8 + o * 0.1 + repeatNoise).toFixed(3), (66 + p * 1.2 + o * 0.1 + repeatNoise).toFixed(3), (1.61 + p * 0.004 + o * 0.0008 + r * 0.0004).toFixed(4), 'OK', `O-0${o + 1}`])
}
fs.writeFileSync(new URL('test_dataset_grr.csv', dir), [['measurement_id','product_id','lot_id','machine_id','station_id','process_step','timestamp','subgroup_id','input_temperature','input_voltage','input_pressure','input_speed','input_load','output_thickness','result','operator'], ...grr].map(r => r.join(',')).join('\n') + '\n')
