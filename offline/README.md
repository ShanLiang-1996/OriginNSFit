# OriginNSFit 离线部署包

这个目录用于在不能联网的 Windows 电脑上部署 OriginNSFit，并运行 ASTM E739 S-N / ε-N 分析和 Origin 项目生成。

## 适用环境

- Windows 10/11 64 位
- Python 3.12.x 64 位
- Origin / OriginPro 已安装，并可被 Python 自动化调用
- 已从 GitHub 或 U 盘复制完整项目目录，包括 `offline/wheelhouse/`

注意：`offline/wheelhouse/` 中的 wheel 文件按当前开发环境准备，主要面向 `Python 3.12 + Windows x64`。如果离线电脑使用 Python 3.10/3.11 或非 Windows 系统，需要重新准备对应平台的 wheel 包。

## 一键安装

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\offline\install_offline.ps1
```

脚本会执行以下操作：

1. 创建 `.venv` 虚拟环境。
2. 只从 `offline/wheelhouse/` 安装依赖。
3. 安装当前项目包。
4. 打印验证命令。

## 手动安装

如果不想运行脚本，可以在项目根目录手动执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\offline\wheelhouse pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\offline\wheelhouse -r .\offline\requirements-offline.txt
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\offline\wheelhouse --no-build-isolation --no-deps -e .
```

## 验证拟合

只拟合并输出 CSV，不启动 Origin：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input examples --output output --pattern e739_example.csv --level "名义水平" --dry-run
```

成功后会生成：

```text
output\e739_summary.csv
output\e739_transformed_data.csv
output\e739_curve_bands.csv
output\e739_level_stats.csv
```

## 真实连接 Origin

确认 dry-run 成功后，把数据放到 `data/`，并去掉 `--dry-run`：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --pattern "*.csv"
```

默认会生成 Origin 项目和导出图：

```text
output\e739_analysis.opj
output\figures\
```

默认优先保存为旧版 Origin 更容易打开的 `.opj`；如果当前 Origin 不支持保存 `.opj`，会自动退回 `.opju`。如果确实需要 `.opju`，可以用 `--project output\e739_analysis.opju` 明确指定。

Origin 项目中包含总汇总表、每组有效点、线性化值、置信带采样点、重复水平统计、E739 线性化图和工程习惯的 S-N / ε-N 图。

主工程图默认使用包内模板 `src/originnsfit/templates/e739_graph1.otpu`。如果需要换成新的 Origin 图模板，可以运行时加 `--graph-template "C:\path\to\your_template.otpu"`。

如果 Origin 2018 等旧版对 `.otpu` 模板不兼容，可以加 `--no-graph-template`。E739 图形绘制默认走 LabTalk `plotxy` 兼容路径，程序会把散点、拟合线和置信带明确追加到同一个图层，避免一条曲线生成一张图。Origin 自动化失败时会写出 `output/origin_automation.log`，离线电脑上可以先看这个文件里的真实错误。

如果列名不同，可以手动指定：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --life "N" --response "S"
```

响应列可以使用 `塑性应变幅`、`应变最大值`、`应变幅`、`应力幅`、`strain`、`stress` 等名称；名称只影响输出文字，E739 拟合流程不变。

## 离线打包 exe

依赖安装完成后，在项目根目录执行：

```powershell
.\.venv\Scripts\pyinstaller.exe OriginNSFit.spec
```

打包结果在：

```text
dist\OriginNSFit.exe
```

## 更新离线资源

如果以后更新了依赖版本，在联网开发机上执行：

```powershell
.\.venv\Scripts\python.exe -m pip download --only-binary=:all: --dest .\offline\wheelhouse -r .\offline\requirements-offline.txt
```

然后把整个项目目录复制到离线电脑。
