import fs from 'node:fs'

const dir = new URL('../data/', import.meta.url)
const headers = ['lot','serial_no','datetime','machine','operator','part','input_temperature','input_voltage','input_pressure','input_speed','input_load','output_thickness','result']
const row = (prefix, i, y) => [prefix, `${prefix}-${String(i + 1).padStart(3, '0')}`, `2026-09-${String(1 + Math.floor(i / 8)).padStart(2, '0')} ${String(8 + (i % 8)).padStart(2, '0')}:00:00`, `Line-${i % 2 ? 'B' : 'A'}`, `O-0${(i % 3) + 1}`, `P-0${(i % 5) + 1}`, (82 + 0.08 * i + 0.7 * Math.sin(i / 5)).toFixed(3), (11.5 + 0.018 * i + 0.06 * Math.sin(i / 4)).toFixed(3), (3.05 + 0.004 * i).toFixed(3), (116 + 0.12 * i).toFixed(3), (64 + 0.12 * i).toFixed(3), y.toFixed(4), y >= 1.60 && y <= 1.65 ? 'OK' : 'NG']
const write = (name, rows) => fs.writeFileSync(new URL(name, dir), [headers, ...rows].map(r => r.join(',')).join('\n') + '\n')
const x = i => (i - 39.5) / 39.5
write('test_dataset_linear.csv', Array.from({ length: 60 }, (_, i) => row('LIN', i, 1.62 + 0.008 * x(i) + 0.0015 * Math.sin(i))))
write('test_dataset_quadratic.csv', Array.from({ length: 80 }, (_, i) => row('QUAD', i, 1.62 + 0.001 + 0.014 * x(i) ** 2 + 0.004 * x(i) + 0.0005 * Math.sin(i))))
write('test_dataset_interaction.csv', Array.from({ length: 80 }, (_, i) => row('INT', i, 1.62 + 0.006 * x(i) + 0.004 * Math.sin(i / 3) * Math.cos(i / 5) + 0.0005 * Math.sin(i))))
write('test_dataset_timeseries.csv', Array.from({ length: 45 }, (_, i) => row('TS', i, 1.62 + 0.004 * Math.sin(i / 3) + 0.00008 * i + 0.0005 * Math.sin(i / 9))))
const grr = []
let measurementIndex = 1
for (let p = 0; p < 5; p++) for (let o = 0; o < 3; o++) for (let r = 0; r < 3; r++) {
  const repeatNoise = r * 0.01
  grr.push([`M-${String(measurementIndex++).padStart(3, '0')}`, `P-${String(p + 1).padStart(3, '0')}`, 'GRR-01', 'MC-01', 'ST-01', 'coating', `2026-09-${String(1 + p).padStart(2, '0')} ${String(8 + o).padStart(2, '0')}:${String(r * 10).padStart(2, '0')}:00`, `SG-${p + 1}`, (84 + p * 0.6 + o * 0.03 + repeatNoise).toFixed(3), (11.8 + p * 0.08 + o * 0.005 + repeatNoise * 0.01).toFixed(3), (3.1 + p * 0.025 + o * 0.002 + repeatNoise * 0.01).toFixed(3), (118 + p * 0.8 + o * 0.1 + repeatNoise).toFixed(3), (66 + p * 1.2 + o * 0.1 + repeatNoise).toFixed(3), (1.61 + p * 0.004 + o * 0.0008 + r * 0.0004).toFixed(4), 'OK', `O-0${o + 1}`])
}
fs.writeFileSync(new URL('test_dataset_grr.csv', dir), [['measurement_id','product_id','lot_id','machine_id','station_id','process_step','timestamp','subgroup_id','input_temperature','input_voltage','input_pressure','input_speed','input_load','output_thickness','result','operator'], ...grr].map(r => r.join(',')).join('\n') + '\n')
