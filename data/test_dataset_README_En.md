# Preloaded Test Data Guide

**Languages:** [繁體中文](test_dataset_README.md) · [English](test_dataset_README_En.md)

## File: `data/test_dataset.csv`

### Column definitions

| Column | Role/type | Example | Description |
|---|---|---|---|
| lot | Categorical | L240901-A | Production lot |
| serial_no | Categorical | SNC-0001 | Product serial number |
| datetime | Timestamp | 2026-09-01 08:07:00 | Production timestamp |
| machine | Categorical | Line-A / Line-B | Production line |
| operator | Categorical | O-01 / O-02 / O-03 | Operator identifier |
| part | Categorical | P-01 to P-05 | Part identifier |
| input_temperature | Numeric input | 81.84 | Process temperature (°C) |
| input_voltage | Numeric input | 11.355 | Supply voltage (V) |
| input_pressure | Numeric input | 3.058 | Process pressure (MPa) |
| input_speed | Numeric input | 116.9 | Speed (RPM) |
| input_load | Numeric input | 65.53 | Load (N) |
| output_thickness | Numeric output | 1.6177 | Finished thickness (mm) |
| result | Binary output | OK / NG | Quality result |

### Data characteristics

- 60 rows
- 5 numeric inputs: `input_temperature`, `input_voltage`, `input_pressure`, `input_speed`, `input_load`
- 1 continuous output: `output_thickness`
- 1 binary label: `result` (OK/NG)
- 6 categorical or identifier fields: `lot`, `serial_no`, `datetime`, `machine`, `operator`, `part`

### Supported model tests

| Model | Target | Purpose |
|---|---|---|
| `doe_linear` | `output_thickness` | Linear DOE, at least 3 inputs |
| `doe_quadratic` | `output_thickness` | Quadratic DOE with interaction terms |
| `random_forest` | `output_thickness` | Nonlinear tree model |
| `xgboost` | `output_thickness` | High-dimensional boosting |
| `lightgbm` | `output_thickness` | Efficient boosting |
| `residual_hybrid` | `output_thickness` | DOE plus RF residual model |
| `logistic_regression` | `result` | Binary OK/NG classification |
| `weibull_regression` | `output_thickness` | Reliability/lifetime analysis |

## Recommended test flow (choose the scenario file)

### Recommended sample sizes

- General analysis: at least 30 rows.
- Linear DOE: about 10–15 rows per input (roughly 50–75 rows for five inputs).
- Quadratic DOE or interactions: 60–100+ rows overall.
- GRR: at least 5 parts × 3 operators × 2–3 repeated measurements.
- Time series/SPC: use at least 30 ordered observations where possible.

1. **Import data**: Open Data Import, upload `test_dataset.csv` as the baseline, then switch to the scenario file required by the test matrix. Assign the five inputs, `output_thickness` as output, and `result` as the quality label.
2. **Define the process**: Set `output_thickness` limits to LSL=1.60 and USL=1.65. Optionally enter LCL/UCL or enable automatic 3-sigma limits.
3. **Fit models**: In Model Center, compare linear/quadratic DOE, tree, boosting, hybrid, logistic, or Weibull models according to the target.
4. **Validate**: Run full validation and review the model comparison table (R², RMSE, AUC, shape_k, AIC), interaction heatmap, and experiment recommendations.

### Scenario files and test matrix

| File | Start page | Main validation |
|---|---|---|
| `test_dataset.csv` | Data Import | End-to-end baseline |
| `test_dataset_linear.csv` | Model Center | Linear DOE and interactive prediction |
| `test_dataset_quadratic.csv` | Model Center | Linear versus quadratic DOE |
| `test_dataset_interaction.csv` | Model Center | Interaction, SHAP, sensitivity, and effect size |
| `test_dataset_quality_issues.csv` | Data Import | Quality warnings and readiness |
| `test_dataset_grr.csv` | Exploration - GRR | EV, AV, and %GRR |
| `test_dataset_timeseries.csv` | Exploration - Time Series | Trend, cycle, autocorrelation, and features |
| `test_dataset_out_of_spec.csv` | Process Definition / SPC / Simulation | Specification violations and NG risk |

### Expected results

- Linear and quadratic DOE can be compared directly; the quadratic fixture contains controlled curvature that the quadratic model should capture.
- With 60–80 rows, coefficients and simulation percentiles should be more stable than with small fixtures.
- Logistic regression can be evaluated on `result` (the baseline has approximately 2% NG).
- Weibull regression can estimate lifetime-related parameters when its assumptions are met.

### Advanced tests

- General/DOE files: change `input_temperature=95` and inspect the predicted `output_thickness`.
- General/DOE files: select a fitted model and run 10,000 Monte Carlo simulations.
- General/time-series/out-of-spec files: plot SPC charts for `input_temperature` or `output_thickness` and inspect outliers.
- GRR file: assign measurement, part, and operator columns, then run GRR.

## Scenario test data

These files are internal test fixtures, not user data-collection templates. General scenarios use the 13-column CSV structure; GRR uses the engineering multi-level structure.

| File | Data characteristics | Main feature | Usage |
|---|---|---|---|
| `test_dataset.csv` | 60-row baseline | Import, checks, process definition, models, reports | Follow the full flow |
| `test_dataset_linear.csv` | 60 rows, near-linear output | Linear DOE | Fit and inspect coefficients |
| `test_dataset_quadratic.csv` | 80 rows with curvature | Quadratic DOE | Compare linear and quadratic fits |
| `test_dataset_interaction.csv` | 80 rows with interaction signal | Interaction, SHAP, sensitivity, effect size | Inspect effects and ranking |
| `test_dataset_quality_issues.csv` | 8 rows with deliberate issues | Data-quality report/readiness | Import and review warnings |
| `test_dataset_grr.csv` | 45 rows (5 parts × 3 operators × 3 repeats) | GRR | Assign engineering fields |
| `test_dataset_timeseries.csv` | 45 ordered rows with cycles | Trend, time series, SPC | Set `datetime` and numeric field |
| `test_dataset_out_of_spec.csv` | 8 rows crossing LSL/USL | SPC, specification checks, NG risk | Set limits and inspect violations |

### Testing notes

- Fixtures support rapid feature verification; production conclusions require sufficient, representative data.
- DOE fixtures share the same core columns but use different output relationships, so model and simulation differences should be explainable.
- Fix specifications, simulation count, and random seed when comparing models or simulations.
- `test_dataset_quality_issues.csv` deliberately contains issues expected to be detected.
- `test_dataset_grr.csv` uses engineering multi-level fields and should not be treated as an ordinary CSV role mapping.
