# OriginNSFit 离线部署包

这个目录用于在不能联网的 Windows 电脑上部署 OriginNSFit。

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

验证：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input examples --output output --pattern "*.csv" --dry-run
```

## 真实连接 Origin

确认 dry-run 成功后，把测试命令中的 `--dry-run` 去掉：

```powershell
.\.venv\Scripts\python.exe -m originnsfit --input data --output output --pattern "*.csv"
```

如果 Origin 自动化失败，优先检查：

- Origin / OriginPro 是否已安装并能正常启动。
- Python 和 Origin 的位数是否一致，建议都使用 64 位。
- 是否安装了 `originpro` 和 `OriginExt`，可用下面命令检查：

```powershell
.\.venv\Scripts\python.exe -m pip show originpro OriginExt originpy
```

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
