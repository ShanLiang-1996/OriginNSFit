# OriginNSFit 使用手册

本文档面向需要批量完成 S-N / epsilon-N 疲劳数据分析、导出 CSV、生成 Origin 项目和图像的用户。项目当前重点支持 ASTM E739 线性化流程，并额外提供 shifted-log 和带 run-out 右删失的 threshold-log MLE 模型。

## 1. 项目能做什么

OriginNSFit 可以完成以下工作：

- 批量读取 `csv`、`tsv`、`txt`、`xlsx`、`xls` 数据文件。
- 自动识别疲劳寿命列和应力/应变响应列，也支持命令行手动指定列名。
- 按 ASTM E739 的线性化流程拟合 `log10(N) = A + B X`。
- 支持三类 E739 模型：
  - `standard`：标准线性化模型。
  - `shifted-log`：`log10(N) = A + B log10(S - C)`，用非线性最小二乘拟合。
  - `threshold_log_mle`：`log10(N) = A + B log10(S - C) + error`，并将 run-out 作为右删失数据进入最大似然。
- 对所有模型识别 run-out / suspended 行：
  - `standard` 和 `shifted-log`：run-out 不进入 OLS/NLS 拟合，但会保留在 `e739_runout_data.csv` 和 Origin 图中。
  - `threshold_log_mle`：run-out 作为右删失观测进入 `norm.logsf` 似然，同时也会在输出和图中标识。
- 输出汇总表、线性化数据、置信带采样点、重复水平统计表。
- 自动生成 Origin 项目，工程图中 run-out 点显示为空心散点加右箭头。
- 默认优先保存旧版 Origin 更容易打开的 `.opj`，失败时自动尝试 `.opju`。

## 2. 推荐目录结构

```text
OriginNSFit/
  data/                  放你的批量输入数据
  examples/              示例数据
  output/                程序输出目录
  src/originnsfit/       程序源码
  docs/                  使用说明和开发参考
  offline/               离线部署文件
```

建议把真实试验数据放入 `data/`，把程序输出统一放入 `output/`。`output/` 中的结果文件会随每次运行更新。

## 3. 安装

### 3.1 联网电脑安装

在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

验证命令：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input examples --output output --pattern e739_example.csv --level "名义水平" --dry-run
```

如果命令成功，会生成 `output/e739_summary.csv`、`output/e739_transformed_data.csv`、`output/e739_curve_bands.csv` 和 `output/e739_level_stats.csv`。

### 3.2 离线电脑安装

离线电脑请优先使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\offline\install_offline.ps1
```

离线安装依赖于 `offline/wheelhouse/` 中的 wheel 文件。当前离线包主要面向 Windows x64 + Python 3.12。如果离线电脑 Python 版本不同，需要在联网电脑重新下载对应 wheel。

详细步骤见 [offline/README.md](../offline/README.md)。

## 4. 输入数据格式

最小 CSV 示例：

```csv
E739示例,,
试样ID,塑性应变幅,寿命,名义水平,状态
E739-001,0.01636,168,L1,failure
E739-002,0.01609,200,L1,failure
E739-003,0.00675,1000,L2,runout
```

项目中也提供了可直接运行的 run-out 示例：[examples/e739_runout_example.csv](../examples/e739_runout_example.csv)。

说明：

- 单独的标题行，如 `E739示例,,`，会被识别为一个数据组。
- 第一行真正的列名应包含寿命列和响应列。
- 一份文件中可以包含多个数据组。
- CSV 建议使用 UTF-8 with BOM，即 `utf-8-sig`，Excel 和中文列名更稳定。

### 4.1 常用列

```text
寿命          疲劳寿命 N，必须为正数
塑性应变幅    响应量 S，可替换为应变最大值、应变幅、应力幅等
名义水平      可选，用于重复水平和线性充分性 F 检验
状态          可选，用于标记 failure / runout / suspended
```

