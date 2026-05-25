# originpro 绘图速查手册

这份手册面向 OriginNSFit 项目离线维护使用，重点覆盖批量 S-N 曲线绘图时最常改的代码位置。示例基于项目依赖中的 `originpro` 包。

## 1. 基本流程

```python
import originpro as op

op.set_show(True)          # 显示 Origin；批处理时可用 False
wks = op.new_sheet("w")    # 新建工作表
graph = op.new_graph()     # 新建图页
layer = graph[0]           # 取第 1 个图层
```

结束时可以调用：

```python
op.exit()
```

在本项目里，这些逻辑封装在 `src/originnsfit/origin_client.py` 的 `OriginClient` 类中。

## 2. 写入数据到 Origin 工作表

`from_list(col, data, lname, axis)` 用于写入列数据：

```python
wks.from_list(0, life_values, "寿命", axis="X")
wks.from_list(1, response_values, "应变幅", axis="Y")
wks.from_list(2, fit_life_values, "寿命_fit", axis="X")
wks.from_list(3, fit_response_values, "应变幅_fit", axis="Y")
```

常用 `axis`：

```text
X   X 列
Y   Y 列
N   普通列
E   Y 误差列
M   X 误差列
L   标签列
```

## 3. 添加数据点和拟合线

散点图：

```python
data_plot = layer.add_plot(wks, 1, 0, type="scatter")
```

线图：

```python
fit_plot = layer.add_plot(wks, 3, 2, type="line")
```

参数顺序是：

```text
add_plot(工作表, Y列索引, X列索引, type=图类型)
```

列索引从 0 开始，所以 `1, 0` 表示第 2 列作为 Y，第 1 列作为 X。

常用图类型：

```text
scatter      散点
line         线
linesymbol   线+点
column       柱状图
```

## 4. 调整数据点样式

当前项目 E739 工程图默认空心圆点：

```python
data_plot.symbol_kind = 2
data_plot.symbol_size = 15
data_plot.symbol_interior = 1
data_plot.set_cmd("-c 1", "-w 1500")
```

常用属性：

```text
symbol_kind       符号形状，项目里 2 为空心圆，3 为三角形
symbol_size       符号大小
symbol_interior   填充方式，1 通常为空心/常规填充
```

`set_cmd()` 可以执行 Origin 的 LabTalk `set` 命令。常用项：

```text
-c 颜色编号
-w 线宽或符号边框相关宽度；部分 Origin 样式中 500 约等于 1 pt
```

如果要改颜色，可以先试：

```python
data_plot.set_cmd("-c 1")   # 黑色
fit_plot.set_cmd("-c 2")    # 红色
```

## 5. 调整拟合线样式

当前项目：

```python
fit_plot.set_cmd("-c 2", "-w 1000")
```

更细：

```python
fit_plot.set_cmd("-c 2", "-w 500")
```

更粗：

```python
fit_plot.set_cmd("-c 2", "-w 1500")
```

## 6. 坐标轴类型

设置 X 轴为 log10：

```python
layer.xscale = "log10"
```

设置 Y 轴为线性：

```python
layer.yscale = "linear"
```

其他可用值包括：

```text
linear
log10
ln
log2
reciprocal
```

改完数据或坐标后，通常调用：

```python
layer.rescale()
```

## 7. 坐标轴标题

Origin 默认坐标轴标签对象名：

```text
xb   X 轴标题
yl   Y 轴标题
```

示例：

```python
x_label = layer.label("xb")
if x_label is not None:
    x_label.text = "寿命 (log10)"

y_label = layer.label("yl")
if y_label is not None:
    y_label.text = "应变幅"
```

## 8. 网格线

项目里使用 `layer.lt_exec()` 执行 LabTalk 来打开网格：

```python
layer.lt_exec(
    "layer.x.grid.show=3;"
    "layer.y.grid.show=3;"
    "layer.x.grid.majorcolor=18;"
    "layer.y.grid.majorcolor=18;"
    "layer.x.grid.minorcolor=19;"
    "layer.x.grid.majorstyle=2;"
    "layer.y.grid.majorstyle=2;"
    "layer.x.grid.minorstyle=3"
)
```

常用含义：

```text
layer.x.grid.show=0   关闭 X 网格
layer.x.grid.show=1   显示 X 主网格
layer.x.grid.show=3   显示 X 主/次网格
layer.y.grid.show=1   显示 Y 主网格
layer.y.grid.show=3   显示 Y 主/次网格
```

如果图太密，可以把 `show=3` 改为 `show=1`。

## 9. 添加公式标签

添加标签：

```python
label = layer.add_label("文本", x_position, y_position)
```

把标签绑定到图层坐标：

```python
label.set_int("attach", 2)
label.set_float("x1", x_position)
label.set_float("y1", y_position)
```

Origin 文本支持转义序列。当前项目用它来渲染公式：

```python
text = (
    "试验1\n"
    "\\x(0394)\\x(03B5) = 0.0588628 (N\\-(f))\\+(-0.241306)\n"
    "R\\+(2) = 0.84482"
)
```

含义：

```text
\x(0394)   希腊大写 Delta，即 Δ
\x(03B5)   希腊小写 epsilon，即 ε
\-(f)      下标 f
\+(2)      上标 2
```

如果文字没有按预期渲染，检查：

```python
label.set_int("verbatim", 0)
```

## 10. 导出图片

```python
graph.activate()
graph.save_fig(r"C:\path\figure.png", width=1600)
```

常用格式：

```text
.png
.jpg
.svg
.emf
```

项目里会检查导出的文件是否真实存在，如果不存在会报错，避免误以为绘图成功。

## 11. 本项目最常修改的位置

绘图主函数：

```text
src/originnsfit/origin_client.py
```

常调参数：

```text
symbol_size       数据点大小
symbol_kind       数据点形状
data_plot.set_cmd 数据点颜色和边框
fit_plot.set_cmd  拟合线颜色和线宽
layer.xscale      X 轴类型
layer.yscale      Y 轴类型
_style_grid       网格设置
_origin_formula_text 公式文字
```

拟合模型和输出：

```text
src/originnsfit/fitting.py
src/originnsfit/cli.py
```

## 12. 调试建议

先只跑拟合：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input examples --output output --pattern example.csv --dry-run
```

确认 CSV 输出后再调用 Origin：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input examples --output output --pattern example.csv
```

如果 Origin 图没有导出，优先检查：

```text
Origin 是否能正常启动
output/figures 是否有写入权限
公式标签坐标是否落在当前轴范围内
layer.rescale() 是否在添加图后调用
```
