"""把一张 PNG 转换成多尺寸 ICO（exe 图标 + 浏览器 favicon）。

用法：
    uv run --with pillow python scripts/make_icon.py <源图片.png>

产物：
    launcher/app.ico            打包进 exe（见 traffic_forwarding.spec 的 icon=）
    frontend/public/favicon.ico 浏览器标签页
    frontend/public/favicon.png 高分辨率备用
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/make_icon.py <源图片>", file=sys.stderr)
        return 2

    source = Path(sys.argv[1]).expanduser().resolve()
    if not source.is_file():
        print(f"找不到文件：{source}", file=sys.stderr)
        return 2

    image = Image.open(source).convert("RGBA")

    # 非正方形时居中裁切，避免图标被拉伸
    width, height = image.size
    if width != height:
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        image = image.crop((left, top, left + side, top + side))

    icon_path = ROOT / "launcher" / "app.ico"
    image.save(icon_path, format="ICO", sizes=SIZES)
    print(f"ICO   -> {icon_path} ({icon_path.stat().st_size:,} bytes)")

    public_dir = ROOT / "frontend" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)

    favicon_ico = public_dir / "favicon.ico"
    image.save(favicon_ico, format="ICO", sizes=SIZES)
    print(f"FAVICON -> {favicon_ico}")

    favicon_png = public_dir / "favicon.png"
    image.resize((64, 64), Image.LANCZOS).save(favicon_png, format="PNG")
    print(f"PNG   -> {favicon_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
