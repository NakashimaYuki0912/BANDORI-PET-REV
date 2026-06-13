import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape

from computer_tools import computer_tools, is_computer_tool_name, run_computer_tool
from mcp_bridge import call_mcp_tool, is_mcp_tool_name, mcp_native_tools, mcp_proxy_tools


WEB_SEARCH_TOOL_NAME = "web_search"
WEATHER_TOOL_NAME = "get_weather"

WEB_SEARCH_ENGINE_LABELS = {
    "bing": "Bing",
    "bing_cn": "Bing CN",
    "google": "Google",
    "duckduckgo": "DuckDuckGo",
    "baidu": "Baidu",
}


CHAT_COMPLETIONS_WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": WEB_SEARCH_TOOL_NAME,
        "description": (
            "Search the public web for current or external information. "
            "Use this for news, latest facts, prices, schedules, software/API "
            "details, or anything that may have changed recently."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The web search query, including enough keywords to be specific.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "How many search results to return, from 1 to 8.",
                },
            },
            "required": ["query"],
        },
    },
}


CHAT_COMPLETIONS_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": WEATHER_TOOL_NAME,
        "description": (
            "查询指定城市的实时天气与近两日预报。"
            "当用户询问天气、温度、降雨、是否适合出行等问题时调用；"
            "不填写 location 则查询用户默认城市。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": (
                        "城市 LocationID（如 101010100）或 经度,纬度（如 116.40,39.90）。"
                        "省略则使用用户配置的默认城市。"
                    ),
                },
            },
            "required": [],
        },
    },
}


def weather_tool_system_hint(default_city_name: str = "默认城市") -> str:
    return (
        "【天气查询工具】\n"
        f"系统提示词中已包含{default_city_name}的实时天气数据，回答{default_city_name}天气时直接使用，无需调用工具。\n"
        "仅当用户明确询问其他城市的天气时，才调用 get_weather 并传入对应的 LocationID。\n"
        "常见城市：北京 101010100、上海 101020100、广州 101280101、深圳 101280601。\n"
        "无论如何，回答天气问题时必须明确说出真实数据（天气状况和温度），不得用诗意描述代替。"
    )


def with_weather_tool_system_hint(messages: list[dict], default_city_name: str = "默认城市") -> list[dict]:
    copied = [dict(item) for item in messages]
    hint = {"role": "system", "content": weather_tool_system_hint(default_city_name)}
    if copied and copied[0].get("role") == "system":
        copied.insert(1, hint)
    else:
        copied.insert(0, hint)
    return copied


def _run_weather_tool(arguments: dict, tool_config: dict) -> str:
    import weather_manager
    location = (arguments.get("location") or "").strip() or tool_config.get("weather_city", "")
    private_key = tool_config.get("weather_private_key", "")
    api_host = tool_config.get("weather_api_host", "")
    key_id = tool_config.get("weather_key_id", "")
    project_id = tool_config.get("weather_project_id", "")
    if not private_key or not api_host or not key_id or not project_id:
        return "天气功能未配置完整，无法查询。"
    if not location:
        return "请指定城市 LocationID（如 101010100）或 经度,纬度（如 116.40,39.90）。"
    text = weather_manager.get_weather_prompt(private_key, api_host, location, key_id, project_id)
    return text if text else "天气查询失败，请检查 LocationID 是否正确。"


