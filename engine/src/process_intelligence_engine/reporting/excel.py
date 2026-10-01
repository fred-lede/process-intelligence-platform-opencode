"""Excel report generator."""
from __future__ import annotations
from datetime import datetime
from typing import Any

from .base import ReportGenerator, cell_value, flatten_rows
from .models import ReportData


class ExcelReportGenerator(ReportGenerator):
    """Generate Excel report."""
    
    def generate(self) -> bytes:
        """Generate Excel report as bytes."""
        try:
            from io import BytesIO
            from openpyxl import Workbook
        except ImportError:
            raise ImportError("openpyxl is required for Excel generation. Install with: pip install openpyxl")
        
        output = BytesIO()
        wb = Workbook()
        
        # Sheet 1: Project Info
        ws1 = wb.active
        ws1.title = "專案資訊"
        ws1.append(["專案名稱", self.data.project_name])
        ws1.append(["操作者", self.data.operator])
        ws1.append(["產生時間", self.data.created_at.strftime("%Y-%m-%d %H:%M:%S")])
        ws1.append(["資料集 ID", self.data.dataset_id])
        ws1.append(["來源檔案", self.data.source_file])
        ws1.append(["資料列數", self.data.row_count])
        ws1.append(["欄位數", self.data.column_count])
        ws1.append(["Report status", self.data.report_status])
        ws1.append(["Approved by", self.data.approved_by])
        ws1.append(["Approved at", self.data.approved_at])
        evidence = wb.create_sheet("Evidence")
        evidence.append(["Claim ID", "Source", "Status", "Text", "Source entities"])
        for claim in (self.data.approval_record or {}).get("claims", []):
            evidence.append([claim.get("claim_id", ""), claim.get("origin_source", ""),
                claim.get("evidence_status", ""), claim.get("text", ""),
                ", ".join(claim.get("source_entity_ids", []))])
        
        def header(ws, labels) -> None:
            """Write a header row and bold it (new sheets; keeps the legacy ones untouched)."""
            from openpyxl.styles import Font
            ws.append(labels)
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)

        # Sheet: Specifications. The report's own contract (LSL/USL/target) was
        # collected into ReportData but never written to any sheet. Structured keys
        # such as input_ranges are expanded into rows rather than written raw.
        spec = self.data.spec or {}
        limits = spec.get("limits") or {}
        spec_rows: list[tuple[str, Any]] = []
        for key, value in spec.items():
            if key == "limits":
                continue
            spec_rows += flatten_rows(str(key), value)
        spec_rows += [(k, limits[k]) for k in ("lsl", "usl", "target", "cl") if limits.get(k) is not None]
        if spec_rows:
            ws_spec = wb.create_sheet("規格")
            header(ws_spec, ["欄位/項目", "規格值"])
            for key, value in spec_rows:
                ws_spec.append([key, cell_value(value)])

        # Sheet: Data quality
        quality = self.data.quality_summary or {}
        if quality:
            ws_q = wb.create_sheet("資料品質")
            header(ws_q, ["項目", "值"])
            ws_q.append(["發現問題數", quality.get("issue_count", 0)])
            for sev, count in (quality.get("issues_by_severity") or {}).items():
                ws_q.append([f"嚴重度 {sev}", count])
            issues = quality.get("issues") or []
            if issues:
                ws_q.append([])
                header(ws_q, ["檢查", "欄位", "嚴重度", "說明"])
                for issue in issues:
                    ws_q.append([
                        issue.get("check", issue.get("type", "")),
                        issue.get("column", ""),
                        issue.get("severity", ""),
                        issue.get("message", ""),
                    ])

        # Sheet 2: Field Roles
        ws2 = wb.create_sheet("欄位角色")
        ws2.append(["欄位名稱", "角色", "信心度", "資料型態"])
        for field in self.data.fields:
            ws2.append([
                field.get("name", ""),
                field.get("role", ""),
                field.get("confidence", 0),
                field.get("data_type", ""),
            ])
        
        # Sheet 3: Model Comparison. The extra metrics (AUC / accuracy /
        # shape_k / AIC) are rendered in HTML per model type; Excel only carried
        # the four regression metrics.
        if self.data.model_comparison:
            ws3 = wb.create_sheet("模型比較")
            ws3.append(["模型 ID", "模型類型", "R²", "RMSE", "MAE", "Adj R²",
                        "AUC", "Accuracy", "Shape k", "AIC", "狀態"])
            for model in self.data.model_comparison:
                m = model.get("metrics") or {}
                ws3.append([
                    model.get("model_id", ""),
                    model.get("model_type", ""),
                    m.get("r2", ""),
                    m.get("rmse", ""),
                    m.get("mae", ""),
                    m.get("adj_r2", ""),
                    m.get("auc", ""),
                    m.get("accuracy", ""),
                    m.get("shape_k", ""),
                    m.get("aic", ""),
                    model.get("status", ""),
                ])

        # Sheet: selected model, its equation and coefficients. HTML renders a
        # "最終方程式/模型" section with a coefficient table; Excel had neither.
        best = self.data.best_model or {}
        coefs = best.get("coefficients") or {}
        if best or coefs:
            ws_bm = wb.create_sheet("最終模型")
            header(ws_bm, ["項目", "值"])
            for key in ("model_id", "model_type", "target", "equation", "status"):
                if best.get(key) not in (None, ""):
                    ws_bm.append([key, best.get(key)])
            for key, value in (best.get("metrics") or {}).items():
                ws_bm.append([f"metrics.{key}", cell_value(value)])
            if coefs:
                ws_bm.append([])
                header(ws_bm, ["係數項", "係數值"])
                for term, value in coefs.items():
                    ws_bm.append([term, cell_value(value)])
        
        # Sheet 4: Interactions
        if self.data.interactions.get("matrix"):
            ws4 = wb.create_sheet("交互作用")
            factors = self.data.interactions.get("factors", [])
            ws4.append([""] + factors)
            matrix = self.data.interactions.get("matrix", [])
            for i, factor in enumerate(factors):
                row = [factor]
                for j, val in enumerate(matrix[i]):
                    row.append(val)
                ws4.append(row)

        if self.data.sensitivity_effects.get("items"):
            ws_sens = wb.create_sheet("敏感度與效應量")
            ws_sens.append(["輸入欄位", "敏感度", "效應量"])
            for item in self.data.sensitivity_effects["items"]:
                ws_sens.append([item.get("input", ""), item.get("sensitivity", ""), item.get("effect_size", "")])
        
        # Sheet: SPC capability and violations. Collected into ReportData and
        # rendered in HTML, but entirely absent from the workbook -- for a
        # manufacturing report Cp/Cpk and the rule counts are the numbers people
        # actually paste into other documents.
        spc_results = self.data.spc_results or []
        if spc_results:
            ws_spc = wb.create_sheet("SPC")
            header(ws_spc, ["欄位", "圖表", "點數", "中心線", "UCL", "LCL", "MR UCL", "MR 中心",
                            "Cp", "Cpk", "Pp", "Ppk", "σ_within", "σ_overall", "違規數"])
            suggestion_rows = []
            for r in spc_results:
                cap = r.get("capability") or {}
                ws_spc.append([
                    r.get("column", ""),
                    r.get("chart_type", ""),
                    r.get("n_points", ""),
                    r.get("x_mean", ""),
                    r.get("x_ucl", ""),
                    r.get("x_lcl", ""),
                    r.get("mr_ucl", ""),
                    r.get("mr_mean", ""),
                    cap.get("cp", ""),
                    cap.get("cpk", ""),
                    cap.get("pp", ""),
                    cap.get("ppk", ""),
                    cap.get("sigma_within", ""),
                    cap.get("sigma_overall", ""),
                    r.get("violations", ""),
                ])
                for s in (r.get("suggestions") or []):
                    suggestion_rows.append([
                        r.get("column", ""), s.get("severity", ""), s.get("message", ""),
                    ])
            if suggestion_rows:
                ws_sug = wb.create_sheet("SPC 優化建議")
                header(ws_sug, ["欄位", "嚴重度", "說明"])
                for row in suggestion_rows:
                    ws_sug.append(row)

        # Sheet: distributions (best fit per column, as HTML's 正常分布 table)
        fits = self.data.distribution_fits or {}
        if fits:
            ws_d = wb.create_sheet("分佈配適")
            header(ws_d, ["欄位", "最佳分布", "AIC", "KS p 值", "偏態", "峰度"])
            for col, entries in fits.items():
                if not entries:
                    continue
                f = entries[0]
                ws_d.append([
                    col, f.get("name", ""), f.get("aic", ""), f.get("ks_p_value", ""),
                    f.get("skewness", ""), f.get("kurtosis", ""),
                ])

        # Sheet: anomaly scenarios
        anomalies = self.data.anomalies or []
        if anomalies:
            ws_a = wb.create_sheet("異常情境")
            header(ws_a, ["名稱", "類型", "欄位", "方向", "閾值", "發生機率", "信心度"])
            for a in anomalies:
                ws_a.append([
                    a.get("name", ""), a.get("type", ""), a.get("target_input", ""),
                    a.get("direction", ""), a.get("threshold", ""),
                    a.get("occurrence_probability", ""), a.get("confidence", ""),
                ])

        # Sheet: Monte Carlo risk (summary, percentiles, anomaly contribution)
        mc = self.data.monte_carlo or {}
        if mc:
            ws_mc = wb.create_sheet("蒙地卡羅")
            header(ws_mc, ["項目", "值"])
            for key in ("n_simulations", "seed", "ng_count", "ng_probability",
                        "output_mean", "output_std", "output_median"):
                if mc.get(key) is not None:
                    ws_mc.append([key, mc.get(key)])
            mc_cap = mc.get("capability") or {}
            for key in ("pp", "ppk", "cp", "cpk", "sigma_overall"):
                if mc_cap.get(key) is not None:
                    ws_mc.append([f"capability.{key}", mc_cap.get(key)])
            pct = mc.get("percentiles") or {}
            if pct:
                ws_mc.append([])
                header(ws_mc, ["百分位", "值"])
                for k in ("p1", "p5", "p50", "p95", "p99"):
                    if pct.get(k) is not None:
                        ws_mc.append([k, pct.get(k)])
            rankings = mc.get("anomaly_rankings") or []
            if rankings:
                ws_mc.append([])
                header(ws_mc, ["異常 ID", "欄位", "NG 數", "NG 機率"])
                for r in rankings:
                    ws_mc.append([
                        r.get("anomaly_id", ""), r.get("target_input", ""),
                        r.get("ng_count", ""), r.get("ng_probability", ""),
                    ])

        # Sheet: credibility (the six-dimension confidence score)
        cred = self.data.credibility or {}
        if cred:
            ws_c = wb.create_sheet("可信度")
            header(ws_c, ["維度", "分數"])
            ws_c.append(["綜合可信度", cred.get("composite", "")])
            ws_c.append(["等級", cred.get("level", "")])
            for label, key in (
                ("資料覆蓋", "data_coverage"), ("預測準確", "predictive_acc"),
                ("統計穩定", "statistical_stability"), ("工程合理", "engineering_reasonable"),
                ("驗證程度", "validation_degree"), ("外推風險", "extrapolation_risk"),
            ):
                if cred.get(key) is not None:
                    ws_c.append([label, cred.get(key)])

        # Sheet: proposed process window
        window = self.data.process_window or {}
        if window.get("column_limits"):
            ws_w = wb.create_sheet("建議製程窗口")
            header(ws_w, ["欄位", "Min", "Max", "中心"])
            for col, vals in window["column_limits"].items():
                ws_w.append([col, vals.get("min", ""), vals.get("max", ""), vals.get("center", "")])
            if window.get("basis"):
                ws_w.append([])
                ws_w.append(["基準", window.get("basis")])

        # Sheet: governance and traceability (chain steps, gates, unconfirmed
        # items, extrapolation warnings). HTML carries these as Appendix A/C and
        # the evidence summary; Excel carried none of it, which undercuts the
        # platform's traceability claim.
        steps = (self.data.chain_trace or {}).get("steps", [])
        gates = self.data.gate_summary or {}
        unconfirmed = self.data.unconfirmed_items or []
        ex = self.data.extrapolation_summary or {}
        if steps or gates or unconfirmed or ex:
            ws_g = wb.create_sheet("治理與追溯")
            header(ws_g, ["項目", "值"])
            for key, value in gates.items():
                ws_g.append([f"gate.{key}", cell_value(value)])
            for item in unconfirmed:
                ws_g.append(["未確認項目", cell_value(item)])
            for key in ("out_of_range_ratio", "max_risk_score", "recommendation"):
                if ex.get(key) not in (None, ""):
                    ws_g.append([f"外推.{key}", cell_value(ex.get(key))])
            if steps:
                ws_g.append([])
                header(ws_g, ["Step", "Entity ID", "Operator", "Timestamp", "Status"])
                for step in steps:
                    ws_g.append([
                        step.get("step", ""), step.get("entity_id", ""), step.get("operator", ""),
                        step.get("timestamp", ""), step.get("status", ""),
                    ])

        # Sheet: source label legend (Appendix B); falls back to the standard set
        labels = self.data.source_labels or {
            "ai_guess": "AI guess",
            "stat_sig": "Statistically significant",
            "eng_hypothesis": "Engineering hypothesis",
            "exp_confirmed": "Experiment confirmed",
            "unverified": "Unverified",
        }
        ws_l = wb.create_sheet("來源標籤")
        header(ws_l, ["Label Key", "Meaning"])
        for key, value in labels.items():
            ws_l.append([key, cell_value(value)])

        # Sheet 5: Recommendations
        if self.data.recommendations:
            ws5 = wb.create_sheet("實驗建議")
            ws5.append(["類型", "優先級", "因子", "說明"])
            for rec in self.data.recommendations:
                ws5.append([
                    rec.get("type", ""),
                    rec.get("priority", ""),
                    ", ".join(rec.get("factors", [])),
                    rec.get("reason", ""),
                ])
        
        wb.save(output)
        output.seek(0)
        return output.read()
