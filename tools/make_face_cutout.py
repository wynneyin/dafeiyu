"""把一张人物照片裁成贴脸图（透明 PNG），放到 Live2D/faces。

贴脸图的要求：头部居中、背景透明、多余的脖子/球衣尽量裁掉。
默认按蓝幕抠图（这套直播间素材多是蓝背景），也可以传 --key none 直接裁切。

用法：
    python tools/make_face_cutout.py 照片.webp --name 牢大
    python tools/make_face_cutout.py 照片.png --name 牢大 --key none
    python tools/make_face_cutout.py 照片.webp --name 牢大 --crop 0.30,0.02,0.70,0.44

生成 Live2D/faces/<名字>.png 后，角色管理页「动作与表情 → 贴脸」会自动出现。
"""

import argparse
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
FACES = ROOT / "Live2D" / "faces"


def parse_crop(text):
    parts = [float(x) for x in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--crop 需要 4 个 0~1 的小数：x0,y0,x1,y1")
    return parts


def chroma_blue(img):
    """把蓝色背景抠掉，边缘做一点羽化。返回 RGBA。"""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            blueness = b - max(r, g)
            if blueness > 22 and b > 90:
                px[x, y] = (r, g, b, 0)
            elif blueness > 10 and b > 80:
                alpha = int((22 - blueness) / 12 * 255)
                px[x, y] = (r, g, b, max(0, min(a, alpha)))
    alpha = img.getchannel("A").filter(ImageFilter.GaussianBlur(1.2))
    img.putalpha(alpha)
    return img


def trim(img):
    """裁到不透明内容的包围盒，避免贴脸图里留一圈透明边导致定位偏移。"""
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def main():
    parser = argparse.ArgumentParser(description="生成 Live2D 贴脸图")
    parser.add_argument("source", help="原始照片（webp/png/jpg 都可以）")
    parser.add_argument("--name", required=True, help="贴脸图名字，也是配置里 face 的值")
    parser.add_argument("--crop", type=parse_crop, default=[0.30, 0.02, 0.70, 0.44],
                        help="裁剪范围（相对宽高）：x0,y0,x1,y1，默认只取头部")
    parser.add_argument("--key", choices=["blue", "none"], default="blue",
                        help="背景处理：blue=蓝幕抠图（默认），none=原图裁切")
    parser.add_argument("--out-dir", default=str(FACES), help="输出目录，默认 Live2D/faces")
    args = parser.parse_args()

    src = Image.open(args.source)
    w, h = src.size
    x0, y0, x1, y1 = args.crop
    box = (int(w * x0), int(h * y0), int(w * x1), int(h * y1))
    img = src.crop(box)

    if args.key == "blue":
        img = chroma_blue(img)
    else:
        img = img.convert("RGBA")
    img = trim(img)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.name}.png"
    img.save(out)
    print(f"已生成 {out}（{img.width}x{img.height}）")


if __name__ == "__main__":
    main()
