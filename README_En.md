# Process Intelligence Platform

**Languages:** [繁體中文](README.md) · [English](README_En.md)

**Author:** Fred Wang

An explainable and traceable process-analysis platform with traditional DOE and AI-assisted models. Supports macOS and Windows desktop applications.

## GitHub and license

[fred-lede/process-intelligence-platform-opencode](https://github.com/fred-lede/process-intelligence-platform-opencode) · [MIT License](LICENSE)

## Architecture

- Frontend: React 18, TypeScript, Ant Design 5, Zustand, i18next
- Desktop: Tauri 2.0 (Rust)
- Analysis engine: Python 3.12 managed by `uv` (numpy, pandas, scikit-learn, scipy, shap)
- Charts: Plotly.js
- Storage: in-memory `DatasetRegistry`; raw data stays local by default

## Quick start

Requirements: Rust 1.77+, Node.js 18+, Python 3.12, and a system WebView. On macOS install OpenMP with `brew install libomp`. PDF export also requires the system dependencies in [docs/deployment.md](docs/deployment.md).

```bash
npm install
cd engine && uv venv --python 3.12 && uv sync --extra dev && cd ..
npm run tauri dev
```

Run checks with `npx tsc --noEmit`, `npm run build`, `cd engine && .venv/bin/pytest -q`, and `cd src-tauri && cargo test engine::tests::pings_live_engine`.

## Features

- Data Import: Excel/CSV import, role/type detection, quality checks, distribution fitting, and readiness gates.
- Process Definition: output LSL/USL/center, input ranges, control limits, quality review, anomaly scenarios, and analysis packages.
- Exploration: distribution, trend, time-series, and GRR analysis.
- Model Center: linear/quadratic DOE, tree models, hybrid, logistic and Weibull regression; ANOVA, interactions, SHAP, sensitivity, effect sizes, validation, and residual diagnostics.
- SPC: I-MR, X-bar/R, X-bar/S, EWMA, CUSUM, Western Electric rules, outliers, change points, capability indices, and batch comparison.
- Monte Carlo: distribution-aware sampling (`uniform`, `triangular`, `normal`, `empirical`), Bootstrap, Copula correlation, specification risk, percentiles, and Pp/Ppk.
- Validation Lab, interactive what-if prediction, HTML/PDF/Excel reports, immutable versions, configurable process flow, and a confirmation-based multilingual AI Assistant.

## Supported models

| Model | Use |
|---|---|
| `doe_linear` | Main effects |
| `doe_quadratic` | Curvature and interactions |
| `random_forest` | Nonlinear regression |
| `xgboost` / `lightgbm` | Boosted nonlinear prediction |
| `residual_hybrid` | DOE trend plus RF residual |
| `logistic_regression` | Binary NG/OK prediction |
| `weibull_regression` | Reliability/lifetime analysis |

## Project structure

```text
src/          React frontend and feature pages
src-tauri/    Tauri Rust backend
engine/       Python analysis engine and tests
data/         Test datasets and data documentation
docs/         Specifications and deployment documentation
```

## Test datasets

Multiple scenario fixtures are provided. See [`data/test_dataset_README_En.md`](data/test_dataset_README_En.md) for column contracts, sample-size guidance, workflows, and the test matrix.

- `test_dataset.csv`: 60-row end-to-end baseline
- `test_dataset_linear.csv`: 60-row linear DOE scenario
- `test_dataset_quadratic.csv`: 80-row curvature scenario
- `test_dataset_interaction.csv`: 80-row interaction scenario
- `test_dataset_quality_issues.csv`: deliberate quality problems
- `test_dataset_grr.csv`: 45 rows (5 parts × 3 operators × 3 repeats)
- `test_dataset_timeseries.csv`: 45-row trend/cycle scenario
- `test_dataset_out_of_spec.csv`: specification-violation scenario

## Design principles

- Industry-agnostic and configurable.
- Raw data remains local unless de-identified cloud transfer is explicitly confirmed.
- Traditional DOE remains a transparent fallback.
- Recommendations expose evidence, assumptions, applicability, and limitations.
- Dataset, model, simulation, report, filter, and grain metadata remain traceable.
- AI operations are drafts and require human confirmation before changing project state.

## Version history

### v0.8.3 (2026-09-11)

Added page-specific usage guides with statistical principles, formulas, chart interpretation, limitations, and engineering recommendations in English, Traditional Chinese, and Spanish.

### v0.8.2 (2026-09-10)

Added `best_distribution`-driven Monte Carlo sampling, `uniform`/`triangular`/`normal`/`empirical` sampling, manual overrides, parameter reporting, and extrapolation-risk metadata.

### v0.8.1 (2026-09-10)

Added permutation-RMSE sensitivity analysis and standardized effect-size tables/charts integrated with Model Center, reports, and AI summaries.

### v0.8.0 (2026-09-09)

Added source-data readiness checks, candidate distribution fitting, visual status summaries, critical-issue gates, and dataset-version traceability.

### v0.7.0 (2026-09-09)

Added synchronized version metadata, cross-page grain/filter propagation, report metadata, AI error guidance, and cross-platform build checks.

### v0.6.0 (2026-09-09)

Added optional engineering multi-level data contracts, metadata detection, subgroup SPC, and grain/filter traceability while preserving ordinary CSV compatibility.

### v0.5.0 (2026-09-09)

Added controlled AI providers, de-identified transfer preview, confirmation-required operation drafts, cross-page analysis context, persistent model settings, and multilingual structured responses.

Earlier releases introduced the core import, process definition, exploration, modeling, validation, simulation, SPC, reporting, governance, and audit workflows. See [`README.md`](README.md) for the detailed historical record.

## Developer

- Author: Fred Wang
- License: MIT