如果你的列名不同，可以手动指定：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --life "N" --response "S"
```

### 4.2 run-out 状态写法

程序会把以下状态识别为失效点：

```text
failure, failed, fail, fracture, broken, yes, true, 1
```

程序会把以下状态识别为 run-out / 非失效点：

```text
runout, run-out, run out, suspended, suspension, censored, right-censored, no, false, 0
```

空白或无法识别的状态默认按失效点处理。建议在数据中明确写 `failure` 或 `runout`。

## 5. 模型说明

### 5.1 standard

默认模型：

```text
Y = A + B X
Y = log10(N)
X = log10(S)      默认
```

也可以用：

```powershell
--e739-x-transform linear
```

此时：

```text
X = S
```

当提供 `--status` 时，`standard` 模型只用失效点拟合。run-out 点不会进入 OLS 拟合，但会输出到 `e739_runout_data.csv`，并在 Origin 图中显示为空心散点加右箭头。

### 5.2 shifted-log

模型：

```text
log10(N) = A + B log10(S - C)
```

调用：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --e739-model shifted-log
```

`C` 由非线性最小二乘拟合得到，要求 `S - C > 0`。当提供 `--status` 时，run-out 点同样不进入拟合，但会保留在 run-out 输出和图中。

### 5.3 threshold_log_mle

模型：

```text
log10(N) = A + B log10(S - C) + error
error ~ Normal(0, sigma^2)
```

调用：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --pattern "*.csv" --status "状态" --e739-model threshold_log_mle
```

参数约束：

```text
C < min(S)
B < 0
sigma > 0
```

失效点的似然贡献为正态密度。run-out 点只知道真实失效寿命大于观测寿命，因此用正态生存概率进入似然：

```text
log L_runout = log P(Y > observed log10(N))
```

实现中使用 `scipy.stats.norm.logsf`，避免直接计算 `log(1 - cdf)` 带来的数值不稳定。

## 6. 常用命令

### 6.1 只输出 CSV，不启动 Origin

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --pattern "*.csv" --dry-run
```

### 6.2 指定寿命列和响应列

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --life "寿命" --response "最大应变"
```

### 6.3 加入名义水平

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --level "名义水平"
```

### 6.4 加入 run-out 标识

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --status "状态"
```

### 6.5 使用右删失 MLE 模型

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --status "状态" --e739-model threshold_log_mle
```

### 6.6 兼容旧版 Origin，不使用模板

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --no-graph-template
```

### 6.7 同时输出线性化图

默认只生成工程图。如果还需要 E739 线性化图，添加：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --linearized-graph
```

### 6.8 隐藏 run-out 箭头

保留 run-out 空心散点，但不显示右箭头：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --status "状态" --no-runout-arrows
```

### 6.9 指定自己的 Origin 图模板

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --graph-template "C:\path\to\your_template.otpu"
```

## 7. 输出文件

E739 工作流会在 `output/` 里生成：

```text
e739_summary.csv             每组模型参数、置信区间、公式、统计量、Origin/图片路径
e739_transformed_data.csv    参与主要拟合流程的数据点及线性化结果
e739_runout_data.csv         仅当存在 run-out 时生成，记录 run-out 行及其绘图坐标
e739_curve_bands.csv         中位曲线和置信带采样点
e739_level_stats.csv         重复水平统计和线性充分性 F 检验所需数据
origin_automation.log        Origin 自动化失败时生成，记录错误
e739_analysis.opj            Origin 项目，默认优先输出旧版兼容格式
figures/                     Origin 导出的 PNG 图像
```

`e739_summary.csv` 中常用字段：

```text
coefficient_a / coefficient_b / coefficient_c
threshold
sigma
r2_log_life
rmse_log_life
n_failure
n_runout
log_likelihood
negative_log_likelihood
log_life_formula
life_response_formula
warnings
```

## 8. 图像说明

Origin 项目中每个数据组默认包含工程图：

- 工程图：横轴为疲劳寿命 `N_f / cycles`，纵轴为响应量，如最大应变、应变幅或应力幅。

