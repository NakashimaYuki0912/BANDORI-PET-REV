import base64
import gzip
import http.client
import json
import ssl
import threading
import time
import urllib.parse
from datetime import datetime

_CACHE_TTL = 1800  # 30 minutes

_lock = threading.Lock()
_cache_text: str = ""
_cache_time: float = 0.0
_cache_id: str = ""

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _generate_jwt(private_key_pem: str, key_id: str, project_id: str) -> str:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    private_key = load_pem_private_key(private_key_pem.strip().encode(), password=None)

    def b64u(data: dict) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(data, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()

    now = int(time.time())
    header = b64u({"alg": "EdDSA", "kid": key_id})
    payload = b64u({"sub": project_id, "iat": now - 30, "exp": now + 3600})
    message = f"{header}.{payload}".encode()
    signature = private_key.sign(message)
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload}.{sig_b64}"


def _make_request(url: str, jwt_token: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query

    conn = http.client.HTTPSConnection(host, context=_SSL_CTX, timeout=10)
    try:
        conn.request(
            "GET",
            path,
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "User-Agent": "BandoriPet/1.0",
                "Host": host,
                "Accept-Encoding": "gzip",
            },
        )
        resp = conn.getresponse()
        raw = resp.read()
    finally:
        conn.close()

    if resp.getheader("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    data = json.loads(raw)
    if resp.status != 200 and "error" in data:
        err = data["error"]
        raise RuntimeError(f"HTTP {resp.status}: {err.get('detail', err.get('title', ''))}")
    return data


def _build_host(api_host: str) -> str:
    host = api_host.strip().rstrip("/")
    if not host.startswith("http"):
        host = "https://" + host
    return host


def get_weather_prompt(
    private_key_pem: str, api_host: str, location: str, key_id: str, project_id: str
) -> str:
    """Return a weather+time text snippet for the system prompt, or '' if unavailable."""
    global _cache_text, _cache_time, _cache_id
    if not private_key_pem or not api_host or not location or not key_id or not project_id:
        return ""
    current_id = f"{key_id}:{project_id}:{api_host}:{location}"
    with _lock:
        if _cache_id == current_id and _cache_text and (time.time() - _cache_time) < _CACHE_TTL:
            return _cache_text
    try:
        text = _fetch_weather_text(private_key_pem, api_host, location, key_id, project_id)
    except Exception:
        text = ""
    with _lock:
        _cache_text = text
        _cache_time = time.time()
        _cache_id = current_id
    return text


def test_weather(
    private_key_pem: str, api_host: str, location: str, key_id: str, project_id: str
) -> tuple[bool, str]:
    if not private_key_pem:
        return False, "私钥为空"
    if not key_id:
        return False, "凭据 ID 为空（控制台项目页面查看）"
    if not project_id:
        return False, "项目 ID 为空（控制台项目页面查看）"
    if not api_host:
        return False, "API Host 为空（控制台 → 设置中查看）"
    if not location:
        return False, "位置为空，请填写 LocationID 或经纬度坐标"
    host = _build_host(api_host)
    try:
        jwt_token = _generate_jwt(private_key_pem, key_id, project_id)
        url = f"{host}/v7/weather/3d?location={urllib.parse.quote(location)}&lang=zh&unit=m"
        data = _make_request(url, jwt_token)
        code = data.get("code", "?")
        if code != "200":
            return False, (
                f"天气查询失败（code={code}）\n"
                f"code=401: 认证失败  code=403: 权限不足  code=404: 位置不存在\n"
                f"位置格式：LocationID（如 101240101）或 经度,纬度（如 115.86,28.68）"
            )
        daily = data.get("daily", [])
        if not daily:
            return False, "返回数据为空"
        today = daily[0]
        msg = (
            f"✓ 今日：{today['textDay']}，{today['tempMin']}~{today['tempMax']}°C，"
            f"湿度{today['humidity']}%，{today['windDirDay']}{today['windScaleDay']}级"
        )
        return True, msg
    except Exception as e:
        return False, f"请求异常：{e}"


def invalidate_cache():
    global _cache_time
    with _lock:
        _cache_time = 0.0


def _fetch_weather_text(
    private_key_pem: str, api_host: str, location: str, key_id: str, project_id: str
) -> str:
    host = _build_host(api_host)
    jwt_token = _generate_jwt(private_key_pem, key_id, project_id)
    url = f"{host}/v7/weather/3d?location={urllib.parse.quote(location)}&lang=zh&unit=m"
    data = _make_request(url, jwt_token)
    if data.get("code") != "200":
        return ""
    daily = data.get("daily", [])
    if not daily:
        return ""
    today = daily[0]
    time_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    parts = [
        "【当前时间与天气】",
        f"现在是{time_str}。",
        f"今日天气：{today['textDay']}，气温{today['tempMin']}~{today['tempMax']}°C，"
        f"湿度{today['humidity']}%，{today['windDirDay']}{today['windScaleDay']}级。",
    ]
    if len(daily) > 1:
        tmr = daily[1]
        parts.append(
            f"明日天气：{tmr['textDay']}，气温{tmr['tempMin']}~{tmr['tempMax']}°C。"
        )
    return "\n".join(parts)
