const DEFAULT_ENDPOINT = "http://127.0.0.1:38472/ai-events"
const DEFAULT_SOURCE = "opencode"
const DEFAULT_TTL_MS = 4500
const DEFAULT_TIMEOUT_MS = 900
const DEFAULT_MAX_TEXT = 240
const DEFAULT_MAX_OUTPUT_TEXT = 4000
const DEFAULT_OUTPUT_HOLD_MS = 30000
const DEFAULT_OUTPUT_FLUSH_MS = 160
const DEFAULT_DONE_HINT = "opencode 输出完成，输入 @clear 清除"

function readEnv() {
  const global = globalThis
  return {
    ...(global.process?.env ?? {}),
    ...(global.Bun?.env ?? {}),
  }
}

function envFlag(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase())
}

function envNumber(value, fallback) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
}

function compactText(value) {
  if (value == null) return ""
  if (typeof value === "string") return value.trim()
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  if (Array.isArray(value)) {
    return value.map(compactText).filter(Boolean).join(" ").trim()
  }
  if (typeof value === "object") {
    for (const key of [
      "text",
      "content",
      "delta",
      "summary",
      "message",
      "title",
      "command",
      "cmd",
      "filePath",
      "path",
      "name",
      "status",
    ]) {
      const text = compactText(value[key])
      if (text) return text
    }
  }
  return ""
}

function clipText(text, maxText) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim()
  if (!normalized || normalized.length <= maxText) return normalized
  return `${normalized.slice(0, Math.max(0, maxText - 1)).trimEnd()}...`
}

function clipRawText(text, maxText) {
  const normalized = String(text || "").replace(/\r\n?/g, "\n")
  if (!normalized || normalized.length <= maxText) return normalized
  return normalized.slice(-maxText)
}

function appendDoneHint(text, hint, maxText) {
  const body = String(text || "")
  const suffix = String(hint || "").trim()
  if (!suffix) return clipRawText(body, maxText)
  const displaySuffix = `\n\n${suffix}`
  const bodyLimit = Math.max(0, maxText - displaySuffix.length)
  const visibleBody = body.length > bodyLimit ? body.slice(-bodyLimit) : body
  return `${visibleBody}${displaySuffix}`
}

function pick(obj, paths) {
  for (const path of paths) {
    let current = obj
    for (const part of path.split(".")) {
      current = current?.[part]
    }
    if (current != null && current !== "") return current
  }
  return ""
}

function eventType(event) {
  const type = String(event?.type || "").toLowerCase()
  const name = String(event?.name || "").toLowerCase()
  return name && name !== "sync" ? name : type
}

function cleanEventName(type) {
  return String(type || "").replace(/\.\d+$/, "")
}

function describeTool(input, output, maxText) {
  const toolName = String(pick(input, ["tool", "name"]) || pick(output, ["tool", "name"]) || "tool")
  const args = output?.args ?? input?.args ?? input?.parameters ?? {}
  const details =
    pick(args, ["command", "cmd"]) ||
    pick(args, ["filePath", "path", "pattern", "query", "url"]) ||
    compactText(args)
  return clipText(details ? `${toolName}: ${details}` : toolName, maxText)
}

function describeEvent(event, maxText) {
  return clipText(
    compactText(
      pick(event, [
        "error.message",
        "properties.error.message",
        "properties.message",
        "properties.delta",
        "properties.text",
        "properties.part.text",
        "properties.part.delta",
        "properties.part.content",
        "properties.info.error.data.message",
        "properties.info.error.message",
        "data.message",
        "data.delta",
        "data.text",
        "data.part.text",
        "data.part.delta",
        "data.part.content",
        "data.error.message",
        "part.delta",
        "part.text",
        "part.content",
        "message.content",
        "message.text",
        "session.title",
        "session.id",
        "permission.title",
        "permission.message",
        "file.path",
        "command.command",
        "todo.items",
        "data",
        "text",
      ]) || event,
    ),
    maxText,
  )
}

function extractModelText(event, maxText) {
  const type = cleanEventName(eventType(event))
  const text =
    pick(event, [
      "properties.delta",
      "properties.text",
      "properties.part.text",
      "properties.part.delta",
      "data.delta",
      "data.text",
      "data.part.text",
      "data.part.delta",
      "part.delta",
      "part.text",
      "delta",
      "text",
    ]) || ""
  if (text) {
    return {
      text: clipRawText(text, maxText),
      mode: type.endsWith(".delta") || type === "message.part.delta" ? "append" : "replace",
    }
  }

  const part = event?.properties?.part ?? event?.data?.part ?? event?.part
  if (part?.type === "text" && part.text) {
    return { text: clipRawText(part.text, maxText), mode: "replace" }
  }

  const info = event?.properties?.info ?? event?.data?.info ?? event?.message
  const content = info?.content
  if (Array.isArray(content)) {
    const visible = content
      .filter((item) => item?.type === "text")
      .map((item) => String(item.text || ""))
      .filter(Boolean)
      .join("\n")
    if (visible) return { text: clipRawText(visible, maxText), mode: "replace" }
  }
  return { text: "", mode: "replace" }
}