如果运行时添加 `--linearized-graph`，还会额外生成线性化图：横轴为 `log10(response)`、`response` 或 `log10(response - C)`，纵轴为 `log10(N)`。

run-out 点的显示方式：

- 失效点：空心散点。
- run-out 点：空心散点，并在点右侧添加右箭头；添加 `--no-runout-arrows` 时只显示空心散点。
- 对 `standard` / `shifted-log`，run-out 不影响拟合线和置信带。
- 对 `threshold_log_mle`，run-out 同时影响最大似然参数，并在图中标识。

工程图公式显示为：

```text
N_f = a * (响应量)^b
```

或：

```text
N_f = a * (响应量 - C)^b
```

其中 `a = 10^A`，`b = B`。

## 9. Origin 版本兼容

### 9.1 Origin 2018 或更低版本建议

如果旧版 Origin 打不开模板或图形创建异常，优先使用：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --no-graph-template
```

程序默认使用 LabTalk `plotxy` 方式把散点、拟合线和置信带显式追加到同一个图层，避免旧版 Origin 中出现一条曲线生成一张图的问题。

### 9.2 网格显示

新版 Origin 通常支持：

```text
layer.x.grid.show=3
layer.y.grid.show=3
```

部分旧版 Origin 对该对象属性刷新不稳定。项目现在同时调用旧式 LabTalk：

```text
axis -ps X G 3
axis -ps Y G 3
```

再设置 `layer.x.grid.majorcolor`、`majortype`、`minorcolor` 等属性。这样旧版负责先显示网格，新版负责细化颜色和线型。

## 10. 离线电脑排查

如果 CSV 正常生成，但 Origin 项目没有生成：

1. 确认命令没有加 `--dry-run`。
2. 确认命令没有加 `--hidden-origin`。
3. 在离线电脑手动打开 Origin，确认许可证、首次启动弹窗、用户文件夹设置都已完成。
4. 查看：

```text
output/origin_automation.log
```

5. 单独测试 Origin 自动化：

```powershell
.\.venv\Scripts\python.exe -c "import originpro as op; op.set_show(True); print('Origin should open'); op.exit()"
```

6. 如果模板兼容性可疑，加 `--no-graph-template` 重试。

## 11. 最小验证脚本

项目包含一个最小验证脚本：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_threshold_log_mle.py
```

它会验证：

- 无 run-out 时 `threshold_log_mle` 可以拟合。
- 有 run-out 时 run-out 进入 `logsf` 右删失似然。
- `C < min(S)`。
- `sigma > 0`。
- `B < 0`。
- `standard` 模型带 `--status` 时，只用失效点拟合，同时保留 run-out 输出。
- CLI 能导出 `e739_runout_data.csv`。

## 12. 常见问题

### 12.1 中文 CSV 打开乱码

程序写出的 CSV 使用 `utf-8-sig`。如果你自己准备输入 CSV，建议也保存为 UTF-8 with BOM。Excel 中可以使用“另存为 CSV UTF-8”。

### 12.2 为什么 standard 模型不把 run-out 放进拟合

标准 E739 OLS 模型只适用于已失效寿命点。run-out 表示真实失效寿命大于观测寿命，不能直接当作失效寿命使用。若要让 run-out 参与统计估计，应使用 `threshold_log_mle`。

### 12.3 低应变点没有进入 shifted-log 或 threshold-log

这两个模型要求 `S - C > 0`。如果某些行不满足模型定义域，程序会在 `warnings` 字段中记录，并从绘图用 run-out 数据中剔除这些点。

### 12.4 Origin 窗口不显示

检查是否使用了 `--hidden-origin`。如果没有使用，但仍不显示，优先测试 `originpro` 是否能打开 Origin，或查看 `origin_automation.log`。

### 12.5 输出目录里文件太多

核心结果优先看：

```text
output/e739_summary.csv
output/e739_transformed_data.csv
output/e739_runout_data.csv
output/e739_analysis.opj
output/figures/
```

如果本次没有 run-out，程序会删除旧的 `e739_runout_data.csv`，避免误读历史结果。
