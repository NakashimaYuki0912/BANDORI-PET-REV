# TODO.md — 待办事项与后续规划

> [!NOTE]
> 本文档由 **Gemini** 持续整理与归档。
> - 标有 `<!-- [Gemini 修改] -->` 或 `[Gemini 备注]` 的条目由 Gemini 实施与规划；
> - 标有 `<!-- [GPT 修改] -->` 或 `[GPT 备注]` 的条目由 GPT 实施与完善。

本文档记录 **BandoriPet** 尚未修改、待实现或规划中的优化项，供后续开发与迭代跟踪。

---

## 一、 音频资源与交互全语音化 (Audio & Full Voicing)

- [x] **GPT-SoVITS 本地运行时部署与开箱即用启动 <!-- [Gemini & GPT 修改] -->**
  - **现状 [Gemini 备注]**:
    - [x] 已完成全部 40 位角色的模型权重提纯提取：`D:\BANDORI-GPT-SoVITS\weights\ckpt_files` (40个) 与 `pth_files` (40个)，严格按 `e15 > e10 > e5` 规则选取最优轮次。
    - [x] 已将多余备份模型 (74个 ckpt, 82个 pth) 移入 `weights\warehouse\` 仓库，方便随时切换。
    - [x] 已完成 `tts_manager.py` 与 `config.json` 的本地智能路径解析，自动关联项目内置声优参考音频与台词。
    - [x] 已新增状态诊断自检工具 `TOOL-check-tts-status.py`。
    - [x] 已新增一键半精度启动脚本 `TOOL-start-gpt-sovits.bat`。
  - **现状 [GPT 备注]**:
    - [x] 在 `main.py` 中实现了 `start_local_gpt_sovits(runtime)` 本机运行时自动进程托管，通过 `config.json` 中的 `tts_gpt_sovits_runtime` 参数可自动由桌宠拉起整合包 API 服务，免除手动开脚本。
    - [x] 官方 v2 整合包已部署至 `D:/BANDORI-GPT-SoVITS/GPT-SoVITS-v2-240821`。普通聊天和微故事都使用本机 `127.0.0.1:9880`。微故事通过 `ambient_tts_provider: off` 沿用本机语音。

- [x] **连贯微故事模式 Realtime 语音合成支持 <!-- [GPT 修改] -->**
  - **现状 [GPT 备注]**:
    - [x] `realtime_story_tts.py` 保留 OpenAI Realtime 语音支持作为可选后端。当前实际使用本机 GPT-SoVITS v2。
    - [x] 在 `ambient_chat_manager.py` 中接入了多段式故事解析器 `parse_ambient_story_segments`，实现 2~4 段连续日常故事分步投递。

- [x] **移除无配音双击气泡并转为安全动作触发 <!-- [Gemini 修改] -->**
  - **现状 [Gemini 备注]**:
    - [x] 原双击文本气泡（`daily_chat`）因无配音且缺乏沉浸感已被正式移除。
    - [x] 在 `pet_window.py` 中将 `_on_double_click` 统一重定向为安全动作触发，彻底消除了“哑巴气泡”。

- [x] **连续多次点击（Poke 戳戳）全角色语音互动机制 <!-- [Gemini 修改] -->**
  - **现状 [Gemini 备注]**:
    - [x] 在 `pet_window.py` 中实现了连击滑动窗口检测（默认 1.8s 内 5 次，3.5s 冷却保护）。
    - [x] 在 `repeated_click.py` 中为全部 40 位角色构建了多条专属抱怨台词（中日双语对照、预置 Live2D 动作与表情）。
    - [x] 在 `tts_manager.py` 的启动预热逻辑中纳入了戳戳语音，支持启动即自动预热缓存，达到零延迟发声。
    - [x] 支持本地音频优先检测与口型联动（`characters/<key>/repeated_clicks/*.{wav,mp3}`）。
    - [x] 新增并通过专属单元测试 `tests/test_repeated_click.py`（16 项用例全部通过）。

- [x] **后台微故事请求线程安全性重构与崩溃修复 <!-- [Gemini 修改] -->**
  - **现状 [Gemini 备注]**:
    - [x] 查明了桌宠后台子进程每 15 秒因 Windows 访问越界 `0xC0000005` / `0xe24c4a02` 崩溃重启的问题：工作线程内直接创建了非线程安全的 `QNetworkAccessManager` 与事件循环。
    - [x] 将 `realtime_story_tts.py` 中的 `post_openai_story_json` 重构为纯 Python `urllib.request` 线程安全实现，完美适配系统代理与超时管控。
    - [x] 修正了 `tts_manager.py` 中 `_remote_tts_root` 的默认值回退逻辑与 `tests/test_ambient_story_mode.py` 的环境模拟，全套 71 项自动化测试 100% 恢复绿灯通过。

- [x] **40 位角色戳戳和登场问候离线音频 <!-- [Gemini & GPT 修改] -->**
  - 覆盖 122 条戳戳与 160 条登场问候。沿用已有合成缓存，并用各角色本地 GPT-SoVITS 权重补齐其余日语 WAV。
  - 按台词匹配 `characters/<key>/repeated_clicks/` 和 `characters/<key>/startup_greetings/` 内的离线音频。新增或修改台词后仍可通过 TTS 生成。
  - **离线音频音画对齐与编码报错修复 [Gemini 备注]**:
    - [x] 查明戳戳反应（Repeated Click）气泡台词与日文语音明显对不上的根因：早期批量生成的离线音频部分混入了声优参考音频（如 Lisa 的戳戳音频开头串入了 7 秒的参考台词 `アタシもピンうさのファン第一号として応援してるよ...`），已通过 Whisper ASR 转写定位并用本地 GPT-SoVITS 完成无泄漏的纯净重合成替换。
    - [x] 修复日文波浪号（`〜`、`～`）在 Windows 平台导致 GPT-SoVITS 控制台 GBK 编码报错（`'gbk' codec can't encode character '\u301c'`）的问题：在 `tts_manager.py` 的 `_gpt_sovits_payload` 与 `strip_tts_action_tags` 中统一做字符安全规整（规范化为长音符 `ー`），彻底消除动态合成 HTTP 400 失败。
  - **CHU2 参考音频升级与 Prompt 文本对齐 [Gemini 备注]**:
    - [x] 用户将 `audio_reference/chu2.mp3` 替换为更有起伏活力的 `chu2.wav`（时长 6.72s，采样率 24kHz 单声道）。
    - [x] 经 Whisper 转写该音频实际台词为 `パレオ、今の音最高だったわ！そのままの勢いで一気に決めろよ！`，已同步修正 `audio_reference/dialog.json`，消除了因 prompt_text 与音频不匹配导致的幻觉与乱音。
    - [x] 同步清理了 `tts_cache/gpt_sovits/chu2/` 旧缓存并用新音频更新了 `characters/chu2/repeated_clicks/` 戳戳音频。

---

## 二、 设置面板可视化配置 (Settings Window UI)

- [ ] **TTS 本地/云端/远程服务一键切换卡片 <!-- [Gemini 修改] -->**
  - 在设置面板中增加本地 GPT-SoVITS 状态指示灯（连通/离线），提供一键测试发声按钮。

---

## 三、 多语言与国际化 (i18n)

- [x] **故事状态多语言国际化词条补充 <!-- [GPT 修改] -->**
  - **现状 [GPT 备注]**: 已在 `lang/en_US.json`、`lang/ja.json`、`lang/zh_CN.json`、`lang/zh_TW.json` 中补齐 `PetWindow.story_not_ready`、`story_writing`、`story_audio_progress`、`story_text_failed`、`story_audio_failed`。
- [ ] **托盘菜单与环形菜单词条抽取 <!-- [Gemini 修改] -->**
  - **现状 [Gemini 备注]**: `main.py` 系统托盘已支持 `MainTray.trigger_story`，桌宠右键侧边菜单已用专注与休闲模式切换替换“讲故事”，新增模式文案已抽取。
  - **待办**: 将相关文本更深度抽取到 `i18n_manager.py`，保持全平台多语言统一。

---

## 四、 微故事模式与情境感知体验增强 (Ambient Story Refinements)

- [x] **微故事语音连续播放与动作匹配**
  - 整则语音提前生成。开讲前按当前角色模型匹配每段动作，上一段语音播完即切换下一段气泡、语音和动作。
- [ ] **讲故事过程中的打断与防冲突保护**
  - 点击或拖拽桌宠时已可清空待播段落。聊天框发消息时的联动及自然收尾体验待完善。
  - **待办**: 若用户在角色分段讲故事期间主动在对话框发送文本，或大幅拖拽角色、频繁连击戳戳时，增加自然的打断处理（如角色说“哎呀，你先说～”或者暂缓后续段落投递）。
- [x] **情境微故事提示词**
  - 将正在播放的音乐、天气和时段作为可选回忆线索。故事围绕角色、乐团及熟人展开，保留分段动作和原有语音流程。
