from __future__ import annotations

import math
from pathlib import Path

from .fitting import SNCurveFit


class OriginAutomationError(RuntimeError):
    """Raised when Origin automation cannot be completed."""


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

    def __enter__(self) -> "OriginClient":
        if self._visible:
            try:
                self._op.set_show(True)
            except TypeError:
                self._op.set_show()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            self._op.exit()
        except Exception:
            pass

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
            data_plot.symbol_size = 12
            data_plot.symbol_interior = 1
            data_plot.set_cmd("-c 1", "-w 2")
        if fit_plot is not None:
            fit_plot.set_cmd("-c 2", "-w 3")

        layer.xscale = "log10"
        layer.yscale = "log10"
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

    def _set_axis_labels(self, layer, life_column: str, response_column: str) -> None:
        x_label = layer.label("xb")
        if x_label is not None:
            x_label.text = f"{life_column} (log10)"
        y_label = layer.label("yl")
        if y_label is not None:
            y_label.text = f"{response_column} (log10)"

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
        y_position = 10 ** (
            0.8 * self._safe_log10(fit.result.response_min)
            + 0.2 * self._safe_log10(fit.result.response_max)
        )
        label = layer.add_label(text, x_position, y_position)
        if label is not None:
            label.set_int("verbatim", 0)
            label.set_int("attach", 2)
            label.set_float("x1", x_position)
            label.set_float("y1", y_position)

    def _origin_formula_text(self, title: str, fit: SNCurveFit) -> str:
        return (
            f"{title}\n"
            f"\\x(0394)\\x(03B5) = {fit.result.coefficient_a:.6g} "
            f"(N\\-(f))\\+({fit.result.coefficient_b:.6g})\n"
            f"R\\+(2) = {fit.result.r2:.5f}"
        )

    @staticmethod
    def _safe_log10(value: float) -> float:
        return 0.0 if value <= 0 else math.log10(value)
