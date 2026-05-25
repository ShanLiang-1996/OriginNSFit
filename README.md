# OriginNSFit

OriginNSFit 用于批量读取 S-N / ε-N 疲劳数据，按 ASTM E739 的线性化流程完成统计分析，并自动生成 Origin 项目文件。

默认 E739 模型：

```text
Y = A + B X
Y = log10(N)
X = log10(应力/应变响应)   # 默认
```

也可以用 `--e739-x-transform linear` 切换为 `X = 应力/应变响应`。程序会输出参数估计、A/B 的置信区间、整条中位曲线的置信带、重复水平统计和线性充分性 F 检验。E739 的这些基础流程只适用于失效寿命数据；如果数据中有 run-out / suspended test，请用 `--status` 指定状态列，程序会在结果中给出警告。

## 数据格式

CSV 可以包含多组试验块，格式参考 [examples/e739_example.csv](examples/e739_example.csv)：

```csv
E739示例,,
试样ID,塑性应变幅,寿命,名义水平
E739-001,0.01636,168,L1
E739-002,0.01609,200,L1
```

每个 `试验X,,` 或类似单独标题行会被识别为一组。常用列：

- `寿命`：疲劳寿命 N，必须为正数。
- `应变幅` / `应力幅` / `stress` / `strain`：受控响应量，默认按 `log10` 进入 E739 的 X。
- `名义水平`：可选，用于把略有差异但属于同一名义水平的重复试验分组，供 F 检验使用。
- `状态`：可选，用于标记 run-out / suspended 等非失效数据。

如果列名不同，可以手动指定：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --life "N" --response "S"
```

## 环境准备

联网环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

离线环境请看 [offline/README.md](offline/README.md)。离线调整 Origin 绘图代码时，可参考 [docs/originpro_plotting_manual.md](docs/originpro_plotting_manual.md)。

## 验证 E739 分析

只计算并输出 CSV，不启动 Origin：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input examples --output output --pattern e739_example.csv --level "名义水平" --dry-run
```

输出文件：

```text
output/e739_summary.csv             每组 E739 参数、置信区间、F 检验、公式和 Origin/图片路径
output/e739_transformed_data.csv    原始有效点、X/Y 线性化值、拟合值、残差
output/e739_curve_bands.csv         中位曲线和置信带采样点
output/e739_level_stats.csv         重复水平的均值、数量、残差统计
```

## 生成 Origin 项目

电脑上安装 Origin / OriginPro 后，去掉 `--dry-run`：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --pattern "*.csv"
```

默认会生成：

```text
output/e739_analysis.opju
output/figures/
```

Origin 项目中包含总汇总工作簿、每组数据的有效点表、置信带采样表、重复水平统计表、E739 线性化图，以及工程习惯的 S-N / ε-N 图。

主工程图默认使用包内模板 `src/originnsfit/templates/e739_graph1.otpu`，该模板来自示例项目中修改后的 Graph1。若要改外观，可以在 Origin 中调整一张图后另存为 `.otpu`，再运行时指定：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --graph-template "C:\path\to\your_template.otpu"
```

工程图公式会显示为 `N_f = a * (ε_max)^b`，其中 `a = 10^A`、`b = B`，由 E739 的 `log10(N) = A + B log10(response)` 换算得到。

如果需要旧版幂律拟合流程：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --analysis power --input data --output output
```

## 打包 exe

```powershell
.\.venv\Scripts\pyinstaller.exe OriginNSFit.spec
```

打包结果会输出到：

```text
dist\OriginNSFit.exe
```

## 目录

```text
src/originnsfit/       Python 包源码
examples/              示例 S-N / ε-N 数据
data/                  本地批量输入数据，默认忽略
output/                分析结果、Origin 项目和导出图像，默认忽略
offline/               离线部署教程和 wheel 资源
```
