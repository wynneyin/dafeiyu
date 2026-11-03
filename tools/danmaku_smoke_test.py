"""弹幕冒烟测试：注入一条弹幕，验证 弹幕 -> LLM -> TTS -> 字幕 全链路。

用法：
    .venv\\Scripts\\python.exe tools\\danmaku_smoke_test.py
    .venv\\Scripts\\python.exe tools\\danmaku_smoke_test.py --content "点一首歌" --timeout 60

前提：主程序已在跑（HTTP API 端口取自 config.json 的 api_port），字幕服务在 5500。
退出码 0 = 全链路通过，1 = 有环节失败。
"""

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

USERNAME = "冒烟测试"


def load_config():
    with (ROOT / "config.json").open(encoding="utf-8") as f:
        return json.load(f)


def post_json(url, payload, timeout=15):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def newest_log():
    logs = sorted((ROOT / "log").glob("log-*.txt"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def read_since(path, offset):
    with path.open("rb") as f:
        f.seek(offset)
        return f.read().decode("utf-8", errors="replace"), f.tell()


def wait_for(read_log, patterns, timeout, label):
    """轮询日志，直到 patterns 里的标记全部出现或超时。"""
    deadline = time.time() + timeout
    seen_text = ""
    while time.time() < deadline:
        text, _ = read_log()
        seen_text += text
        if all(p in seen_text for p in patterns):
            return seen_text
        time.sleep(0.5)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", default="用一句话跟直播间打个招呼")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    cfg = load_config()
    port = int(cfg.get("api_port") or 8082)
    base = f"http://127.0.0.1:{port}"
    reply = ""
    checks = {}

    print("=" * 56)
    print("大肥鱼 弹幕冒烟测试")
    print(f"主程序 API : {base}")
    print(f"LLM        : {cfg.get('chat_type')} / {cfg.get('claude', {}).get('model')}")
    print(f"TTS        : {cfg.get('audio_synthesis_type')}")
    print("=" * 56)

    # 0. 主程序在线
    try:
        info = get_json(f"{base}/get_sys_info")
        checks["main_api"] = info.get("code") == 200
        print(f"[1/5] 主程序 API .......... {'OK' if checks['main_api'] else 'FAIL'}")
    except Exception as exc:
        print(f"[1/5] 主程序 API .......... FAIL ({exc})")
        print("RESULT: FAIL")
        return 1

    caption_id_before = 0
    try:
        caption_id_before = int(get_json("http://127.0.0.1:5500/state").get("id") or 0)
    except Exception:
        pass

    log_path = newest_log()
    if log_path is None:
        print("找不到日志文件 log/log-*.txt")
        print("RESULT: FAIL")
        return 1
    offset = log_path.stat().st_size

    def read_log():
        return read_since(log_path, offset)

    # 1. 注入弹幕
    payload = {
        "type": "comment",
        "data": {"platform": "dy", "username": USERNAME, "content": args.content},
    }
    try:
        resp = post_json(f"{base}/send", payload)
        checks["inject"] = resp.get("code") == 200
        print(f"[2/5] 注入弹幕 ............ {'OK' if checks['inject'] else 'FAIL'} ({resp})")
    except Exception as exc:
        print(f"[2/5] 注入弹幕 ............ FAIL ({exc})")
        print("RESULT: FAIL")
        return 1

    # 2. 日志里出现回复
    text = wait_for(read_log, ["send接口收到数据", f"[AI回复{USERNAME}]"], args.timeout, "reply")
    if text:
        checks["reply"] = True
        for line in text.splitlines():
            if f"[AI回复{USERNAME}]" in line:
                reply = line.split(f"[AI回复{USERNAME}]：", 1)[-1].strip()
        print("[3/5] LLM 生成回复 ........ OK")
        print(f"      回复：{reply}")
    else:
        checks["reply"] = False
        print("[3/5] LLM 生成回复 ........ FAIL（超时或报错）")

    # 3. TTS 合成（合成在回复之后异步进行，最多再等 20 秒）
    tts_text = ""
    pattern = f"合成内容：【{reply}" if reply else "合成成功"
    deadline = time.time() + 20
    while time.time() < deadline:
        tts_text, _ = read_log()
        if pattern in tts_text or "合成失败" in tts_text:
            break
        time.sleep(0.5)

    if pattern in tts_text:
        checks["tts"] = True
        print("[4/5] TTS 合成 ............ OK")
    else:
        checks["tts"] = False
        print("[4/5] TTS 合成 ............ FAIL")
        for sig in ("LLM没有正确返回数据", "无返回", "合成失败", "Could not resolve authentication"):
            if sig in tts_text:
                print(f"      日志命中：{sig}")

    # 4. 字幕服务收到台词
    caption_ok = False
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            state = get_json("http://127.0.0.1:5500/state")
            if state.get("text") and int(state.get("id") or 0) > caption_id_before:
                caption_ok = True
                checks["caption"] = True
                if reply and state["text"][:10] in reply:
                    checks["caption_match"] = True
                print(f"[5/5] 字幕服务 ............ OK（{state['text'][:40]}）")
                break
        except Exception:
            break
        time.sleep(0.5)
    if not caption_ok:
        checks["caption"] = False
        print("[5/5] 字幕服务 ............ FAIL（没收到台词，检查 5500 是否在跑）")

    ok = all(checks.get(k) for k in ("main_api", "inject", "reply", "tts"))
    print("-" * 56)
    print(f"弹幕内容：{USERNAME}：{args.content}")
    print(f"时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"日志：{log_path}")
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
