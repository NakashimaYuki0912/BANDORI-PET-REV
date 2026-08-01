# BandoriPet 发布部署指南

本文档说明如何将 BandoriPet 打包为可分发的 Release 版本，并发布到 GitHub Releases。

---

## 1. 环境准备

### 1.1 基础环境

| 组件 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.10+ (推荐 3.11/3.12) | 主解释器 |
| Git | 最新 | 版本控制 |
| Visual Studio Build Tools | 2019+ | Windows 下编译 C 扩展依赖 |

### 1.2 Python 依赖安装

```bash
# 克隆仓库
git clone https://github.com/HELPMEEADICE/BANDORI-PET-REV.git
cd BANDORI-PET-REV

# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
```

### 1.3 第三方子模块

项目使用 `third_party/` 下的子模块，需初始化：

```bash
git submodule update --init --recursive
```

包含：
- `third_party/Live2D-v2-Lua/` — 自研 LuaJIT Live2D v2 渲染核心
- `third_party/PyQt-Fluent-Widgets/` — PySide6 分支的 Fluent Design 组件库

---

## 2. 模型资源准备（必需）

**模型文件不随代码仓库分发**，用户需自行下载并放入 `models/` 目录。

### 2.1 推荐格式：zstd 流式包（~900MB，启动快、无需解压）

```bash
# 下载地址
https://modelscope.cn/datasets/HELPMEEADICE/BanG-Dream-Live2D/resolve/master/models.zip
```

下载后解压 `models.zip`，将里面的 `*.zst` 文件放入项目根目录的 `models/` 文件夹：

```
BANDORI-PET-REV/
├── models/
│   ├── kasumi.zst
│   ├── yukina.zst
│   └── ... (共 45+ 个 .zst 文件)
├── main.py
└── ...
```

### 2.2 传统格式：7z 解压目录（~4GB）

若使用旧版模型包，解压后结构为：

```
models/
├── kasumi/
│   ├── live_default/
│   │   └── model.json
│   └── ...
└── ...
```

> ⚠️ 7z 格式需完整解压到磁盘，启动较慢。建议使用 `TOOL-convert_models_to_zst.py` 转换为 zst 格式。

---

## 3. 打包构建

### 3.1 版本号更新

发布前修改 `app_info.py` 中的版本号：

```python
APP_VERSION = "3.0.7"  # 语义化版本：MAJOR.MINOR.PATCH
```

### 3.2 执行打包

```bash
# 确保在虚拟环境中
.venv\Scripts\activate

# 清理旧构建
rmdir /s /q build dist 2>nul

# 执行 cx_Freeze 打包
python setup.py build
```

### 3.3 打包产物

构建完成后，`build/exe.win32-3.x/` 目录下包含：

```
build/exe.win32-3.x/
├── BandoriPet.exe          # 主程序入口
├── bandori_codex_runner.exe
├── bandori_ai_event.exe
├── python311.dll           # Python 运行时
├── *.pyd / *.dll           # 依赖库
├── models/                 # 空目录（运行时需用户放入模型）
├── characters/             # 角色 Prompt
├── audio_reference/        # TTS 参考音频
├── pixels/                 # 像素风素材
├── third_party/            # 第三方库
├── logo.ico
├── band.json
├── outfit.json
└── ...
```

### 3.4 生成便携版 ZIP

```bash
# 进入构建目录
cd build/exe.win32-3.x

# 打包（PowerShell）
Compress-Archive -Path * -DestinationPath "..\..\BandoriPet-3.0.7-WIN-AMD64.zip"
```

### 3.5 生成 MSI 安装包（可选）

```bash
# 需安装 WiX Toolset v3.11+
python setup.py bdist_msi
```

产物：`dist/BandoriPet-3.0.7-win32.msi`

---

## 4. GitHub Release 发布流程

### 4.1 创建 Release

1. 进入 GitHub 仓库 → **Releases** → **Create a new release**
2. Tag 版本：`v3.0.7`（与 `app_info.py` 一致）
3. Release 标题：`BandoriPet v3.0.7`
4. 勾选 **Set as the latest release**

### 4.2 上传资源文件

| 文件名 | 说明 |
|--------|------|
| `BandoriPet-3.0.7-WIN-AMD64.zip` | 便携版，解压即用（推荐） |
| `BandoriPet-3.0.7-win32.msi` | 安装版，支持开始菜单/卸载/开机自启 |

### 4.3 Release Notes 模板

```markdown
## BandoriPet v3.0.7

### 📦 下载
- **便携版（推荐）**：[BandoriPet-3.0.7-WIN-AMD64.zip](https://github.com/HELPMEEADICE/BANDORI-PET-REV/releases/download/v3.0.7/BandoriPet-3.0.7-WIN-AMD64.zip)
- **安装版**：[BandoriPet-3.0.7-win32.msi](https://github.com/HELPMEEADICE/BANDORI-PET-REV/releases/download/v3.0.7/BandoriPet-3.0.7-win32.msi)

### ⚠️ 必读：模型资源
程序**不包含模型文件**，首次运行需下载模型包：
- [zstd 格式 ~900MB（推荐，启动快）](https://modelscope.cn/datasets/HELPMEEADICE/BanG-Dream-Live2D/resolve/master/models.zip)
- [7z 格式 ~4GB（传统格式）](https://modelscope.cn/datasets/HELPMEEADICE/BanG-Dream-Live2D/resolve/master/models.7z)

下载后解压，将 `models/` 文件夹放到程序同级目录。

### 🆕 更新内容
- 修复了 XXX 问题
- 新增 XXX 功能
- 优化了 XXX 性能

### 🔧 完整更新日志
见 [CHANGELOG.md](CHANGELOG.md)
```

