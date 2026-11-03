"""角色快速管理页：切皮套、换音色、改人设、存角色档案。

独立的小服务，默认 http://127.0.0.1:8090 ，只监听本机。
- 皮套：列出 Live2D/live2d-model 下的模型，写 model_name.js + avatar.json，
  舞台页检测到 avatar.json 变化会自动刷新，OBS 不用手动点。
- 音色：写 config.json 的 edge-tts 段，支持在线试听，然后通知主程序热重载。
- 人设：写 config.json 的 claude.preset，同样热重载，不重启进程。
- 角色档案：把「皮套 + 音色 + 人设 + LLM」存成一套，以后一键切换。

依赖都是项目已有的：标准库 + edge_tts（试听用）。
"""

import json
import os
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"
MODEL_ROOT = ROOT / "Live2D" / "live2d-model"
MODEL_JS = ROOT / "Live2D" / "js" / "model_name.js"
AVATAR_JSON = ROOT / "Live2D" / "avatar.json"
PROFILES = ROOT / "data" / "characters.json"
HTML = ROOT / "tools" / "character_manager.html"

HOST = "127.0.0.1"
PORT = 8090

# 常用中文音色，含官方 id 和一句风格说明
VOICES = [
    ("zh-CN-XiaoyiNeural", "晓伊 · 女声 · 活泼"),
    ("zh-CN-XiaoxiaoNeural", "晓晓 · 女声 · 温柔"),
    ("zh-CN-XiaochenNeural", "晓辰 · 女声 · 轻松"),
    ("zh-CN-XiaohanNeural", "晓涵 · 女声 · 温暖"),
    ("zh-CN-XiaomengNeural", "晓梦 · 女声 · 可爱"),
    ("zh-CN-XiaomoNeural", "晓墨 · 女声 · 成熟"),
    ("zh-CN-XiaoqiuNeural", "晓秋 · 女声 · 知性"),
    ("zh-CN-XiaoruiNeural", "晓睿 · 女声 · 稳重"),
    ("zh-CN-XiaoshuangNeural", "晓双 · 女声 · 童声"),
    ("zh-CN-XiaoxuanNeural", "晓萱 · 女声 · 自信"),
    ("zh-CN-XiaoyanNeural", "晓颜 · 女声 · 亲和"),
    ("zh-CN-XiaoyouNeural", "晓悠 · 女声 · 童声"),
    ("zh-CN-XiaozhenNeural", "晓甄 · 女声 · 干练"),
    ("zh-CN-YunxiNeural", "云希 · 男声 · 阳光"),
    ("zh-CN-YunjianNeural", "云健 · 男声 · 沉稳"),
    ("zh-CN-YunxiaNeural", "云夏 · 男声 · 少年"),
    ("zh-CN-YunyangNeural", "云扬 · 男声 · 播音腔"),
    ("zh-CN-liaoning-XiaobeiNeural", "小北 · 女声 · 东北话"),
    ("zh-CN-shaanxi-XiaoniNeural", "小妮 · 女声 · 陕西话"),
    ("zh-TW-HsiaoChenNeural", "曉臻 · 女声 · 台湾腔"),
    ("zh-TW-HsiaoYuNeural", "曉雨 · 女声 · 台湾腔"),
    ("zh-HK-HiuMaanNeural", "曉曼 · 女声 · 粤语"),
]

_lock = threading.Lock()


# ---------------------------------------------------------------- 工具
def read_config():
    with CONFIG.open(encoding="utf-8") as f:
        return json.load(f)


def write_config(cfg):
    """原子写，避免主程序正好在读半截文件。"""
    tmp = CONFIG.with_name(CONFIG.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG)


def normalize_rate(value):
    """接受 10 / "+10%" / -5，统一成 "+10%" 这种格式。"""
    text = str(value or "").strip().replace("％", "%")
    if not text:
        return "+0%"
    if text.endswith("%"):
        text = text[:-1]
    try:
        number = int(float(text))
    except ValueError:
        return "+0%"
    number = max(-100, min(100, number))
    return f"{number:+d}%"


