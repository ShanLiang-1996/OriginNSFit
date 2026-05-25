from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from importlib import resources
import math
from pathlib import Path

import pandas as pd

from .e739 import E739Fit
from .fitting import SNCurveFit


class OriginAutomationError(RuntimeError):
    """Raised when Origin automation cannot be completed."""


@dataclass(frozen=True)
class OriginE739Job:
    fit: E739Fit
    label: str
    title: str


class OriginClient:
    def __init__(self, visible: bool = True) -> None:
        try:
            import originpro as op
        except ImportError as exc:
            raise OriginAutomationError(
                "originpro is not installed. Run `pip install -r requirements.txt` first."
            ) from exc

        self._op = op
        self._visible = visible
        self._resource_stack = ExitStack()

    def __enter__(self) -> "OriginClient":
        try:
            self._op.set_show(self._visible)
        except TypeError:
            if self._visible:
                self._op.set_show()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            self._op.exit()
        except Exception:
            pass
        self._resource_stack.close()

    def plot_sn_curve(
        self,
        fit: SNCurveFit,
        life_column: str,
        response_column: str,
        output_path: Path,
        title: str,
        symbol_kind: int = 3,
    ) -> Path:
        wks = self._op.new_sheet("w")
        wks.from_list(0, fit.data[life_column].tolist(), life_column, axis="X")
        wks.from_list(1, fit.data[response_column].tolist(), response_column, axis="Y")
        wks.from_list(2, fit.curve[life_column].tolist(), f"{life_column}_fit", axis="X")
        wks.from_list(3, fit.curve[response_column].tolist(), f"{response_column}_fit", axis="Y")

        graph = self._op.new_graph()
        layer = graph[0]
        data_plot = layer.add_plot(wks, 1, 0, type="scatter")
        fit_plot = layer.add_plot(wks, 3, 2, type="line")

        if data_plot is not None:
            data_plot.symbol_kind = symbol_kind
            data_plot.symbol_size = 15
            data_plot.symbol_interior = 1
            data_plot.set_cmd("-c 1", "-w 1500")
        if fit_plot is not None:
            fit_plot.set_cmd("-c 2", "-w 1000")

        layer.xscale = "log10"
        layer.yscale = "linear"
        layer.rescale()
        self._style_grid(layer)
        self._set_axis_labels(layer, life_column, response_column)
        self._add_formula_label(layer, fit, life_column, response_column, title)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        graph.activate()
        exported = graph.save_fig(str(output_path.resolve()), width=1600)
        exported_path = Path(exported) if exported else output_path
        if not exported_path.exists():
            raise OriginAutomationError(f"Origin did not export figure: {output_path}")
        return exported_path

    def create_e739_project(
        self,
        jobs: list[OriginE739Job],
        summary: pd.DataFrame,
        output_path: Path,
        figures_dir: Path | None = None,
        symbol_kind: int = 3,
        graph_template_path: Path | None = None,
    ) -> tuple[Path, list[dict[str, str]]]:
        self._op.new(False)
        if not jobs:
            raise OriginAutomationError("No E739 analysis jobs to write to Origin.")

        summary_book = self._op.new_book("w", lname="E739 Summary")
        summary_wks = summary_book[0]
        summary_wks.name = "Summary"
        summary_wks.from_df(summary)

        figure_records: list[dict[str, str]] = []
        for job in jobs:
            book = self._op.new_book("w", lname=job.title)
            data_wks = book[0]
            data_wks.name = "Data"
            data_wks.from_df(job.fit.data)

            curve_wks = book.add_sheet("CurveBand")
            curve_wks.from_df(job.fit.curve)

            level_wks = book.add_sheet("Levels")
            level_wks.from_df(job.fit.level_stats)

            job_summary = summary[summary["label"] == job.label] if "label" in summary else summary
            summary_wks = book.add_sheet("Summary")
            summary_wks.from_df(job_summary.reset_index(drop=True))

            record: dict[str, str] = {"label": job.label}
            if figures_dir is not None:
                engineering_path = figures_dir / f"{job.label}_e739_engineering.png"
                linearized_path = figures_dir / f"{job.label}_e739_linearized.png"
            else:
                engineering_path = None
                linearized_path = None

            record["engineering_figure"] = str(
                self._plot_e739_engineering(
                    job,
                    data_wks,
                    curve_wks,
                    engineering_path,
                    symbol_kind,
                    graph_template_path,
                )
                or ""
            )
            record["linearized_figure"] = str(
                self._plot_e739_linearized(
                    job,
                    data_wks,
                    curve_wks,
                    linearized_path,
                    symbol_kind,
                )
                or ""
            )
            figure_records.append(record)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        saved = self._op.save(str(output_path.resolve()))
        if not saved or not output_path.exists():
            raise OriginAutomationError(f"Origin did not save project: {output_path}")
        return output_path, figure_records

    def _plot_e739_engineering(
        self,
        job: OriginE739Job,
        data_wks,
        curve_wks,
        output_path: Path | None,
        symbol_kind: int,
        graph_template_path: Path | None,
    ) -> Path | None:
        graph = self._new_e739_graph(f"{job.title} E739", graph_template_path)
        layer = graph[0]
        self._clear_template_text_labels(layer)
        lower_plot = layer.add_plot(curve_wks, "response", "life_lower_band", type="line")
        upper_plot = layer.add_plot(curve_wks, "response", "life_upper_band", type="line")
        fit_plot = layer.add_plot(curve_wks, "response", "life_fit", type="line")
        data_plot = layer.add_plot(data_wks, "e739_response", "e739_life", type="scatter")

        self._style_confidence_plot(lower_plot)
        self._style_confidence_plot(upper_plot)
        if fit_plot is not None:
            fit_plot.set_cmd("-c 2", "-w 1000")
        if data_plot is not None:
            data_plot.symbol_kind = symbol_kind
            data_plot.symbol_size = 15
            data_plot.symbol_interior = 1
            data_plot.set_cmd("-c 1", "-w 1500")

        layer.xscale = "log10"
        layer.yscale = "log10" if job.fit.result.x_transform == "log" else "linear"
        layer.rescale()
        self._set_e739_engineering_limits(layer, job.fit)
        self._style_grid(layer)
        self._delete_legend(layer)
        self._set_axis_label_text(
            layer,
            "疲劳寿命 N\\-(f) / cycles",
            "最大应变 \\x(03B5)\\-(max)",
        )
        self._add_e739_engineering_label(layer, job)
        if output_path is None:
            return None
        return self._export_graph(graph, output_path)

    def _plot_e739_linearized(
        self,
        job: OriginE739Job,
        data_wks,
        curve_wks,
        output_path: Path | None,
        symbol_kind: int,
    ) -> Path | None:
        graph = self._op.new_graph(lname=f"{job.title} E739 Linearized")
        layer = graph[0]
        lower_plot = layer.add_plot(
            curve_wks,
            "log10_life_lower_band",
            "e739_x",
            type="line",
        )
        upper_plot = layer.add_plot(
            curve_wks,
            "log10_life_upper_band",
            "e739_x",
            type="line",
        )
        fit_plot = layer.add_plot(curve_wks, "log10_life_fit", "e739_x", type="line")
        data_plot = layer.add_plot(
            data_wks,
            "e739_y_log10_life",
            "e739_x",
            type="scatter",
        )

        self._style_confidence_plot(lower_plot)
        self._style_confidence_plot(upper_plot)
        if fit_plot is not None:
            fit_plot.set_cmd("-c 2", "-w 1000")
        if data_plot is not None:
            data_plot.symbol_kind = symbol_kind
            data_plot.symbol_size = 15
            data_plot.symbol_interior = 1
            data_plot.set_cmd("-c 1", "-w 1500")

        layer.xscale = "linear"
        layer.yscale = "linear"
        layer.rescale()
        self._set_e739_linearized_limits(layer, job.fit)
        self._style_grid(layer)
        self._delete_legend(layer)
        x_label = "log10(response)" if job.fit.result.x_transform == "log" else "response"
        self._set_axis_label_text(layer, x_label, "log10(N)")
        self._add_e739_linearized_label(layer, job)
        if output_path is None:
            return None
        return self._export_graph(graph, output_path)

    def _set_axis_labels(self, layer, life_column: str, response_column: str) -> None:
        self._set_axis_label_text(layer, f"{life_column} (log10)", response_column)

    def _set_axis_label_text(self, layer, x_text: str, y_text: str) -> None:
        x_label = layer.label("xb")
        if x_label is not None:
            x_label.text = x_text
            x_label.set_int("verbatim", 0)
        y_label = layer.label("yl")
        if y_label is not None:
            y_label.text = y_text
            y_label.set_int("verbatim", 0)

    def _style_grid(self, layer) -> None:
        layer.lt_exec(
            "layer.x.grid.show=3;"
            "layer.y.grid.show=3;"
            "layer.x.grid.majorcolor=18;"
            "layer.y.grid.majorcolor=18;"
            "layer.x.grid.minorcolor=19;"
            "layer.y.grid.minorcolor=19;"
            "layer.x.grid.majorstyle=2;"
            "layer.y.grid.majorstyle=2;"
            "layer.x.grid.minorstyle=3;"
            "layer.y.grid.minorstyle=3"
        )

    def _add_formula_label(
        self,
        layer,
        fit: SNCurveFit,
        life_column: str,
        response_column: str,
        title: str,
    ) -> None:
        text = self._origin_formula_text(title, fit)
        x_position = 10 ** (
            0.9 * self._safe_log10(fit.result.life_min)
            + 0.1 * self._safe_log10(fit.result.life_max)
        )
        y_position = fit.result.response_min + 0.24 * (
            fit.result.response_max - fit.result.response_min
        )
        label = layer.add_label(text, x_position, y_position)
        if label is not None:
            label.set_int("verbatim", 0)
            label.set_int("attach", 2)
            label.set_float("x1", x_position)
            label.set_float("y1", y_position)

    def _style_confidence_plot(self, plot) -> None:
        if plot is not None:
            plot.set_cmd("-c 15", "-w 500")

    def _new_e739_graph(self, title: str, graph_template_path: Path | None):
        template_path = graph_template_path or self._default_e739_graph_template()
        if template_path is not None and template_path.exists():
            return self._op.new_graph(lname=title, template=str(template_path.resolve()))
        return self._op.new_graph(lname=title)

    def _default_e739_graph_template(self) -> Path | None:
        template = resources.files("originnsfit").joinpath("templates/e739_graph1.otpu")
        if not template.is_file():
            return None
        stack = ExitStack()
        self._resource_stack.enter_context(stack)
        return stack.enter_context(resources.as_file(template))

    def _clear_template_text_labels(self, layer) -> None:
        for name in ("Text", "Text1", "Text2", "Text3", "Label", "Label1"):
            try:
                label = layer.label(name)
                if label is not None:
                    layer.remove_label(label)
            except Exception:
                pass

    def _set_e739_engineering_limits(self, layer, fit: E739Fit) -> None:
        x_min = min(float(fit.curve["life_lower_band"].min()), fit.result.life_min)
        x_max = max(float(fit.curve["life_upper_band"].max()), fit.result.life_max)
        layer.set_xlim(*self._expanded_log_limits(x_min, x_max, pad=0.06))
        if fit.result.x_transform == "log":
            layer.set_ylim(
                *self._expanded_log_limits(
                    fit.result.response_min,
                    fit.result.response_max,
                    pad=0.08,
                )
            )
        else:
            layer.set_ylim(
                *self._expanded_linear_limits(
                    fit.result.response_min,
                    fit.result.response_max,
                    pad=0.08,
                )
            )

    def _set_e739_linearized_limits(self, layer, fit: E739Fit) -> None:
        layer.set_xlim(*self._expanded_linear_limits(fit.result.x_min, fit.result.x_max, pad=0.06))
        y_min = min(
            float(fit.data["e739_y_log10_life"].min()),
            float(fit.curve["log10_life_lower_band"].min()),
        )
        y_max = max(
            float(fit.data["e739_y_log10_life"].max()),
            float(fit.curve["log10_life_upper_band"].max()),
        )
        layer.set_ylim(*self._expanded_linear_limits(y_min, y_max, pad=0.08))

    def _delete_legend(self, layer) -> None:
        for name in ("Legend", "legend"):
            try:
                label = layer.label(name)
                if label is not None:
                    layer.remove_label(label)
                    return
            except Exception:
                pass
        try:
            layer.lt_exec("legend -d")
        except Exception:
            pass

    def _add_e739_linearized_label(self, layer, job: OriginE739Job) -> None:
        fit = job.fit
        x_position = fit.result.x_min + 0.52 * (fit.result.x_max - fit.result.x_min)
        y_values = fit.data["e739_y_log10_life"]
        y_min = float(y_values.min())
        y_max = float(y_values.max())
        y_position = y_min + 0.9 * (y_max - y_min)
        text = (
            f"{job.title}\n"
            f"log10(N) = {fit.result.coefficient_a:.6g} "
            f"{self._origin_signed(fit.result.coefficient_b)} X\n"
            f"{fit.result.confidence:.0%} confidence band, "
            f"R\\+(2) = {fit.result.r2:.5f}"
        )
        self._add_layer_label(layer, text, x_position, y_position)

    def _add_e739_engineering_label(self, layer, job: OriginE739Job) -> None:
        fit = job.fit
        x_position = 10 ** (
            0.72 * self._safe_log10(fit.result.life_min)
            + 0.28 * self._safe_log10(fit.result.life_max)
        )
        if fit.result.x_transform == "log":
            y_position = 10 ** (
                0.05 * self._safe_log10(fit.result.response_min)
                + 0.95 * self._safe_log10(fit.result.response_max)
            )
        else:
            y_position = fit.result.response_min + 0.82 * (
                fit.result.response_max - fit.result.response_min
            )
        text = (
            f"{self._origin_life_response_formula(fit)}\n"
            f"{fit.result.confidence:.0%} 置信带"
        )
        self._add_layer_label(layer, text, x_position, y_position)

    def _add_layer_label(self, layer, text: str, x_position: float, y_position: float) -> None:
        label = layer.add_label(text, x_position, y_position)
        if label is not None:
            label.set_int("verbatim", 0)
            label.set_int("attach", 2)
            label.set_float("x1", x_position)
            label.set_float("y1", y_position)

    def _export_graph(self, graph, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        graph.activate()
        exported = graph.save_fig(str(output_path.resolve()), width=1600)
        exported_path = Path(exported) if exported else output_path
        if not exported_path.exists():
            raise OriginAutomationError(f"Origin did not export figure: {output_path}")
        return exported_path

    def _origin_formula_text(self, title: str, fit: SNCurveFit) -> str:
        return (
            f"{title}\n"
            f"\\x(0394)\\x(03B5) = {fit.result.coefficient_a:.6g} "
            f"(N\\-(f))\\+({fit.result.coefficient_b:.6g})\n"
            f"R\\+(2) = {fit.result.r2:.5f}"
        )

    def _origin_life_response_formula(self, fit: E739Fit) -> str:
        if fit.result.x_transform != "log":
            return fit.result.life_response_formula
        return (
            f"N\\-(f) = {fit.result.life_response_coefficient_a:.6g} "
            f"* (\\x(03B5)\\-(max))\\+({fit.result.life_response_coefficient_b:.6g})"
        )

    @staticmethod
    def _origin_signed(value: float) -> str:
        if value < 0:
            return f"- {abs(value):.6g}"
        return f"+ {value:.6g}"

    @staticmethod
    def _expanded_linear_limits(low: float, high: float, pad: float) -> tuple[float, float]:
        if high == low:
            margin = abs(high) * pad or pad
        else:
            margin = (high - low) * pad
        return low - margin, high + margin

    @staticmethod
    def _expanded_log_limits(low: float, high: float, pad: float) -> tuple[float, float]:
        if low <= 0 or high <= 0:
            return OriginClient._expanded_linear_limits(low, high, pad)
        log_low = math.log10(low)
        log_high = math.log10(high)
        if log_high == log_low:
            margin = pad
        else:
            margin = (log_high - log_low) * pad
        return 10 ** (log_low - margin), 10 ** (log_high + margin)

    @staticmethod
    def _safe_log10(value: float) -> float:
        return 0.0 if value <= 0 else math.log10(value)