def web_search_system_hint(include_sources: bool = True) -> str:
    source_rule = (
        "工具返回搜索结果后，请基于结果作答，并在回复末尾输出严格 JSON 来源块，"
        "格式为 {\"web_search_sources\":[{\"title\":\"网页标题\",\"url\":\"https://...\"}]}；"
        "不要用 Markdown 列表展示来源。"
        if include_sources
        else "工具返回搜索结果后，请自然消化资料并保持角色口吻；除非用户明确要求来源，不要列出 URL 或引用列表。"
    )
    return (
        "【联网搜索工具】\n"
        "如果用户询问最新、实时、新闻、价格、日程、版本、API 文档、外部事实，"
        "或任何可能随时间变化的信息，你可以调用 web_search 工具。"
        "普通闲聊、角色扮演、情感陪伴、改写润色、总结已有上下文时，不要为了保险起见就去搜索。"
        "只有当搜索结果会明显提升正确性时才调用。"
        "调用 web_search 时，query 必须直接包含用户真正想查询的主体、时间或关键词，不要使用“你/我/它/这个”等代词，也不要把整段提示词原样塞进去。"
        f"{source_rule}"
        "如果没有收到真实工具结果，不要声称自己已经联网搜索。"
    )


def chat_completion_tools(web_search_enabled: bool, tool_config: dict | None = None) -> list[dict]:
    tools = [CHAT_COMPLETIONS_WEB_SEARCH_TOOL] if web_search_enabled else []
    config = tool_config or {}
    if config.get("weather_enabled"):
        tools.append(CHAT_COMPLETIONS_WEATHER_TOOL)
    tools.extend(mcp_proxy_tools(config))
    tools.extend(computer_tools(config))
    return tools


def responses_native_tools(tool_config: dict | None = None) -> list[dict]:
    return mcp_native_tools(tool_config or {})


def local_tool_system_hint(tool_config: dict | None = None) -> str:
    config = tool_config or {}
    hints = []
    if config.get("llm_hide_tool_call_details", True):
        hints.append(
            "最终回复请保持角色口吻，不要主动提到 MCP、tool_calls、function calling、Computer Use、工具调用、JSON schema 等实现细节；"
            "如果工具失败，也用自然语言轻描淡写地说明做不到或信息不足。"
        )
    if config.get("llm_mcp_enabled", False):
        hints.append(
            "可用外部能力时，优先根据用户意图谨慎调用；不要编造工具执行结果。"
        )
    if config.get("computer_use_enabled", False):
        if config.get("computer_use_auto_detect", True):
            hints.append(
                "当用户用自然语言表达与当前屏幕、窗口、光标、按钮、输入框、复制粘贴、打开/关闭/切换窗口、"
                "移动到某处、点一下、看一下这里/那边/这个界面等相关意图时，可以自行判断是否需要使用 Computer Use；"
                "不要求用户说出“工具”“操作鼠标”“查看屏幕”等精确词。"
            )
        else:
            hints.append(
                "只有当用户明确要求查看屏幕或操作电脑时才使用 Computer Use。"
            )
        hints.append(
            "使用 Computer Use 前优先截图确认界面；如果坐标不确定，先截图再行动。"
            "鼠标移动/点击/滚动请使用最近一次截图图片上的像素坐标，程序会自动映射到真实桌面坐标。"
            "不要执行购买、支付、删除、发送消息、发布内容、登录、修改安全设置等高风险操作。"
        )
    if not hints:
        return ""
    return "【工具使用边界】\n" + "\n".join(hints)


def with_local_tool_system_hint(messages: list[dict], tool_config: dict | None = None) -> list[dict]:
    hint_text = local_tool_system_hint(tool_config)
    if not hint_text:
        return [dict(item) for item in messages]
    copied = [dict(item) for item in messages]
    hint = {"role": "system", "content": hint_text}
    if copied and copied[0].get("role") == "system":
        copied.insert(1, hint)
    else:
        copied.insert(0, hint)
    return copied


def with_web_search_system_hint(messages: list[dict], include_sources: bool = True) -> list[dict]:
    copied = [dict(item) for item in messages]
    hint = {"role": "system", "content": web_search_system_hint(include_sources)}
    if copied and copied[0].get("role") == "system":
        copied.insert(1, hint)
    else:
        copied.insert(0, hint)
    return copied


