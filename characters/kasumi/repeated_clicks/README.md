# 多次点击语音文件目录 (Repeated Click Audio)

你可以将准备好的角色被戳/多次点击的语音音频文件（支持 `.wav`, `.mp3`, `.ogg`, `.flac` 格式）放入此文件夹中。

### 支持的使用方式：
1. **自动读取**：直接把音频文件（如 `poke_01.mp3`, `poke_02.wav`）放到该角色目录（`characters/<角色名>/repeated_clicks/`），多次点击桌宠时会自动随机播放其中的语音。
2. **在 `greetings.json` 中配置**：在角色的 `greetings.json` 的 `repeated_click` 项中指定文件名，例如：
   ```json
   "repeated_click": [
     {
       "text": "哇啊！不要一直戳我啦，好痒好痒~！[smile01]",
       "tts_text": "わあっ！何回もつつかないでよ、くすぐったいよ〜！",
       "audio": "poke_01.wav",
       "motion": "smile01",
       "expression": "smile"
     }
   ]
   ```
3. **TTS 自动合成与预热缓存**：如果没有本地音频文件，系统会通过 TTS 发音并在启动时自动预热缓存，实现秒播。
