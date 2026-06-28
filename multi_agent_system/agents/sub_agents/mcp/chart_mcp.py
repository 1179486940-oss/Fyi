"""
MCP: 图表引擎
生成数据分析图（柱状图、折线图、饼图、瀑布图、甘特图）
输出 PNG (matplotlib) / HTML (plotly)，返回下载链接
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from config import get_settings
from utils.logger import get_logger
from utils.helpers import generate_uuid

logger = get_logger(__name__)


class ChartMCP:
    """图表生成 MCP Server"""

    def __init__(self):
        settings = get_settings()
        self._storage_path = settings.storage.storage_path / "charts"
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._base_url = f"http://{settings.server.host}:{settings.server.port}/files"

    # ── 图表生成 ─────────────────────────────────────────

    async def generate_line_chart(
        self,
        data: list[dict],
        x_field: str,
        y_field: str,
        title: str = "折线图",
        output_format: str = "html",
    ) -> dict[str, Any]:
        """生成折线图"""
        return await self._generate_chart("line", data, x_field, y_field, title, output_format)

    async def generate_bar_chart(
        self,
        data: list[dict],
        x_field: str,
        y_field: str,
        title: str = "柱状图",
        output_format: str = "html",
    ) -> dict[str, Any]:
        """生成柱状图"""
        return await self._generate_chart("bar", data, x_field, y_field, title, output_format)

    async def generate_pie_chart(
        self,
        data: list[dict],
        label_field: str,
        value_field: str,
        title: str = "饼图",
    ) -> dict[str, Any]:
        """生成饼图"""
        return await self._generate_chart("pie", data, label_field, value_field, title, "html")

    async def generate_multi_chart(
        self,
        data: list[dict],
        charts: list[dict],
        title: str = "组合图表",
    ) -> dict[str, Any]:
        """
        生成复合图表（多个子图）
        charts: [{"type": "line", "x": "date", "y": "value", "title": "..."}]
        """
        try:
            file_id = generate_uuid()
            file_path = self._storage_path / f"{file_id}.html"

            import plotly.subplots as sp
            import plotly.graph_objects as go

            rows = len(charts)
            fig = sp.make_subplots(rows=rows, cols=1, subplot_titles=[c.get("title", "") for c in charts])

            for i, chart_config in enumerate(charts):
                chart_type = chart_config.get("type", "bar")
                x_vals = [r[chart_config["x"]] for r in data]
                y_vals = [r[chart_config["y"]] for r in data]

                if chart_type == "line":
                    fig.add_trace(go.Scatter(x=x_vals, y=y_vals, mode="lines+markers", name=chart_config.get("title", "")), row=i+1, col=1)
                elif chart_type == "bar":
                    fig.add_trace(go.Bar(x=x_vals, y=y_vals, name=chart_config.get("title", "")), row=i+1, col=1)

            fig.update_layout(title_text=title, height=300 * rows)
            fig.write_html(str(file_path))

            return {
                "status": "success",
                "file_id": file_id,
                "download_url": f"{self._base_url}/{file_id}/download",
                "format": "html",
            }
        except Exception as e:
            logger.error("Multi-chart generation failed: %s", e)
            return {"status": "error", "message": str(e)}

    # ── 核心生成逻辑 ─────────────────────────────────────

    async def _generate_chart(
        self,
        chart_type: str,
        data: list[dict],
        x_field: str,
        y_field: str,
        title: str,
        output_format: str = "html",
    ) -> dict[str, Any]:
        """通用图表生成"""
        if not data:
            return {"status": "error", "message": "No data provided"}

        x_vals = [r[x_field] for r in data if x_field in r]
        y_vals = [r[y_field] for r in data if y_field in r]

        file_id = generate_uuid()

        try:
            if output_format == "html":
                return await self._generate_plotly(chart_type, x_vals, y_vals, title, file_id)
            else:
                return await self._generate_matplotlib(chart_type, x_vals, y_vals, title, file_id)
        except Exception as e:
            logger.error("Chart generation failed: %s", e)
            return {"status": "error", "message": str(e)}

    async def _generate_plotly(
        self, chart_type: str, x_vals: list, y_vals: list, title: str, file_id: str,
    ) -> dict[str, Any]:
        """使用 Plotly 生成 HTML 交互图"""
        import plotly.graph_objects as go

        file_path = self._storage_path / f"{file_id}.html"

        if chart_type == "line":
            fig = go.Figure(go.Scatter(x=x_vals, y=y_vals, mode="lines+markers"))
        elif chart_type == "bar":
            fig = go.Figure(go.Bar(x=x_vals, y=y_vals))
        elif chart_type == "pie":
            fig = go.Figure(go.Pie(labels=x_vals, values=y_vals))
        else:
            fig = go.Figure(go.Bar(x=x_vals, y=y_vals))

        fig.update_layout(
            title=title,
            xaxis_title=x_vals[0] if chart_type != "pie" else "",
            yaxis_title="值",
            template="plotly_dark",
        )
        fig.write_html(str(file_path))

        logger.info("Plotly chart generated: %s (%s)", title, file_id)
        return {
            "status": "success",
            "file_id": file_id,
            "download_url": f"{self._base_url}/{file_id}/download",
            "format": "html",
            "interactive": True,
        }

    async def _generate_matplotlib(
        self, chart_type: str, x_vals: list, y_vals: list, title: str, file_id: str,
    ) -> dict[str, Any]:
        """使用 Matplotlib 生成 PNG 静态图"""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        file_path = self._storage_path / f"{file_id}.png"

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "line":
            ax.plot(x_vals, y_vals, marker="o", linewidth=2)
        elif chart_type == "bar":
            ax.bar(x_vals, y_vals)
        else:
            ax.bar(x_vals, y_vals)

        ax.set_title(title)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        plt.xticks(rotation=45)
        plt.tight_layout()
        fig.savefig(str(file_path), dpi=150)
        plt.close(fig)

        logger.info("Matplotlib chart generated: %s (%s)", title, file_id)
        return {
            "status": "success",
            "file_id": file_id,
            "download_url": f"{self._base_url}/{file_id}/download",
            "format": "png",
            "interactive": False,
        }
