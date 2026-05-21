from __future__ import annotations

from pathlib import Path

import pandas as pd


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

    def plot_xy(
        self,
        frame: pd.DataFrame,
        x_column: str,
        y_column: str,
        output_path: Path,
    ) -> Path:
        data = frame[[x_column, y_column]].dropna()
        wks = self._op.new_sheet("w")
        wks.from_list(0, data[x_column].tolist(), x_column)
        wks.from_list(1, data[y_column].tolist(), y_column)

        graph = self._op.new_graph()
        layer = graph[0]
        layer.add_plot(wks, 1, 0)
        layer.rescale()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        graph.save_fig(str(output_path))
        return output_path