---

## 5. 用户端部署说明（写入 Release 或 Wiki）

### 5.1 便携版使用步骤

1. 下载 `BandoriPet-<version>-WIN-AMD64.zip`
2. 解压到任意目录（路径**不要包含中文/特殊字符**）
3. 下载模型包 `models.zip`，解压后将 `models/` 文件夹放到程序同级目录
4. 双击 `BandoriPet.exe` 运行
5. 首次运行会弹出设置向导，选择角色、配置 LLM API Key

### 5.2 安装版使用步骤

1. 下载并运行 `BandoriPet-<version>-win32.msi`
2. 按向导安装（默认 `C:\Program Files\BandoriPet\`）
3. 从开始菜单或桌面快捷方式启动
4. 首次运行自动打开设置向导
5. 模型文件需手动放入安装目录下的 `models/`，或在设置中指定自定义模型路径

### 5.3 开机自启

- 设置 → 通用 → 勾选「开机自动启动」
- 或安装版勾选安装向导中的「创建开机自启项」

---

## 6. 平台兼容性说明

| 平台 | 支持度 | 备注 |
|------|--------|------|
| Windows 10/11 x64 | ✅ 完整支持 | 主力平台，MSI/便携版均可用 |
| Windows ARM64 | ⚠️ 未测试 | 需重新打包 |
| macOS (Apple Silicon) | ⚠️ 部分兼容 | 需自行 `py2app` 打包，Live2D 渲染需 MoltenVK |
| Linux (X11/Wayland) | ⚠️ 部分兼容 | 需 `pyinstaller` + 系统依赖，Wayland 下需 XWayland |

> 非 Windows 平台建议开发者自行构建，不提供官方 Release。

---

## 7. 常见问题排查

### 7.1 启动报错：找不到模型

```
[ModelManager] No models found in models/
```
**解决**：确认 `models/` 目录存在且包含 `.zst` 文件或解压后的角色目录。

### 7.2 启动报错：`ImportError: DLL load failed`

**原因**：缺少 Visual C++ Redistributable 或 OpenGL 驱动。
**解决**：
- 安装 [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- 更新显卡驱动

### 7.3 TTS 语音不播放

**检查项**：
1. 设置 → 语音 → 启用 TTS
2. `tts_api_url` 指向本地 Qwen3TTS（默认 `http://127.0.0.1:9880/`）
3. 本地需运行 Qwen3TTS 后端（另行下载，非本项目打包内容）

### 7.4 多显示器 DPI 缩放异常

已在代码中强制 `PassThrough` 策略。如仍有问题，尝试：
- Windows 设置 → 显示 → 缩放 → 关闭“让 Windows 尝试修复应用，使其不模糊”
- 右键 exe → 属性 → 兼容性 → 更改高 DPI 设置 → 替换高 DPI 缩放行为 → 系统

### 7.5 杀毒软件误报

cx_Freeze 打包的 exe 可能被部分国产杀毒软件误报。
**建议**：Release 页面提示用户添加信任，或提交样本到杀毒厂商白名单。

---

## 8. 自动化构建（可选：GitHub Actions）

`.github/workflows/release.yml` 示例：

```yaml
name: Build Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      
      - name: Build with cx_Freeze
        run: python setup.py build
      
      - name: Package portable zip
        run: |
          cd build/exe.win32-3.*
          7z a ../../BandoriPet-${{ github.ref_name }}-WIN-AMD64.zip ./*
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: BandoriPet-WIN-AMD64
          path: BandoriPet-*-WIN-AMD64.zip
      
      - name: Create Release
        uses: softprops/action-gh-release@v1
        if: startsWith(github.ref, 'refs/tags/')
        with:
          files: BandoriPet-*-WIN-AMD64.zip
          generate_release_notes: true
```

---

## 9. 许可证合规

| 部分 | 许可证 | 分发限制 |
|------|--------|----------|
| 代码 | GPLv3 | 需开源同步修改 |
| Live2D 模型/贴图/动作 | **原版权方所有** | **禁止商用、禁止二次分发模型文件** |
| 第三方库 | 各自许可证 | 遵循各库要求 |

> ⚠️ **重要**：Release 打包时**不得包含任何模型文件**（`.zst`、`.7z`、解压后的 `models/`）。用户必须自行从官方渠道获取。

---

## 10. 版本发布清单

发布前逐项核对：

- [ ] `app_info.py` 版本号已更新
- [ ] `CHANGELOG.md` 已更新
- [ ] `git tag v3.0.7 && git push origin v3.0.7`
- [ ] GitHub Actions 构建通过（或本地构建验证）
- [ ] 便携版 ZIP 能在干净 Windows 环境运行
- [ ] MSI 安装包能正常安装/卸载/开机自启
- [ ] Release 页面上传了两个文件
- [ ] Release Notes 包含模型下载链接提示
- [ ] 已在 Discord/QQ 群/论坛发布更新通知

---

## 附录：目录结构速查

```
BANDORI-PET-REV/
├── main.py                    # 入口
├── setup.py                   # cx_Freeze 打包脚本
├── requirements.txt           # Python 依赖
├── app_info.py                # 版本号、应用名
├── config.json.template       # 配置模板
├── models/                    # 模型目录（用户自行放入）
├── characters/                # 角色 Prompt
├── audio_reference/           # TTS 参考音频
├── pixels/                    # 像素风素材
├── third_party/               # 子模块
├── docs/                      # 文档
├── tools/                     # 辅助脚本
└── tests/                     # 测试用例
```

---

> 文档维护：随版本迭代同步更新。建议将此文件放入仓库 `docs/DEPLOYMENT_GUIDE.md`，并在 Release 正文链接。