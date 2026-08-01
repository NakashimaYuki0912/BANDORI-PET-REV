# BandoriPet v3.1.0.1 使用说明

> **基于 Live2D Cubism SDK 的桌面宠物应用**，让 BanG Dream! 角色以 Live2D 形态显示在桌面上。支持 LLM 驱动的 AI 角色扮演对话、TTS 语音合成、MCP/Computer Use 工具、多角色同时显示、外部聊天软件接入等功能。

---

## 📦 下载与安装

### 便携版（推荐）
1. 下载 `BandoriPet-3.1.0.1-WIN-AMD64.zip`
2. 解压到任意目录（**路径中不要包含中文/特殊字符**）
3. 双击 `BandoriPet.exe` 运行

### 安装版
- 下载 `.msi` 安装包（如提供），按向导安装到 `C:\Program Files\BandoriPet`

### 依赖说明
- Windows 10/11 (64-bit)
- 已内置 Python 3.13 + 所有依赖，**无需额外安装**
- 如需 TTS：需单独下载 Qwen3TTS 后端（可选）

---

## 🚀 快速开始

1. **首次运行**会打开设置向导：
   - 选择要显示的角色（如 `kasumi` 户山香澄）
   - 选择服装（如 `casual` 常服）
   - 配置 LLM API（OpenAI 兼容格式：DeepSeek、OpenRouter、本地 vLLM 等）
   - 可选：启用 TTS、MCP、Computer Use

2. **桌面宠物**出现后：
   - **左键拖拽**：移动位置
   - **右键**：打开菜单（设置、对话、切换角色/服装、退出）
   - **点击模型**：触发对应部位动作（头部、身体等）

3. **AI 对话**：
   - 设置 → LLM → 填入 API Key / Base URL / Model ID
   - 右键宠物 → "打开对话窗口" 或使用紧凑悬浮窗
   - 支持流式输出、Markdown 渲染、代码高亮

---

## ⚙️ 核心功能详解

### 单角色显示（本分支限制）
> ⚠️ **注意**：本分支已移除多角色同屏/多实例支持，仅支持**单角色单实例**运行。
> - 每次仅能启动一个桌宠进程
> - 切换角色需在设置中重新选择并重启
> - 如需多角色同屏，请使用上游原版 `izasaraba/BANDORI-PET-REV`

### 服装切换（优化版）
- 设置 → 角色 → 服装列表
- **首次查看**某服装需加载模型（几秒）
- **再次切换**同一服装**瞬间完成**（内存缓存 `Live2DWidget`）
- 支持 zstd 流式模型（`models/*.zst`）与传统解压目录

### LLM 集成
| 支持项 | 说明 |
|--------|------|
| Chat Completions | OpenAI、DeepSeek、OpenRouter、硅基流动等 |
| Responses API | OpenAI 原生含 MCP 工具调用 |
| 系统提示词 | 角色人设 + 通用动作规则 + 语言规则 + 关系记忆 |
| 动作标签 | 回复末尾 `[tag]` 触发 Live2D 动画 |

### 语言强制规则（v3.1.0.1 新增）
系统提示词末尾自动注入：
- **中文模式**：严禁输出完整日文句子/段落，仅允许极少量口癖（每次 ≤1 个）嵌入中文
- **英文模式**：同理
- **日文模式**：正常日文回复
- 配置：设置 → 语言 / `config.json` 的 `"language": "zh_CN"`

### TTS 语音合成
- 支持：Edge-TTS、Qwen3TTS、CosyVoice 等
- 角色参考音频：`audio_reference/<character>/`
- 设置 → TTS → 选择引擎、语音、语速

### MCP / Computer Use
- **内置 MCP Server**：`bandori_mcp_server.py` 提供桌宠控制接口
- **文件系统 MCP**：`filesystem_mcp_server.py` 只读文件访问
- **Computer Use**：截屏、鼠标/键盘控制、剪贴板（⚠️ 慎重授权）
- 配置：设置 → MCP → 填入服务器地址或启用内置

### 外部聊天软件接入
- Webhook：`http://localhost:38473/webhook` (POST JSON)
- 支持 NapCat OneBot (QQ)、微信转发等
- 文档见 `docs/CHAT_INTEGRATION_GUIDE.md`

### AI 状态悬浮窗
- 紧凑窗口显示 AI 思考/工具调用/回复状态
- 接收 HTTP `POST /ai-event` (端口 38472)
- 支持 Codex CLI、`bandori-ai-event` CLI、opencode 插件推送