def run_local_tool_call(name: str, arguments, tool_config: dict | None = None) -> dict:
    config = tool_config or {}
    if name == WEATHER_TOOL_NAME:
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
        return {"content": _run_weather_tool(arguments if isinstance(arguments, dict) else {}, config), "extra_messages": []}
    if name != WEB_SEARCH_TOOL_NAME:
        if is_mcp_tool_name(name):
            return {"content": call_mcp_tool(name, arguments), "extra_messages": []}
        if is_computer_tool_name(name):
            return run_computer_tool(name, arguments, config)
        return {"content": f"Unsupported tool: {name}", "extra_messages": []}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            arguments = {"query": arguments}
    if not isinstance(arguments, dict):
        arguments = {}
    query = _normalize_web_search_query(
        arguments.get("query", ""),
        (tool_config or {}).get("_latest_user_text", ""),
    )
    try:
        max_results = int(arguments.get("max_results", 5) or 5)
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(8, max_results))
    engine = _normalize_search_engine((tool_config or {}).get("llm_web_search_engine", "bing_cn"))
    return {"content": web_search(query, max_results=max_results, engine=engine), "extra_messages": []}


def run_local_tool(name: str, arguments, tool_config: dict | None = None) -> str:
    return str(run_local_tool_call(name, arguments, tool_config).get("content", ""))


def web_search(query: str, max_results: int = 5, engine: str = "bing_cn") -> str:
    query = str(query or "").strip()
    if not query:
        return "搜索失败：query 不能为空。"

    errors = []
    searcher = _searcher_for_engine(engine)
    try:
        results = searcher(query, max_results=max_results)
    except Exception as exc:
        errors.append(str(exc))
        results = []
    if results:
        return _format_search_results(query, results[:max_results], engine)
    for fallback in (_search_duckduckgo_html, _search_duckduckgo_instant_answer):
        if fallback is searcher:
            continue
        try:
            results = fallback(query, max_results=max_results)
        except Exception as exc:
            errors.append(str(exc))
            results = []
        if results:
            return _format_search_results(query, results[:max_results], "duckduckgo")
    if errors:
        return "搜索失败：" + "；".join(errors[:2])
    return f"没有找到与 “{query}” 相关的搜索结果。"


def _normalize_search_engine(engine: str) -> str:
    engine = str(engine or "").strip().lower()
    return engine if engine in WEB_SEARCH_ENGINE_LABELS else "bing_cn"


def _searcher_for_engine(engine: str):
    return {
        "bing": _search_bing_html,
        "bing_cn": _search_bing_cn_html,
        "google": _search_google_html,
        "duckduckgo": _search_duckduckgo_html,
        "baidu": _search_baidu_html,
    }.get(_normalize_search_engine(engine), _search_bing_cn_html)


def _content_to_text(content) -> str:
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in ("text", "input_text"):
                parts.append(str(item.get("text", "") or ""))
        return "\n".join(parts)
    return str(content or "")


_BAD_SEARCH_QUERIES = {
    "你", "我", "他", "她", "它", "这", "那", "这个", "那个", "这里", "那里",
    "啥", "什么", "吗", "么", "呢", "知道", "搜索", "查", "搜",
}


def _normalize_web_search_query(query, fallback_text: str = "") -> str:
    raw = _strip_prompt_suffix(str(query or ""))
    fallback = _extract_search_query(fallback_text)
    extracted = _extract_search_query(raw)
    candidate = extracted or raw.strip()
    if _is_bad_search_query(candidate) and fallback:
        candidate = fallback
    return _clean_search_query(candidate)


def _strip_prompt_suffix(text: str) -> str:
    text = str(text or "").strip()
    marker = "【后置提示词】"
    if marker in text:
        text = text.split(marker, 1)[0].strip()
    return text


