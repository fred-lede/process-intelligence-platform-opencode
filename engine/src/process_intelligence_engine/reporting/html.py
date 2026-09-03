"""HTML report generator (full 14-section specification, spec 17.2)."""
from __future__ import annotations
import html as _html
from datetime import datetime
from typing import Any

from .base import ReportGenerator
from .models import ReportData
from .charting import histogram_svg, heatmap_svg

SEVERITY_BADGE = {
    "critical": "badge-danger",
    "warning": "badge-warning",
    "info": "badge-info",
}


class HTMLReportGenerator(ReportGenerator):
    """Generate HTML report."""

    def generate(self) -> str:
        """Generate HTML report content."""
        return self._generate_html()

    def _e(self, value: Any) -> str:
        """Escape a value for safe HTML embedding."""
        if value is None:
            return ""
        return _html.escape(str(value))

    def _fmt(self, value: Any, decimals: int = 4) -> str:
        if value is None:
            return "N/A"
        try:
            return f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):
            return self._e(value)

    def _pct(self, value: Any) -> str:
        if value is None:
            return "N/A"
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return self._e(value)

    def _section(self, title: str, body_html: str) -> str:
        return f"<h2>{self._e(title)}</h2>\n{body_html}"

    def _render_info(self) -> str:
        limits = (self.data.spec or {}).get("limits") or {}
        rows = [
            ("資料集 ID", self.data.dataset_id or "N/A"),
            ("來源檔案", self.data.source_file or "N/A"),
            ("資料列數", self.data.row_count),
            ("欄位數", self.data.column_count),
        ]
        if limits.get("lsl") is not None:
            rows.append(("LSL", self._fmt(limits.get("lsl"), 4)))
        if limits.get("usl") is not None:
            rows.append(("USL", self._fmt(limits.get("usl"), 4)))
        if self.data.time_range:
            rows.append(("時間範圍", f"{self._e(self.data.time_range.get('start', ''))} ~ {self._e(self.data.time_range.get('end', ''))}"))
        body = '<table><tr><th>項目</th><th>值</th></tr>'
        for k, v in rows:
            body += f"<tr><td>{self._e(k)}</td><td>{self._e(v)}</td></tr>"
        body += "</table>"
        return self._section("資料來源", body)

    def _render_fields(self) -> str:
        rows = []
        for f in self.data.fields:
            rows.append(f"<tr><td>{self._e(f.get('name'))}</td><td><span class='badge badge-{'success' if f.get('role') == 'output' else 'warning'}'>{self._e(f.get('role'))}</span></td><td>{self._pct(f.get('confidence'))}</td></tr>")
        body = "<table><tr><th>欄位名稱</th><th>角色</th><th>信心度</th></tr>" + "".join(rows) + "</table>"
        limits = (self.data.spec or {}).get("limits") or {}
        spec_rows = []
        for col, vals in (self.data.spec or {}).items():
            if col == "limits":
                continue
            spec_rows.append(f"<tr><td>{self._e(col)}</td><td>{self._e(vals)}</td></tr>")
        if limits:
            for key in ("lsl", "usl", "target", "cl"):
                if limits.get(key) is not None:
                    spec_rows.append(f"<tr><td>{self._e(key)}</td><td>{self._fmt(limits[key])}</td></tr>")
        spec_html = ""
        if spec_rows:
            spec_html = "<h3>規格</h3><table><tr><th>欄位/項目</th><th>規格值</th></tr>" + "".join(spec_rows) + "</table>"
        return self._section("欄位與規格", body + spec_html)

    def _render_quality(self) -> str:
        if not self.data.quality_summary:
            return ""
        body = ""
        summary = self.data.quality_summary
        body += f"<div class='info-box'>發現問題數: {self._e(summary.get('issue_count', 0))} 筆</div>"
        by_sev = summary.get("issues_by_severity") or {}
        if by_sev:
            chips = " ".join(
                f"<span class='badge {SEVERITY_BADGE.get(sev, 'badge-info')}'>{self._e(sev)}: {self._e(cnt)}</span>"
                for sev, cnt in by_sev.items() if cnt
            )
            if chips:
                body += f"<p>{chips}</p>"
        issues = summary.get("issues") or []
        if issues:
            body += "<table><tr><th>檢查</th><th>欄位</th><th>嚴重度</th><th>說明</th></tr>"
            for i in issues:
                body += (
                    f"<tr><td>{self._e(i.get('check'))}</td>"
                    f"<td>{self._e(i.get('column'))}</td>"
                    f"<td><span class='badge {SEVERITY_BADGE.get(i.get('severity'), 'badge-info')}'>{self._e(i.get('severity'))}</span></td>"
                    f"<td>{self._e(i.get('message'))}</td></tr>"
                )
            body += "</table>"
        return self._section("資料品質結果", body)

    def _render_distributions(self) -> str:
        if not self.data.distribution_fits:
            return ""
        limits = (self.data.spec or {}).get("limits") or {}
        anomaly_limits = {}
        for a in self.data.anomalies:
            if a.get("target_input") and a.get("threshold") is not None:
                anomaly_limits.setdefault(a["target_input"], []).append(a)

        body = "<table><tr><th>欄位</th><th>最佳分布</th><th>AIC</th><th>KS p 值</th><th>偏態</th><th>峰度</th></tr>"
        charts = []
        for col, fits in self.data.distribution_fits.items():
            if not fits:
                continue
            f = fits[0]
            body += (
                f"<tr><td>{self._e(col)}</td><td>{self._e(f.get('name'))}</td>"
                f"<td>{self._fmt(f.get('aic'))}</td><td>{self._fmt(f.get('ks_p_value'))}</td>"
                f"<td>{self._fmt(f.get('skewness'))}</td><td>{self._fmt(f.get('kurtosis'))}</td></tr>"
            )
            hist = f.get("histogram") or {}
            edges = hist.get("edges") or hist.get("bins") or []
            counts = hist.get("counts") or []
            if edges and counts:
                lsl = limits.get("lsl") if col == self.data.best_model.get("target") else None
                usl = limits.get("usl") if col == self.data.best_model.get("target") else None
                chart = histogram_svg(
                    edges=edges,
                    counts=counts,
                    title=f"{col} 分布",
                    fit_curve=f.get("pdf") or None,
                    lsl=lsl,
                    usl=usl,
                    xlabel=col,
                )
                # overlay anomaly thresholds for this column
                for anom in anomaly_limits.get(col, []):
                    thr = anom.get("threshold")
                    ap = None
                    if anom.get("direction") in ("above", "higher"):
                        ap = histogram_svg(
                            edges=edges, counts=counts, title=f"{col} — 異常({anom.get('name')}) 高於閾值",
                            fit_curve=f.get("pdf") or None, lsl=thr, xlabel=col)
                    elif anom.get("direction") in ("below", "lower"):
                        ap = histogram_svg(
                            edges=edges, counts=counts, title=f"{col} — 異常({anom.get('name')}) 低於閾值",
                            fit_curve=f.get("pdf") or None, usl=thr, xlabel=col)
                    if ap:
                        charts.append(ap)
                charts.append(chart)
        body += "</table>" + "<div style='margin-top:16px;'>" + "".join(charts) + "</div>"
        return self._section("正常分布", body)

    def _render_anomalies(self) -> str:
        if not self.data.anomalies:
            return ""
        body = "<table><tr><th>名稱</th><th>類型</th><th>欄位</th><th>方向</th><th>發生機率</th><th>信心度</th></tr>"
        for a in self.data.anomalies:
            body += (
                f"<tr><td>{self._e(a.get('name'))}</td><td>{self._e(a.get('type'))}</td>"
                f"<td>{self._e(a.get('target_input'))}</td><td>{self._e(a.get('direction'))}</td>"
                f"<td>{self._pct(a.get('occurrence_probability'))}</td><td>{self._pct(a.get('confidence'))}</td></tr>"
            )
        body += "</table>"
        return self._section("異常分布/情境", body)

    def _render_model_comparison(self) -> str:
        if not self.data.model_comparison:
            return ""
        body = "<table><tr><th>模型 ID</th><th>類型</th><th>R²</th><th>RMSE</th><th>MAE</th><th>Adj R²</th><th>狀態</th></tr>"
        for m in self.data.model_comparison:
            metrics = m.get("metrics") or {}
            body += (
                f"<tr><td>{self._e(m.get('model_id'))}</td><td>{self._e(m.get('model_type'))}</td>"
                f"<td>{self._fmt(metrics.get('r2'))}</td><td>{self._fmt(metrics.get('rmse'))}</td>"
                f"<td>{self._fmt(metrics.get('mae'))}</td><td>{self._fmt(metrics.get('adj_r2'))}</td>"
                f"<td>{self._e(m.get('status'))}</td></tr>"
            )
        body += "</table>"
        return self._section("模型比較", body)

    def _render_best_model(self) -> str:
        bm = self.data.best_model
        if not bm:
            return ""
        body = f"<div class='info-box'><strong>模型類型:</strong> {self._e(bm.get('model_type'))}<br>"
        body += f"<strong>切目標:</strong> {self._e(bm.get('target'))}<br>"
        body += f"<strong>輸入:</strong> {self._e(', '.join(bm.get('inputs') or []))}<br>"
        body += f"<strong>訓練樣本:</strong> {self._e(bm.get('n_train'))} / 測試樣本: {self._e(bm.get('n_test'))}<br>"
        body += f"<strong>狀態:</strong> {self._e(bm.get('status'))}</div>"
        metrics = bm.get("metrics") or {}
        if metrics:
            body += "<h3>指標</h3><table><tr>"
            for k in ("r2", "rmse", "mae", "adj_r2", "mse"):
                if metrics.get(k) is not None:
                    body += f"<th>{self._e(k)}</th>"
            body += "</tr><tr>"
            for k in ("r2", "rmse", "mae", "adj_r2", "mse"):
                if metrics.get(k) is not None:
                    body += f"<td>{self._fmt(metrics.get(k))}</td>"
            body += "</tr></table>"
        if bm.get("equation"):
            body += f"<pre style='background:#f5f5f5;padding:10px;border-radius:5px;'>{self._e(bm['equation'])}</pre>"
        coefs = bm.get("coefficients") or {}
        if coefs:
            body += "<h3>係數</h3><table><tr><th>項</th><th>係數</th></tr>"
            for k, v in coefs.items():
                body += f"<tr><td>{self._e(k)}</td><td>{self._fmt(v)}</td></tr>"
            body += "</table>"
        return self._section("最終方程式/模型", body)

    def _render_interactions(self) -> str:
        data = self.data.interactions or {}
        pairs = data.get("significant_pairs") or []
        sig = [p for p in pairs if p.get("significant")]
        body = "<div class='info-box'>" + ("發現顯著交互作用" if sig else "未發現顯著交互作用") + "</div>"
        if sig:
            body += "<table><tr><th>因子 A</th><th>因子 B</th><th>強度</th></tr>"
            for p in sig:
                body += f"<tr><td>{self._e(p.get('i'))}</td><td>{self._e(p.get('j'))}</td><td>{self._fmt(p.get('strength'))}</td></tr>"
            body += "</table>"
        matrix = data.get("matrix")
        factors = data.get("factors") or []
        if matrix and factors:
            body += heatmap_svg(matrix=matrix, labels=list(factors), title="交互作用強度熱圖")
        return self._section("重要因素與交互作用", body)

    def _render_monte_carlo(self) -> str:
        mc = self.data.monte_carlo
        if not mc:
            return ""
        body = f"<div class='info-box'>模擬次數: {self._e(mc.get('n_simulations'))} | 種子: {self._e(mc.get('seed'))}</div>"
        body += "<table><tr><th>NG 計數</th><th>NG 機率</th><th>輸出均值</th><th>輸出標準差</th><th>中位數</th></tr>"
        body += (
            f"<tr><td>{self._e(mc.get('ng_count'))}</td><td>{self._pct(mc.get('ng_probability'))}</td>"
            f"<td>{self._fmt(mc.get('output_mean'))}</td><td>{self._fmt(mc.get('output_std'))}</td>"
            f"<td>{self._fmt(mc.get('output_median'))}</td></tr></table>"
        )
        pct = mc.get("percentiles") or {}
        if pct:
            body += "<table><tr><th>P1</th><th>P5</th><th>P50</th><th>P95</th><th>P99</th></tr><tr>"
            for k in ("p1", "p5", "p50", "p95", "p99"):
                body += f"<td>{self._fmt(pct.get(k))}</td>"
            body += "</tr></table>"
        hist = mc.get("histogram") or {}
        edges = hist.get("edges") or hist.get("bins") or []
        counts = hist.get("counts") or []
        if edges and counts:
            limits = (self.data.spec or {}).get("limits") or {}
            body += histogram_svg(
                edges=edges,
                counts=counts,
                title="Output 分布（紅線 = 超規區間）",
                fit_curve=None,
                lsl=limits.get("lsl"),
                usl=limits.get("usl"),
                xlabel="Output",
            )
        rankings = mc.get("anomaly_rankings") or []
        if rankings:
            body += "<h3>異常貢獻排名</h3><table><tr><th>異常 ID</th><th>欄位</th><th>NG 數</th><th>NG 機率</th></tr>"
            for r in rankings:
                body += f"<tr><td>{self._e(r.get('anomaly_id'))}</td><td>{self._e(r.get('target_input'))}</td><td>{self._e(r.get('ng_count'))}</td><td>{self._pct(r.get('ng_probability'))}</td></tr>"
            body += "</table>"
        return self._section("蒙地卡羅風險分析", body)

    def _render_credibility(self) -> str:
        c = self.data.credibility
        if not c:
            return ""
        body = f"<div class='info-box'>綜合可信度: {self._fmt(c.get('composite'))} — 等級: {self._e(c.get('level'))}</div>"
        dims = [
            ("資料覆蓋", "data_coverage"),
            ("預測準確", "predictive_acc"),
            ("統計穩定", "statistical_stability"),
            ("工程合理", "engineering_reasonable"),
            ("驗證程度", "validation_degree"),
            ("外推風險", "extrapolation_risk"),
        ]
        body += "<table><tr><th>維度</th><th>分數</th></tr>"
        for label, key in dims:
            if c.get(key) is not None:
                body += f"<tr><td>{self._e(label)}</td><td>{self._fmt(c.get(key))}</td></tr>"
        body += "</table>"
        return self._section("模型限制與驗證", body)

    def _render_recommendations(self) -> str:
        recs = self.data.recommendations or []
        window = self.data.process_window or {}
        body = ""
        if recs:
            body += "<table><tr><th>類型</th><th>優先級</th><th>因子</th><th>原因</th></tr>"
            for r in recs:
                body += (
                    f"<tr><td>{self._e(r.get('type'))}</td><td>{self._e(r.get('priority'))}</td>"
                    f"<td>{self._e(', '.join(r.get('factors') or []))}</td><td>{self._e(r.get('reason'))}</td></tr>"
                )
            body += "</table>"
        if window.get("column_limits"):
            body += "<h3>建議製程窗口</h3><table><tr><th>欄位</th><th>Min</th><th>Max</th><th>中心</th></tr>"
            for col, vals in window["column_limits"].items():
                body += f"<tr><td>{self._e(col)}</td><td>{self._fmt(vals.get('min'))}</td><td>{self._fmt(vals.get('max'))}</td><td>{self._fmt(vals.get('center'))}</td></tr>"
            body += "</table>"
            body += f"<p style='font-size:12px;color:#666'>基準: {self._e(window.get('basis'))}</p>"
        if not recs and not window.get("column_limits"):
            return ""
        return self._section("建議製程窗口與實驗建議", body)

    def _render_footer(self) -> str:
        return (
            f"<div class='footer'>"
            f"<p>Generated by Process Intelligence Platform v{self._e(self.data.version)} | "
            f"操作者: {self._e(self.data.operator)} | 產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
            f"</div>"
        )

    def _generate_html(self) -> str:
        sections = [
            self._render_info(),
            self._render_fields(),
            self._render_quality(),
            self._render_distributions(),
            self._render_anomalies(),
            self._render_model_comparison(),
            self._render_best_model(),
            self._render_interactions(),
            self._render_monte_carlo(),
            self._render_credibility(),
            self._render_recommendations(),
        ]
        html = f"""<!DOCTYPE html>
<html lang="{self.data.language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self._e(self.data.project_name)} - Analysis Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; color: #333; }}
        h1 {{ color: #2563EB; border-bottom: 2px solid #2563EB; padding-bottom: 10px; }}
        h2 {{ color: #444; margin-top: 30px; }}
        h3 {{ color: #555; margin-top: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #2563EB; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .info-box {{ background: #f0f7ff; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 12px; }}
        .badge-success {{ background: #d1fae5; color: #065f46; }}
        .badge-warning {{ background: #fef3c7; color: #92400e; }}
        .badge-danger {{ background: #fee2e2; color: #991b1b; }}
        .badge-info {{ background: #e0e7ff; color: #3730a3; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>{self._truncate(self.data.project_name)}</h1>
    <div class="info-box">
        <strong>報告產生時間:</strong> {self.data.created_at.strftime('%Y-%m-%d %H:%M:%S')}<br>
        <strong>操作者:</strong> {self._e(self.data.operator)}<br>
        <strong>專案名稱:</strong> {self._truncate(self.data.project_name)}
    </div>
    {''.join(sections)}
    {self._render_footer()}
</body>
</html>
"""
        return html