---

## 📁 目录结构

```
BandoriPet/
├── BandoriPet.exe           # 主启动器
├── pet_process.exe          # 桌宠渲染进程
├── settings_process.exe     # 设置面板进程
├── chat_process.exe         # 对话进程
├── bandori-ai-event.exe     # AI 事件 CLI
├── bandori-codex-runner.exe # Codex 包装器
├── config.json              # 用户配置（运行时生成）
├── outfit.json              # 角色/服装元数据
├── band.json                # 乐队/角色映射
├── logo.ico                 # 图标
├── models/                  # Live2D 模型（需用户下载）
│   ├── kasumi/
│   │   ├── casual/
│   │   │   └── model.json
│   │   └── ...
│   └── ...
├── characters/              # LLM System Prompt (40+ 角色)
│   ├── kasumi/
│   │   └── A_kasumi.md
│   └── ...
├── audio_reference/         # TTS 参考音频 (47 角色)
├── pixels/                  # 像素风宠物素材
├── third_party/
│   ├── Live2D-v2-Lua/       # LuaJIT 渲染核心
│   └── PyQt-Fluent-Widgets/ # Fluent UI (PySide6 分支)
├── lang/                    # 多语言 (zh_CN, en_US, ja_JP)
└── docs/                    # 文档
```

---

## 🔧 常用配置项 (`config.json`)

```json
{
  "character": "kasumi",
  "costume": "casual",
  "language": "zh_CN",
  "llm_api_url": "https://api.deepseek.com/v1/chat/completions",
  "llm_api_key": "sk-xxx",
  "llm_model_id": "deepseek-chat",
  "tts_enabled": true,
  "tts_engine": "edge",
  "tts_language": "Chinese",
  "mcp_enabled": false,
  "computer_use_enabled": false,
  "chat_integration_enabled": true,
  "auto_start": false,
  "fps": 60,
  "opacity": 1.0,
  "dark_theme": true
}
```

---

## ❓ 常见问题

| 问题 | 解决方法 |
|------|----------|
| 启动闪退/白屏 | 确保路径无中文；更新显卡驱动；以管理员运行一次 |
| 模型不显示/报错 | 检查 `models/<character>/<costume>/model.json` 存在；尝试切换渲染质量 |
| LLM 无响应 | 检查 API Key/URL/Model；查看日志 `logs/chat_*.log` |
| TTS 无声音 | 检查音频设备；Edge-TTS 需联网；Qwen3TTS 需单独部署 |
| 服装切换卡顿 | v3.1.0.1 已优化缓存，首次加载后即刻切换 |
| 回复全是日文 | 确认 `config.json` 语言为 `zh_CN`；重启生效 |

---

## 📝 更新日志 v3.1.0.1

### 新增
- **全量角色提示词**：40 位主角完整人设（身份、性格、口吻、关系、动作标签等）
- **语言强制规则**：系统提示词末尾注入，彻底解决中文模式下大段日文回复
- **服装预览缓存**：`CostumePreviewPanel` / `Live2DPreviewBubble` 缓存 `Live2DWidget`，二次切换零延迟

### 变更
- **移除多角色同屏支持**：本分支为单实例版本，仅支持单角色运行；需多角色请用上游原版
- `CHARACTER_PROMPTS` 结构化重写，便于维护
- 语言规则提取为字典映射，易于扩展

### 修复
- cx_Freeze 8.6.4 兼容：GUI base `Win32GUI` → `gui`
- 构建时 RecursionError：`sys.setrecursionlimit(3000)`
- 精简打包依赖，移除冲突模块

---

## 📄 许可证

- **代码**：GPLv3
- **角色模型资源**：版权归原版权方所有，**禁止商用**
- **音频参考**：仅供个人学习研究使用

---

## 🔗 相关链接

- **仓库**：https://github.com/izasaraba/BANDORI-PET-REV
- **问题反馈**：GitHub Issues
- **QQ 群**：https://qm.qq.com/q/VJMrn5EkWQ
- **文档目录**：`docs/`
  - `PROMPT.md` — 角色 Prompt 模板 + 动作标签速查
  - `OUTFIT.md` — 角色/服装一览 (305+ 套)
  - `CHAT_INTEGRATION_GUIDE.md` — 聊天软件接入
  - `CODEX_AI_OVERLAY_GUIDE.md` — AI 状态悬浮窗
  - `MCP_COMPUTER_USE_GUIDE.md` — MCP + Computer Use 配置