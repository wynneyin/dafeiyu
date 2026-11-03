#!/usr/bin/env python
"""Claude 接入冒烟测试。

用法：
    .venv\\Scripts\\python tools\\claude_smoke_test.py          # 直连 Claude，测人设 + 上下文记忆
    .venv\\Scripts\\python tools\\claude_smoke_test.py --e2e    # 再走一遍主程序 HTTP API（需先「一键运行」）

Key 优先读 config.json 的 claude.api_key / auth_token，留空就读环境变量
ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN。
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def load_config():
    with (ROOT / "config.json").open(encoding="utf-8") as f:
        return json.load(f)


def check_config(config):
    assert "claude" in config, "config.json 缺少 claude 配置段"
    claude = config["claude"]
    for key in ("model", "preset", "history_enable", "history_max_len"):
        assert key in claude, f"config.json 缺少 claude.{key}"
    has_key = claude.get("api_key") or claude.get("auth_token") \
        or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    assert has_key, "没有可用的 Key：填 claude.api_key / auth_token，或设置 ANTHROPIC_AUTH_TOKEN 环境变量"
    print(f"  OK   chat_type={config.get('chat_type')} model={claude['model']} base_url={claude.get('base_url') or os.environ.get('ANTHROPIC_BASE_URL') or '官方'}")


def check_direct(config):
    from utils.gpt_model.claude import Claude

    claude = Claude(dict(config["claude"], history_enable=True))

    started = time.time()
    first = claude.get_resp("观众昵称：小明\n观众发言：你好呀，你叫什么名字？")
    assert first, "第一轮没有返回内容，看上面的日志排查 base_url / Key / 模型名"
    print(f"  OK   第一轮 ({time.time() - started:.1f}s)：{first}")
    assert "大肥鱼" in first, "回复里没自称大肥鱼，人设可能没生效"

    started = time.time()
    second = claude.get_resp("观众昵称：小明\n观众发言：我刚才问了你什么？")
    assert second, "第二轮没有返回内容"
    print(f"  OK   第二轮 ({time.time() - started:.1f}s)：{second}")
    assert len(claude.history) == 4, f"上下文记忆条数不对：{len(claude.history)}"
    print("  OK   上下文记忆 4 条")


def check_e2e(config):
    url = f"http://127.0.0.1:{config['api_port']}/llm"
    body = json.dumps({"type": "claude", "username": "冒烟测试", "content": "用一句话跟直播间打个招呼"}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            resp_json = json.loads(response.read().decode("utf-8"))
    except OSError as e:
        raise AssertionError(f"连不上主程序 {url}：{e}。先在 WebUI 点「一键运行」") from e

    content = (resp_json.get("data") or {}).get("content")
    assert resp_json.get("code") == 200 and content, f"主程序 /llm 返回异常：{resp_json}"
    print(f"  OK   主程序 /llm ({time.time() - started:.1f}s)：{content}")


def main():
    parser = argparse.ArgumentParser(description="Claude 接入冒烟测试")
    parser.add_argument("--e2e", action="store_true", help="同时测试主程序 HTTP API")
    args = parser.parse_args()

    config = load_config()

    print("[1/3] 配置检查")
    check_config(config)

    print("[2/3] 直连 Claude")
    check_direct(config)

    if args.e2e:
        print("[3/3] 主程序 /llm 接口")
        check_e2e(config)
    else:
        print("[3/3] 已跳过主程序（加 --e2e 开启）")

    print("CLAUDE SMOKE OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"\nCLAUDE SMOKE FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