function todoSummary(event) {
  const items = pick(event, ["properties.todo.items", "data.todo.items", "todo.items", "properties.items", "data.items", "items"])
  if (!Array.isArray(items)) return ""
  const total = items.length
  const done = items.filter((item) => {
    const status = String(item?.status || item?.state || "").toLowerCase()
    return ["done", "completed", "complete"].includes(status)
  }).length
  return total ? `TODO ${done}/${total}` : ""
}

export const BandoriAiOverlay = async (ctx = {}) => {
  const env = readEnv()
  if (envFlag(env.BANDORI_AI_DISABLED) || env.BANDORI_AI_OVERLAY === "0") {
    return {}
  }

  const endpoint = env.BANDORI_AI_ENDPOINT || env.BANDORI_AI_URL || DEFAULT_ENDPOINT
  const token = env.BANDORI_AI_TOKEN || ""
  const source = env.BANDORI_AI_SOURCE || DEFAULT_SOURCE
  const character = env.BANDORI_AI_CHARACTER || ""
  const ttlMs = envNumber(env.BANDORI_AI_TTL_MS, DEFAULT_TTL_MS)
  const requestTimeoutMs = envNumber(env.BANDORI_AI_TIMEOUT_MS, DEFAULT_TIMEOUT_MS)
  const maxText = envNumber(env.BANDORI_AI_MAX_TEXT, DEFAULT_MAX_TEXT)
  const maxOutputText = envNumber(env.BANDORI_AI_MAX_OUTPUT_TEXT, DEFAULT_MAX_OUTPUT_TEXT)
  const outputHoldMs = envNumber(env.BANDORI_AI_OUTPUT_HOLD_MS, DEFAULT_OUTPUT_HOLD_MS)
  const outputFlushMs = envNumber(env.BANDORI_AI_OUTPUT_FLUSH_MS, DEFAULT_OUTPUT_FLUSH_MS)
  const doneHint = env.BANDORI_AI_DONE_HINT ?? DEFAULT_DONE_HINT
  const debug = envFlag(env.BANDORI_AI_DEBUG)
  let lastFailure = ""
  let lastPayloadKey = ""
  let lastPayloadAt = 0
  let lastModelOutputAt = 0
  let modelOutputText = ""
  let modelOutputFlushAt = 0
  let modelOutputFinalized = false

  async function log(level, message, extra = {}) {
    if (!ctx.client?.app?.log) return
    try {
      await ctx.client.app.log({
        body: {
          service: "bandori-ai-overlay",
          level,
          message,
          extra,
        },
      })
    } catch {
      // Logging must never break opencode hooks.
    }
  }

  async function publish(payload, options = {}) {
    const now = Date.now()
    const rawTextMode = String(payload.mode || "").endsWith("_raw")
    const textLimit = options.maxText ?? maxText
    const event = {
      source,
      ...payload,
      state: payload.state || "stream",
      title: payload.title || "",
      text: rawTextMode
        ? clipRawText(payload.text || "", textLimit)
        : clipText(payload.text || "", textLimit),
    }
    if (character && !event.character) event.character = character
    if (ttlMs && event.state !== "clear" && event.state !== "stream" && event.ttl_ms == null) {
      event.ttl_ms = ttlMs
    }

    const key = JSON.stringify([event.state, event.title, event.text, event.mode, event.action])
    const dedupeMs = options.dedupeMs ?? 350
    if (dedupeMs && key === lastPayloadKey && now - lastPayloadAt < dedupeMs) return
    lastPayloadKey = key
    lastPayloadAt = now

    const headers = { "Content-Type": "application/json" }
    if (token) headers.Authorization = `Bearer ${token}`

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), requestTimeoutMs)
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify(event),
        signal: controller.signal,
      })
      if (!response.ok) {
        const failure = `HTTP ${response.status}`
        if (failure !== lastFailure || debug) {
          lastFailure = failure
          await log("warn", "BandoriPet AI event was rejected", { endpoint, status: response.status })
        }
      }
    } catch (error) {
      const failure = error?.name || error?.message || String(error)
      if (debug && failure !== lastFailure) {
        lastFailure = failure
        await log("debug", "BandoriPet AI event was not delivered", { endpoint, error: failure })
      }
    } finally {
      clearTimeout(timeout)
    }
  }

  function modelOutputIsProtected() {
    return outputHoldMs > 0 && Date.now() - lastModelOutputAt < outputHoldMs
  }

  async function publishModelOutput(text, { force = false } = {}) {
    const now = Date.now()
    const previousText = modelOutputText
    modelOutputText = clipRawText(text, maxOutputText)
    lastModelOutputAt = now
    if (!force) modelOutputFinalized = false
    if (!force && !previousText && outputFlushMs > 0 && modelOutputText.length < 12) {
      modelOutputFlushAt = now
      return
    }
    if (!force && outputFlushMs > 0 && now - modelOutputFlushAt < outputFlushMs) return
    modelOutputFlushAt = now
    await publish(
      {
        state: "stream",
        title: "",
        text: force ? appendDoneHint(modelOutputText, doneHint, maxOutputText) : modelOutputText,
        mode: "replace_raw",
        final: force,
      },
      { dedupeMs: force ? 0 : 80, maxText: maxOutputText },
    )
    if (force) modelOutputFinalized = true
  }

  async function finalizeModelOutput() {
    if (!modelOutputText || modelOutputFinalized) return
    await publishModelOutput(modelOutputText, { force: true })
  }

  async function mirrorEvent(event) {
    const type = cleanEventName(eventType(event))
    if (!type) return

    if (type === "server.connected") {
      await publish({
        state: "thinking",
        title: "opencode 已连接",
        text: "BandoriPet 状态悬浮窗插件已加载",
        action: "thinking",
        ttl_ms: 2500,
      })
      return
    }

    if (type === "session.created") {
      modelOutputText = ""
      modelOutputFlushAt = 0
      modelOutputFinalized = false
      await publish({
        state: "thinking",
        title: "opencode 会话开始",
        text: describeEvent(event, maxText),
        action: "thinking",
      })
      return
    }

    if (type === "session.status") {
      const status = String(pick(event, ["properties.status", "data.status", "status", "session.status"]) || "").toLowerCase()
      if (status.includes("idle") && modelOutputIsProtected()) {
        await finalizeModelOutput()
        return
      }
      if (status.includes("idle")) {
        await publish({ state: "done", title: "opencode 已完成", text: "当前会话空闲", action: "smile" })
      } else if (status) {
        await publish({
          state: "thinking",
          title: "opencode 正在工作",
          text: status,
          action: "thinking",
        })
      }
      return
    }

    if (type === "session.idle") {
      if (modelOutputIsProtected()) {
        await finalizeModelOutput()
        return
      }
      await publish({ state: "done", title: "opencode 已完成", text: "任务处理完成", action: "smile" })
      return
    }

    if (type === "session.error") {
      await publish({
        state: "error",
        title: "opencode 出错",
        text: describeEvent(event, maxText),
        action: "surprised",
      })
      return
    }

    if (type === "session.deleted") {
      await publish({ state: "clear", title: "", text: "" })
      return
    }

    if (type === "permission.asked") {
      await publish({
        state: "tool",
        title: "opencode 等待确认",
        text: describeEvent(event, maxText),
        action: "surprised",
      })
      return
    }

    if (type === "permission.replied") {
      await publish({
        state: "thinking",
        title: "opencode 继续执行",
        text: describeEvent(event, maxText),
        action: "thinking",
        ttl_ms: 2500,
      })
      return
    }

    if (type === "file.edited") {
      if (modelOutputIsProtected()) return
      await publish({
        state: "tool",
        title: "opencode 修改文件",
        text: describeEvent(event, maxText),
        action: "thinking",
      })
      return
    }

    if (type === "command.executed") {
      if (modelOutputIsProtected()) return
      await publish({
        state: "tool",
        title: "opencode 执行命令",
        text: describeEvent(event, maxText),
        action: "thinking",
      })
      return
    }

    if (type === "todo.updated") {
      if (modelOutputIsProtected()) return
      await publish({
        state: "thinking",
        title: "opencode 更新 TODO",
        text: todoSummary(event) || describeEvent(event, maxText),
        action: "thinking",
        ttl_ms: 3000,
      })
      return
    }

    if (type === "session.diff") {
      if (modelOutputIsProtected()) {
        await finalizeModelOutput()
        return
      }
      await publish({
        state: "tool",
        title: "opencode 生成变更",
        text: describeEvent(event, maxText),
        action: "thinking",
      })
      return
    }

    if (
      type === "message.part.delta" ||
      type === "message.part.updated" ||
      type === "message.updated" ||
      type === "session.next.text.started" ||
      type === "session.next.text.delta" ||
      type === "session.next.text.ended"
    ) {
      if (type === "session.next.text.started") {
        modelOutputText = ""
        modelOutputFlushAt = 0
        modelOutputFinalized = false
        return
      }

      const output = extractModelText(event, maxOutputText)
      const isDelta = output.mode === "append"
      const nextText = isDelta ? modelOutputText + output.text : output.text

      if (type === "session.next.text.ended") {
        const finalText = nextText || modelOutputText
        if (finalText) await publishModelOutput(finalText, { force: true })
        return
      }

      if (!nextText) return
      await publishModelOutput(nextText)
    }
  }

  return {
    event: async ({ event }) => {
      await mirrorEvent(event)
    },
    "tool.execute.before": async (input, output) => {
      await publish({
        state: "tool",
        title: "opencode 正在运行工具",
        text: describeTool(input, output, maxText),
        action: "thinking",
      })
    },
    "tool.execute.after": async (input, output) => {
      const errorText = compactText(output?.error || output?.result?.error)
      if (errorText) {
        await publish({
          state: "error",
          title: "opencode 工具失败",
          text: clipText(errorText, maxText),
          action: "surprised",
        })
        return
      }
      if (modelOutputIsProtected()) return
      await publish({
        state: "thinking",
        title: "opencode 继续思考",
        text: describeTool(input, output, maxText),
        action: "thinking",
        ttl_ms: 2500,
      })
    },
  }
}
