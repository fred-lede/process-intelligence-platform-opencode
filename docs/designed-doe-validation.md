# Designed DOE validation

`doe_categorical_factorial` is intended for designed experiments such as a
balanced three-level factorial or Taguchi-style study. Numeric-looking factor
levels remain categorical labels. The model estimates main effects and
pairwise interactions within the tested design space; it is not a replacement
for a large production-data forecasting model.

## Evidence hierarchy

Use the evidence in this order:

1. Confirm that all expected factor combinations are present and that the
   design is balanced.
2. Review ANOVA, coefficient confidence intervals, interaction plots, and
   residual diagnostics.
3. When cells are replicated, review pure error and lack-of-fit.
4. Use DOE cell-out validation for a complete one-run-per-cell design.
5. Run a physical confirmation experiment and record predicted versus measured
   output before using the result for production decisions.

Random k-fold cross-validation remains available for comparison, but it is
supplementary for a small designed DOE. A negative random-fold R² can occur
when a fold removes design cells and should not, by itself, reject the DOE.

## Replication and lack-of-fit

With one observation per cell, pure error and lack-of-fit cannot be separated.
The application reports this explicitly. Add repeated runs at selected cells
or center conditions when estimating repeatability and lack-of-fit matters.

## Residual order chart

The residual-versus-order chart uses `Run Order`, meaning the actual execution
sequence after DOE randomization. The x-axis displays consecutive observation
numbers (`1` through `n`) so the chart remains readable even when the source
column contains non-consecutive or non-sorted values. Hover details provide the
observation number, `Run Order`, `Standard Order`, and residual.

Use this chart to look for time, equipment, lot, operator, or other execution-
sequence drift. `Standard Order` is retained for tracing a row back to the DOE
design matrix; it is not used as the process sequence unless the source data
has no valid `Run Order`.

## Confirmation experiments

Use the Validation Lab to select a suggested condition, record planned and
actual factor levels, and enter the measured output. For categorical models,
the application predicts from the selected actual levels automatically. The
validation result reports the number of confirmation experiments, pass rate,
and mean absolute prediction error.

Monte Carlo and OptQuest results for an unconfirmed designed DOE are marked
exploratory. They are candidates for confirmation, not production evidence.
