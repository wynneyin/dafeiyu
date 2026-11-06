"""给 Live2D 模型的 EXP 表情补水印参数。

大肥鱼围裙上有作者水印，运行时靠常驻表情「13 水印消除」（Paramcol_3=1）遮住。
舞台切换到其他表情时，expressionManager 会用新表情顶掉旧表情，水印就露出来了。
这个脚本把 Paramcol_3 追加进每个表情，切换表情时水印仍然隐藏。

只改 EXP/*.exp3.json，不动 moc3/纹理。重复执行是幂等的。

用法：
    python tools/patch_expression_watermark.py                 # 默认处理大肥鱼
    python tools/patch_expression_watermark.py --dry-run
    python tools/patch_expression_watermark.py --model-dir "Live2D/live2d-model/别的模型/EXP"
"""

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "Live2D" / "live2d-model" / "大肥鱼" / "EXP"
PARAM = "Paramcol_3"
SKIP_PREFIX = "13"


def patch(directory: Path, param: str, value: float, dry_run: bool):
    changed = []
    if not directory.is_dir():
        raise SystemExit(f"目录不存在：{directory}")
    for path in sorted(directory.glob("*.exp3.json")):
        if path.name.startswith(SKIP_PREFIX):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        params = data.setdefault("Parameters", [])
        if any(item.get("Id") == param for item in params):
            continue
        params.append({"Id": param, "Value": value, "Blend": "Add"})
        changed.append(path.name)
        if dry_run:
            continue
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    return changed


def main():
    parser = argparse.ArgumentParser(description="给 EXP 表情补水印参数")
    parser.add_argument("--model-dir", default=str(DEFAULT), help="模型的 EXP 目录")
    parser.add_argument("--param", default=PARAM, help="参数 id，默认 Paramcol_3")
    parser.add_argument("--value", type=float, default=1.0, help="参数值，默认 1")
    parser.add_argument("--dry-run", action="store_true", help="只列出会改的文件")
    args = parser.parse_args()

    changed = patch(Path(args.model_dir), args.param, args.value, args.dry_run)
    action = "将修改" if args.dry_run else "已修改"
    print(f"{action} {len(changed)} 个表情文件（参数 {args.param}={args.value}）")
    for name in changed:
        print(" -", name)


if __name__ == "__main__":
    main()
