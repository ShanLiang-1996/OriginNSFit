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


@dataclass(frozen=True)
class ResponsePresentation:
    axis_label: str
    formula_variable: str


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
        use_default_graph_template: bool = True,
    ) -> tuple[Path, list[dict[str, str]]]:
        self._op.new(False)
        if not jobs:
            raise OriginAutomationError("No E739 analysis jobs to write to Origin.")

        summary_book = self._op.new_book("w", lname="E739 Summary")
        summary_wks = summary_book[0]
        summary_wks.name = "Summary"
        self._write_frame_to_sheet(summary_wks, summary)

        figure_records: list[dict[str, str]] = []
        for job in jobs:
            book = self._op.new_book("w", lname=job.title)
            data_wks = book[0]
            data_wks.name = "Data"
            self._write_frame_to_sheet(data_wks, job.fit.data)

            curve_wks = book.add_sheet("CurveBand")
            self._write_frame_to_sheet(curve_wks, job.fit.curve)

            level_wks = book.add_sheet("Levels")
            self._write_frame_to_sheet(level_wks, job.fit.level_stats)

            job_summary = summary[summary["label"] == job.label] if "label" in summary else summary
            summary_wks = book.add_sheet("Summary")
            self._write_frame_to_sheet(summary_wks, job_summary.reset_index(drop=True))

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
                    use_default_graph_template,
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

        saved_project = self._save_project(output_path)
        return saved_project, figure_records

    def _plot_e739_engineering(
        self,
        job: OriginE739Job,
        data_wks,
        curve_wks,
        output_path: Path | None,
        symbol_kind: int,
        graph_template_path: Path | None,
        use_default_graph_template: bool,
    ) -> Path | None:
        graph = self._new_e739_graph(
            f"{job.title} E739",
            graph_template_path,
            use_default_graph_template,
        )
        layer = graph[0]
        self._clear_template_text_labels(layer)
        self._clear_layer_plots(layer)
        graph_name = self._graph_name(graph)

        self._plotxy_from_wks(
            curve_wks,
            self._column_index(job.fit.curve, "life_lower_band"),
            self._column_index(job.fit.curve, "response"),
            plot_code=200,
            target_graph=graph_name,
        )
        self._plotxy_from_wks(
            curve_wks,
            self._column_index(job.fit.curve, "life_upper_band"),
            self._column_index(job.fit.curve, "response"),
            plot_code=200,
            target_graph=graph_name,
        )
        self._plotxy_from_wks(
            curve_wks,
            self._column_index(job.fit.curve, "life_fit"),
            self._column_index(job.fit.curve, "response"),
            plot_code=200,
            target_graph=graph_name,
        )
        self._plotxy_from_wks(
            data_wks,
            self._column_index(job.fit.data, "e739_life"),
            self._column_index(job.fit.data, "e739_response"),
            plot_code=201,
            target_graph=graph_name,
        )

        graph = self._find_graph(graph_name) or graph
        layer = graph[0]
        plots = self._plot_list(layer)
        lower_plot = plots[0] if len(plots) > 0 else None
        upper_plot = plots[1] if len(plots) > 1 else None
        fit_plot = plots[2] if len(plots) > 2 else None
        data_plot = plots[3] if len(plots) > 3 else None
        if len(plots) < 4:
            raise OriginAutomationError(
                f"Origin created only {len(plots)} engineering plot(s) for {job.label}."
            )

        self._style_confidence_plot(lower_plot)
        self._style_confidence_plot(upper_plot)
        if fit_plot is not None:
            self._safe_plot_cmd(fit_plot, "-c 2", "-w 1000")
        if data_plot is not None:
            self._style_data_plot(data_plot, symbol_kind)

        self._set_layer_scale(
            layer,
            "log10",
            "log10" if job.fit.result.x_transform == "log" else "linear",
        )
        self._safe_rescale(layer)
        self._set_e739_engineering_limits(layer, job.fit)
        self._style_grid(layer)
        self._delete_legend(layer)
        self._set_axis_label_text(
            layer,
            "疲劳寿命 N\\-(f) / cycles",
            self._response_presentation(job.fit.result.response_column).axis_label,
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
        if graph is None:
            raise OriginAutomationError("Origin did not create a linearized graph page.")
        layer = graph[0]
        self._clear_layer_plots(layer)
        graph_name = self._graph_name(graph)

        self._plotxy_from_wks(
            curve_wks,
            self._column_index(job.fit.curve, "e739_x"),
            self._column_index(job.fit.curve, "log10_life_lower_band"),
            plot_code=200,
            target_graph=graph_name,
        )
        self._plotxy_from_wks(
            curve_wks,
            self._column_index(job.fit.curve, "e739_x"),
            self._column_index(job.fit.curve, "log10_life_upper_band"),
            plot_code=200,
            target_graph=graph_name,
        )
        self._plotxy_from_wks(
            curve_wks,
            self._column_index(job.fit.curve, "e739_x"),
            self._column_index(job.fit.curve, "log10_life_fit"),
            plot_code=200,
            target_graph=graph_name,
        )
        self._plotxy_from_wks(
            data_wks,
            self._column_index(job.fit.data, "e739_x"),
            self._column_index(job.fit.data, "e739_y_log10_life"),
            plot_code=201,
            target_graph=graph_name,
        )

        graph = self._find_graph(graph_name) or graph
        layer = graph[0]
        plots = self._plot_list(layer)
        lower_plot = plots[0] if len(plots) > 0 else None
        upper_plot = plots[1] if len(plots) > 1 else None
        fit_plot = plots[2] if len(plots) > 2 else None
        data_plot = plots[3] if len(plots) > 3 else None
        if len(plots) < 4:
            raise OriginAutomationError(
                f"Origin created only {len(plots)} linearized plot(s) for {job.label}."
            )

        self._style_confidence_plot(lower_plot)
        self._style_confidence_plot(upper_plot)
        if fit_plot is not None:
            self._safe_plot_cmd(fit_plot, "-c 2", "-w 1000")
        if data_plot is not None:
            self._style_data_plot(data_plot, symbol_kind)

        self._set_layer_scale(layer, "linear", "linear")
        self._safe_rescale(layer)
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
            self._safe_set_int(x_label, "verbatim", 0)
        y_label = layer.label("yl")
        if y_label is not None:
            y_label.text = y_text
            self._safe_set_int(y_label, "verbatim", 0)

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
            self._safe_plot_cmd(plot, "-c 15", "-w 500")

    def _style_data_plot(self, plot, symbol_kind: int) -> None:
        try:
            plot.symbol_kind = symbol_kind
            plot.symbol_size = 15
            plot.symbol_interior = 1
        except Exception:
            pass
        self._safe_plot_cmd(plot, "-c 1", "-w 1500")

    def _safe_plot_cmd(self, plot, *commands: str) -> None:
        try:
            plot.set_cmd(*commands)
        except Exception:
            pass

    def _plotxy_from_wks(
        self,
        wks,
        x_col: int,
        y_col: int,
        plot_code: int,
        target_graph: str | None,
    ) -> str:
        x = x_col + 1
        y = y_col + 1
        data_range = f"{self._worksheet_lt_ref(wks)}!({x},{y})"
        if target_graph:
            output_layer = f"[{target_graph}]1!"
        else:
            output_layer = "[<new>]"
        cmd = f"plotxy iy:={data_range} plot:={plot_code} ogl:={output_layer};"
        self._op.lt_exec(cmd)
        if target_graph:
            self._activate_graph(target_graph)
            return target_graph
        active = self._active_origin_window_name()
        if not active:
            raise OriginAutomationError("Origin did not report the new graph name after plotxy.")
        return active

    def _worksheet_lt_ref(self, wks) -> str:
        try:
            book_name = wks.get_book().name
        except Exception as exc:
            raise OriginAutomationError("Could not resolve Origin workbook name.") from exc
        sheet_name = wks.name
        return f"[{book_name}]{sheet_name}"

    def _column_index(self, frame: pd.DataFrame, column: str) -> int:
        try:
            return int(frame.columns.get_loc(column))
        except KeyError as exc:
            raise OriginAutomationError(f"Column not found for Origin plotting: {column}") from exc

    def _graph_name(self, graph) -> str:
        try:
            name = str(graph.name)
            if name:
                return name
        except Exception:
            pass
        try:
            graph.activate()
        except Exception:
            pass
        name = self._active_origin_window_name()
        if not name:
            raise OriginAutomationError("Could not resolve Origin graph name.")
        return name

    def _active_origin_window_name(self) -> str:
        for getter in ("get_lt_str", "lt_str"):
            try:
                func = getattr(self._op, getter)
            except AttributeError:
                continue
            try:
                return str(func("%H"))
            except Exception:
                continue
        return ""

    def _find_graph(self, graph_name: str):
        try:
            return self._op.find_graph(graph_name)
        except Exception:
            return None

    def _activate_graph(self, graph_name: str) -> None:
        try:
            self._op.lt_exec(f'win -a "{graph_name}";')
        except Exception:
            pass

    def _plot_list(self, layer) -> list:
        try:
            return list(layer.plot_list())
        except Exception:
            return []

    def _new_e739_graph(
        self,
        title: str,
        graph_template_path: Path | None,
        use_default_graph_template: bool,
    ):
        template_path = graph_template_path
        if template_path is None and use_default_graph_template:
            template_path = self._default_e739_graph_template()
        if template_path is not None and template_path.exists():
            try:
                graph = self._op.new_graph(lname=title, template=str(template_path.resolve()))
                if graph is not None:
                    return graph
            except Exception as exc:
                print(f"Origin graph template skipped for compatibility: {exc}")
        graph = self._op.new_graph(lname=title)
        if graph is None:
            raise OriginAutomationError("Origin did not create a graph page.")
        return graph

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

    def _clear_layer_plots(self, layer) -> None:
        try:
            plots = layer.plot_list()
        except Exception:
            return
        for index in range(len(plots) - 1, -1, -1):
            try:
                layer.remove_plot(index)
            except Exception:
                pass

    def _set_e739_engineering_limits(self, layer, fit: E739Fit) -> None:
        x_min = min(float(fit.curve["life_lower_band"].min()), fit.result.life_min)
        x_max = max(float(fit.curve["life_upper_band"].max()), fit.result.life_max)
        self._safe_set_xlim(layer, *self._expanded_log_limits(x_min, x_max, pad=0.06))
        if fit.result.x_transform == "log":
            self._safe_set_ylim(
                layer,
                *self._expanded_log_limits(
                    fit.result.response_min,
                    fit.result.response_max,
                    pad=0.08,
                )
            )
        else:
            self._safe_set_ylim(
                layer,
                *self._expanded_linear_limits(
                    fit.result.response_min,
                    fit.result.response_max,
                    pad=0.08,
                )
            )

    def _set_e739_linearized_limits(self, layer, fit: E739Fit) -> None:
        self._safe_set_xlim(
            layer,
            *self._expanded_linear_limits(fit.result.x_min, fit.result.x_max, pad=0.06),
        )
        y_min = min(
            float(fit.data["e739_y_log10_life"].min()),
            float(fit.curve["log10_life_lower_band"].min()),
        )
        y_max = max(
            float(fit.data["e739_y_log10_life"].max()),
            float(fit.curve["log10_life_upper_band"].max()),
        )
        self._safe_set_ylim(layer, *self._expanded_linear_limits(y_min, y_max, pad=0.08))

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
            self._safe_set_int(label, "verbatim", 0)
            self._safe_set_int(label, "attach", 2)
            self._safe_set_float(label, "x1", x_position)
            self._safe_set_float(label, "y1", y_position)

    def _export_graph(self, graph, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        graph.activate()
        try:
            exported = graph.save_fig(str(output_path.resolve()), width=1600)
        except Exception:
            exported = graph.save_fig(str(output_path.resolve()))
        exported_path = Path(exported) if exported else output_path
        if not exported_path.exists():
            raise OriginAutomationError(f"Origin did not export figure: {output_path}")
        return exported_path

    def _save_project(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        candidates = self._project_save_candidates(output_path)
        for candidate in candidates:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            if self._try_save_project(candidate):
                return candidate
        tried = ", ".join(str(candidate) for candidate in candidates)
        raise OriginAutomationError(f"Origin did not save project. Tried: {tried}")

    def _project_save_candidates(self, output_path: Path) -> list[Path]:
        suffix = output_path.suffix.lower()
        if suffix == ".opj":
            return [output_path, output_path.with_suffix(".opju")]
        if suffix == ".opju":
            return [output_path, output_path.with_suffix(".opj")]
        if suffix:
            return [output_path, output_path.with_suffix(".opj"), output_path.with_suffix(".opju")]
        return [output_path.with_suffix(".opj"), output_path.with_suffix(".opju")]

    def _try_save_project(self, output_path: Path) -> bool:
        try:
            saved = self._op.save(str(output_path.resolve()))
        except Exception:
            return False
        return bool(saved and output_path.exists())

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
        variable = self._response_presentation(fit.result.response_column).formula_variable
        return (
            f"N\\-(f) = {fit.result.life_response_coefficient_a:.6g} "
            f"* ({variable})\\+({fit.result.life_response_coefficient_b:.6g})"
        )

    def _write_frame_to_sheet(self, sheet, frame: pd.DataFrame) -> None:
        try:
            sheet.from_df(frame)
            return
        except Exception as exc:
            print(f"Origin worksheet DataFrame import fallback: {exc}")

        for column_index, column in enumerate(frame.columns):
            values = [
                "" if pd.isna(value) else value
                for value in frame[column].tolist()
            ]
            sheet.from_list(column_index, values, str(column))

    def _response_presentation(self, response_column: str) -> ResponsePresentation:
        text = str(response_column).strip()
        lowered = text.lower().replace("_", " ").replace("-", " ")
        is_stress = "应力" in text or "stress" in lowered or "sigma" in lowered
        is_max = any(token in text for token in ("最大", "峰值")) or any(
            token in lowered
            for token in ("max", "maximum", "peak")
        )
        is_amplitude = "幅" in text or "amplitude" in lowered or lowered.endswith(" amp")

        if is_stress:
            greek = "\\x(03C3)"
            if is_max:
                return ResponsePresentation(f"最大应力 {greek}\\-(max)", f"{greek}\\-(max)")
            if is_amplitude:
                return ResponsePresentation(f"{text} {greek}\\-(a)", f"{greek}\\-(a)")
            return ResponsePresentation(f"{text} {greek}", greek)

        greek = "\\x(03B5)"
        if is_max:
            return ResponsePresentation(f"最大应变 {greek}\\-(max)", f"{greek}\\-(max)")
        if is_amplitude:
            return ResponsePresentation(f"{text} {greek}\\-(a)", f"{greek}\\-(a)")
        return ResponsePresentation(f"{text} {greek}", greek)

    def _safe_set_xlim(self, layer, begin: float, end: float) -> None:
        try:
            layer.set_xlim(begin, end)
        except Exception:
            pass

    def _safe_set_ylim(self, layer, begin: float, end: float) -> None:
        try:
            layer.set_ylim(begin, end)
        except Exception:
            pass

    def _safe_set_int(self, obj, prop: str, value: int) -> None:
        try:
            obj.set_int(prop, value)
        except Exception:
            pass

    def _safe_set_float(self, obj, prop: str, value: float) -> None:
        try:
            obj.set_float(prop, value)
        except Exception:
            pass

    def _set_layer_scale(self, layer, xscale: str, yscale: str) -> None:
        try:
            layer.xscale = xscale
        except Exception:
            pass
        try:
            layer.yscale = yscale
        except Exception:
            pass

    def _safe_rescale(self, layer) -> None:
        try:
            layer.rescale()
        except Exception:
            try:
                layer.lt_exec("layer -r")
            except Exception:
                pass

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