def model_list():
    items = []
    if not MODEL_ROOT.is_dir():
        return items
    for path in sorted(MODEL_ROOT.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir():
            continue
        model3 = next(path.glob("*.model3.json"), None)
        if model3 is None:
            continue
        thumb = ""
        try:
            data = json.loads(model3.read_text(encoding="utf-8"))
            textures = (data.get("FileReferences") or {}).get("Textures") or []
            if textures:
                rel = textures[0].lstrip("/")
                thumb = (
                    "http://127.0.0.1:12345/Live2D/live2d-model/"
                    + quote(path.name)
                    + "/"
                    + "/".join(quote(part) for part in rel.split("/"))
                )
        except Exception:
            pass
        items.append({"name": path.name, "thumb": thumb, "model3": model3.name})
    return items


def current_profile(cfg):
    edge = cfg.get("edge-tts") or {}
    return {
        "model": (cfg.get("live2d") or {}).get("name", ""),
        "voice": edge.get("voice", "zh-CN-XiaoyiNeural"),
        "rate": edge.get("rate", "+0%"),
        "volume": edge.get("volume", "+0%"),
        "preset": (cfg.get("claude") or {}).get("preset", ""),
        "llm_model": (cfg.get("claude") or {}).get("model", ""),
    }


def load_profiles():
    if not PROFILES.exists():
        return []
    try:
        data = json.loads(PROFILES.read_text(encoding="utf-8"))
        return data.get("profiles", [])
    except Exception:
        return []


def save_profiles(profiles):
    PROFILES.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROFILES.with_name(PROFILES.name + ".tmp")
    tmp.write_text(json.dumps({"profiles": profiles}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, PROFILES)


def llm_models():
    """从本地中转拿模型列表，拿不到就返回空，不影响页面。"""
    try:
        cfg = read_config()
        base = ((cfg.get("claude") or {}).get("base_url") or "").rstrip("/")
        if not base:
            return []
        req = urllib.request.Request(base + "/v1/models", headers={"Authorization": "Bearer local-relay"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("id") for m in data.get("data", []) if m.get("id")]
    except Exception:
        return []


def main_online():
    try:
        cfg = read_config()
        port = int(cfg.get("api_port") or 8082)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/get_sys_info", timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8")).get("code") == 200
    except Exception:
        return False


def reload_main():
    cfg = read_config()
    port = int(cfg.get("api_port") or 8082)
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/admin/reload", data=b"", method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return bool(body.get("code") == 200), body.get("message", "")
    except Exception as exc:
        return False, str(exc)


def write_model_files(name, bump=True):
    target = MODEL_ROOT / name
    if not target.is_dir():
        raise ValueError(f"模型目录不存在：{target}")
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    MODEL_JS.parent.mkdir(parents=True, exist_ok=True)
    MODEL_JS.write_text(f'var model_name = "{escaped}";\n', encoding="utf-8")
    if bump:
        # 只有真的换皮套才改 token，避免重复保存时舞台白闪一下
        AVATAR_JSON.write_text(
            json.dumps({"name": name, "token": int(time.time() * 1000)}, ensure_ascii=False),
            encoding="utf-8",
        )


def apply_profile(payload):
    """把页面上的选择落盘，并通知主程序热重载。"""
    messages = []
    model = str(payload.get("model") or "").strip()
    voice = str(payload.get("voice") or "").strip()
    rate = normalize_rate(payload.get("rate"))
    volume = normalize_rate(payload.get("volume"))
    preset = str(payload.get("preset") or "")
    llm_model = str(payload.get("llm_model") or "").strip()

    with _lock:
        cfg = read_config()
        old_model = (cfg.get("live2d") or {}).get("name", "")
        if model:
            write_model_files(model, bump=(model != old_model))
            cfg.setdefault("live2d", {})["name"] = model
        if voice:
            cfg.setdefault("edge-tts", {}).update({"voice": voice, "rate": rate, "volume": volume})
        if preset:
            cfg.setdefault("claude", {})["preset"] = preset
        if llm_model:
            cfg.setdefault("claude", {})["model"] = llm_model
        write_config(cfg)

    messages.append("配置已保存")
    if model and model != old_model:
        messages.append(f"皮套已切到「{model}」，舞台 2 秒内自动刷新")
    elif model:
        messages.append(f"皮套仍是「{model}」")

    ok, detail = reload_main()
    if ok:
        messages.append("主程序已热重载：新音色、新人设立即生效")
    else:
        messages.append(f"主程序未重载（{detail}）；配置已存盘，下次启动生效")
    return messages


def synth_preview(payload):
    import asyncio
    import edge_tts

    text = str(payload.get("text") or "").strip() or "大家好，我是大肥鱼，今天也要好好搬砖。"
    voice = str(payload.get("voice") or "zh-CN-XiaoyiNeural")
    rate = normalize_rate(payload.get("rate"))
    volume = normalize_rate(payload.get("volume"))
    proxy = ""
    try:
        proxy = ((read_config().get("edge-tts") or {}).get("proxy") or "").strip()
    except Exception:
        pass

    async def run():
        comm = edge_tts.Communicate(text, voice, rate=rate, volume=volume, proxy=proxy or None)
        chunks = bytearray()
        async for part in comm.stream():
            if part.get("type") == "audio":
                chunks.extend(part["data"])
        return bytes(chunks)

    return asyncio.run(run())


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "DafeiyuManager/1.0"

    def log_message(self, *args):
        pass

    def _json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            raw = HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=UTF-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if path == "/api/state":
            cfg = read_config()
            state = current_profile(cfg)
            state.update(
                {
                    "models": model_list(),
                    "voices": [{"id": i, "label": label} for i, label in VOICES],
                    "profiles": load_profiles(),
                    "llm_models": llm_models(),
                    "main_online": main_online(),
                    "chat_type": cfg.get("chat_type"),
                    "tts_type": cfg.get("audio_synthesis_type"),
                }
            )
            self._json({"ok": True, "state": state})
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            payload = self._body()
        except Exception as exc:
            self._json({"ok": False, "error": f"请求体不是合法 JSON：{exc}"}, 400)
            return

        try:
            if path == "/api/apply":
                messages = apply_profile(payload)
                self._json({"ok": True, "messages": messages})
                return

            if path == "/api/preview":
                audio = synth_preview(payload)
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(audio)))
                self.end_headers()
                self.wfile.write(audio)
                return

            if path == "/api/profile/save":
                name = str(payload.get("name") or "").strip()
                if not name:
                    self._json({"ok": False, "error": "档案名不能为空"}, 400)
                    return
                data = {
                    "id": str(int(time.time() * 1000)),
                    "name": name[:24],
                    "model": str(payload.get("model") or ""),
                    "voice": str(payload.get("voice") or ""),
                    "rate": normalize_rate(payload.get("rate")),
                    "volume": normalize_rate(payload.get("volume")),
                    "preset": str(payload.get("preset") or ""),
                    "llm_model": str(payload.get("llm_model") or ""),
                    "created_at": time.strftime("%Y-%m-%d %H:%M"),
                }
                profiles = [p for p in load_profiles() if p.get("name") != data["name"]]
                profiles.append(data)
                save_profiles(profiles)
                self._json({"ok": True, "profiles": profiles})
                return

            if path == "/api/profile/delete":
                pid = str(payload.get("id") or "")
                profiles = [p for p in load_profiles() if p.get("id") != pid]
                save_profiles(profiles)
                self._json({"ok": True, "profiles": profiles})
                return

            if path == "/api/profile/apply":
                pid = str(payload.get("id") or "")
                profile = next((p for p in load_profiles() if p.get("id") == pid), None)
                if not profile:
                    self._json({"ok": False, "error": "档案不存在"}, 404)
                    return
                messages = apply_profile(profile)
                self._json({"ok": True, "messages": messages})
                return
        except Exception as exc:
            traceback.print_exc()
            self._json({"ok": False, "error": str(exc)}, 500)
            return

        self._json({"ok": False, "error": "not found"}, 404)


def main():
    if not HTML.exists():
        raise SystemExit(f"缺少页面文件：{HTML}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"角色管理页已启动：http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
