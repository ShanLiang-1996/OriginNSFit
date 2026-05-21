# OriginNSFit

批量读取实验数据，计算基础拟合指标，并通过 Origin 自动生成图形的 Python 项目骨架。

## 环境准备

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input examples --output output --pattern "*.csv" --dry-run
```

如果本机已安装 Origin，去掉 `--dry-run` 后会尝试通过官方 `originpro` API 创建 Origin 工作表并导出图像。

## 打包 exe

```powershell
.\.venv\Scripts\pyinstaller.exe OriginNSFit.spec
```

打包结果会输出到 `dist\OriginNSFit.exe`。`data/` 和 `output/` 默认不会进入 Git，用于放本地输入和生成结果。

## 目录

```text
src/originnsfit/       Python 包源码
scripts/               辅助启动脚本和打包入口
examples/              可提交的示例数据
data/                  本地批量输入数据，默认忽略
output/                拟合结果和导出图像，默认忽略
```

说明：OriginLab 当前推荐的自动化包是 `originpro`；项目也按你的要求安装 `originpy`，方便你后续兼容已有脚本。