def _extract_search_query(text: str) -> str:
    text = _strip_prompt_suffix(text)
    if not text:
        return ""
    quoted = re.search(r"[\"'“”‘’]([^\"'“”‘’]{2,80})[\"'“”‘’]", text)
    if quoted:
        return _clean_search_query(quoted.group(1))

    patterns = (
        r"(?:什么是|啥是|何为)\s*([^？?。！!，,\n]{2,80})",
        r"(?:知道|了解|听说过)\s*(?:什么是|啥是)?\s*([^？?。！!，,\n]{2,80})",
        r"(?:查一下|查找|搜索|搜一下|帮我查|帮我搜|找一下|查|搜)\s*([^？?。！!，,\n]{2,80})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_search_query(match.group(1))

    latin_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_.+\-]{1,80}", text)
    if latin_tokens:
        return max(latin_tokens, key=len)
    return ""


def _clean_search_query(query: str) -> str:
    query = _strip_prompt_suffix(query)
    query = re.sub(r"^[\s，,。？?！!：:;；]+|[\s，,。？?！!：:;；]+$", "", query)
    query = re.sub(r"^(?:你知道|知道|请问|问一下|这个|那个|啥是|什么是)\s*", "", query)
    query = re.sub(r"(?:是什么|是啥|吗|么|呢)$", "", query).strip()
    return query


def _is_bad_search_query(query: str) -> bool:
    query = _clean_search_query(query)
    if not query:
        return True
    if query in _BAD_SEARCH_QUERIES:
        return True
    return len(query) <= 1 and not re.search(r"[A-Za-z0-9]", query)


def _request_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _search_duckduckgo_html(query: str, max_results: int = 5) -> list[dict]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    html = _request_text(url)
    link_matches = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    snippet_matches = re.findall(
        r'<(?:a|div)[^>]+class="result__snippet"[^>]*>(.*?)</(?:a|div)>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    results = []
    for idx, (raw_url, raw_title) in enumerate(link_matches):
        title = _clean_html(raw_title)
        link = _clean_duckduckgo_url(raw_url)
        snippet = _clean_html(snippet_matches[idx]) if idx < len(snippet_matches) else ""
        if not title or not link:
            continue
        results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _search_bing_html(query: str, max_results: int = 5) -> list[dict]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query})
    return _parse_bing_html(_request_text(url), max_results)


def _search_bing_cn_html(query: str, max_results: int = 5) -> list[dict]:
    url = "https://cn.bing.com/search?" + urllib.parse.urlencode({
        "q": query,
        "mkt": "zh-CN",
        "setlang": "zh-CN",
    })
    return _parse_bing_html(_request_text(url), max_results)


