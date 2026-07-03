# 🍴 与原项目的区别

本仓库是 [HELPMEEADICE/BANDORI-PET-REV](https://github.com/HELPMEEADICE/BANDORI-PET-REV) 的 fork，在原项目基础上进行了以下改进。

---

## 🚀 性能优化

| 优化项 | 说明 |
|--------|------|
| **渲染负载减半** | 默认帧率 120→60 FPS，桌面宠物场景无感知差异 |
| **启动速度大幅提升** | 移除 SSH 隧道端口等待（~6s）、zst 模型归档 mtime 缓存（~2s）、冷启动跳过冗余配置读写 |
| **IPC 消除阻塞** | action_bus / ai_event_bus 改用持久 QLocalSocket 连接，消除每次 IPC 调用 200-400ms 阻塞 |
| **聊天消息内存缓存** | 消息历史、关系状态、角色记忆改为内存缓存，每次发送消息不再执行 5+ 次 SQLite 查询 |
| **DB 异步写入** | 聊天消息、助手回复保存改为线程池异步写入，不再阻塞 GUI 线程 |
| **群聊列表增量更新** | 从全量销毁重建改为按 group_key diff，仅修改变化的行 |
| **TTS 锁拆分** | 权重切换锁与 HTTP 请求锁分离，多请求不再互相阻塞 |
| **Lua 层优化** | GC step 每 4 帧执行一次（原每帧），Draw() 预分配 opts table 避免每帧新建 |

---

## 🎨 交互改进

### 右键菜单重设计

圆圈弧形 → 卡片式竖排列表，手绘线描 SVG 图标（气泡/衣架/太阳/挂锁），带标题和副标题。

![右键菜单](https://github.com/user-attachments/assets/210dacd2-31cf-4c0a-806d-50a44e55ca49)

### 设置面板导航重排

侧栏按钮用 Tab 分组（角色 / 对话 / 高级），不再拥挤。

![设置面板](https://github.com/user-attachments/assets/f8adacf5-d4b5-44ca-a113-edd9f52a453a)

### 其他改进

| 改进项 | 说明 |
|--------|------|
| **锁定功能入口** | 桌宠位置锁定/解锁从中心隐藏按钮移到右键菜单独立入口 |
| **同角色无缝换装** | 相同角色切换服装不再关闭窗口重启进程，Live2D 模型原地热替换 |
| **换装面板直达** | 右键→换装直接打开服装选择页，首次打开还是会闪一下，但是后续不再闪现角色列表页，还在排查 |
| **TTS 功能优化** | 替换为 GPT-SoVITS 方式，音源来自 [Bestdori](https://bestdori.com/) |
| **Agent Skills 集成** | 配置 mattpocock/skills 工程技能（triage、to-issues、grill-with-docs 等） |