def _parse_bing_html(html: str, max_results: int = 5) -> list[dict]:
    blocks = re.findall(r'<li\s+class="b_algo"[^>]*>.*?</li>', html, re.IGNORECASE | re.DOTALL)
    results = []
    for block in blocks:
        title_match = re.search(
            r"<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if not title_match:
            continue
        raw_url, raw_title = title_match.groups()
        title = _clean_html(raw_title)
        link = _clean_bing_url(raw_url)
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.IGNORECASE | re.DOTALL)
        snippet = _clean_html(snippet_match.group(1)) if snippet_match else ""
        if not title or not link:
            continue
        results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _search_google_html(query: str, max_results: int = 5) -> list[dict]:
    url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query, "hl": "zh-CN"})
    html = _request_text(url)
    blocks = re.findall(r'<div\s+class="g"[^>]*>.*?</div>\s*</div>\s*</div>', html, re.IGNORECASE | re.DOTALL)
    results = []
    for block in blocks:
        title_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>', block, re.IGNORECASE | re.DOTALL)
        if not title_match:
            continue
        raw_url, raw_title = title_match.groups()
        title = _clean_html(raw_title)
        link = _clean_google_url(raw_url)
        snippet_match = re.search(r'<div[^>]+(?:class="[^"]*VwiC3b[^"]*"|data-sncf="[^"]*")[^>]*>(.*?)</div>', block, re.IGNORECASE | re.DOTALL)
        snippet = _clean_html(snippet_match.group(1)) if snippet_match else ""
        if title and link and not _is_google_internal_url(link):
            results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _search_baidu_html(query: str, max_results: int = 5) -> list[dict]:
    url = "https://www.baidu.com/s?" + urllib.parse.urlencode({"wd": query})
    html = _request_text(url)
    blocks = re.findall(r'<div[^>]+class="[^"]*(?:result|c-container)[^"]*"[^>]*>.*?</div>\s*</div>', html, re.IGNORECASE | re.DOTALL)
    results = []
    for block in blocks:
        title_match = re.search(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.IGNORECASE | re.DOTALL)
        if not title_match:
            continue
        raw_url, raw_title = title_match.groups()
        title = _clean_html(raw_title)
        snippet_match = re.search(r'<span[^>]+class="[^"]*content-right[^"]*"[^>]*>(.*?)</span>|<div[^>]+class="[^"]*c-abstract[^"]*"[^>]*>(.*?)</div>', block, re.IGNORECASE | re.DOTALL)
        snippet = _clean_html(next((part for part in snippet_match.groups() if part), "")) if snippet_match else ""
        link = unescape(raw_url or "").strip()
        if title and link:
            results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _search_duckduckgo_instant_answer(query: str, max_results: int = 5) -> list[dict]:
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    })
    data = json.loads(_request_text(url))
    results = []
    abstract = str(data.get("AbstractText", "") or "").strip()
    abstract_url = str(data.get("AbstractURL", "") or "").strip()
    heading = str(data.get("Heading", "") or "").strip() or query
    if abstract and abstract_url:
        results.append({"title": heading, "url": abstract_url, "snippet": abstract})
    _collect_related_topics(data.get("RelatedTopics", []), results, max_results)
    return results[:max_results]


def _collect_related_topics(items, results: list[dict], max_results: int):
    for item in items or []:
        if len(results) >= max_results:
            return
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("Topics"), list):
            _collect_related_topics(item["Topics"], results, max_results)
            continue
        text = str(item.get("Text", "") or "").strip()
        url = str(item.get("FirstURL", "") or "").strip()
        if text and url:
            title = text.split(" - ", 1)[0][:80]
            results.append({"title": title, "url": url, "snippet": text})


def _clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_duckduckgo_url(raw_url: str) -> str:
    link = unescape(raw_url or "").strip()
    if link.startswith("//"):
        link = "https:" + link
    parsed = urllib.parse.urlsplit(link)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return target
    return link


def _clean_bing_url(raw_url: str) -> str:
    link = unescape(raw_url or "").strip()
    parsed = urllib.parse.urlsplit(link)
    if "bing.com" in parsed.netloc and parsed.path.startswith("/ck/"):
        encoded = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            encoded = encoded[2:]
        if encoded:
            padding = "=" * ((4 - len(encoded) % 4) % 4)
            try:
                decoded = base64.urlsafe_b64decode(encoded + padding).decode("utf-8", errors="replace")
            except Exception:
                decoded = ""
            if decoded.startswith(("http://", "https://")):
                return decoded
    return link


def _clean_google_url(raw_url: str) -> str:
    link = unescape(raw_url or "").strip()
    parsed = urllib.parse.urlsplit(link)
    if parsed.path == "/url":
        target = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
        if target:
            return target
    return link


def _is_google_internal_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.netloc.endswith("google.com") and parsed.path.startswith(("/search", "/preferences", "/settings"))


def _format_search_results(query: str, results: list[dict], engine: str = "bing_cn") -> str:
    lines = [
        f"查询：{query}",
        f"搜索引擎：{WEB_SEARCH_ENGINE_LABELS.get(_normalize_search_engine(engine), 'Bing CN')}",
        "检索时间：" + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    for index, result in enumerate(results, 1):
        lines.append(
            f"{index}. {result.get('title', '').strip()}\n"
            f"   URL: {result.get('url', '').strip()}\n"
            f"   摘要：{result.get('snippet', '').strip()}"
        )
    return "\n".join(lines)
