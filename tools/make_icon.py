# -*- coding: utf-8 -*-
"""由 app.png 生成应用图标资源。

生成内容：
  assets/icon.ico       Windows 多尺寸图标（快捷方式 / 任务栏 / 通知）
  assets/icon.png       256x256 主图标
  assets/icon-192.png   PWA 图标
  assets/icon-512.png   PWA 图标
  assets/icon-32.png    网页 favicon

用法（需要 Pillow）：
  python tools/make_icon.py
"""

from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "app.png"
ASSETS = BASE / "assets"

ICO_SIZES = [16, 24, 32, 40, 48, 64, 96, 128, 256]


def square(img: Image.Image) -> Image.Image:
    """居中裁剪成正方形，避免图标被拉伸变形。"""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def main() -> None:
    source = SRC
    if not source.exists():
        # app.png 丢失时，退回到已有的 icon.png（256x256）
        fallback = ASSETS / "icon.png"
        if not fallback.exists():
            raise SystemExit(f"找不到源图: {SRC}")
        source = fallback

    ASSETS.mkdir(parents=True, exist_ok=True)
    src = Image.open(source).convert("RGBA")
    base = square(src)

    base.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    base.resize((512, 512), Image.LANCZOS).save(ASSETS / "icon-512.png")
    base.resize((192, 192), Image.LANCZOS).save(ASSETS / "icon-192.png")
    base.resize((32, 32), Image.LANCZOS).save(ASSETS / "icon-32.png")
    base.resize((48, 48), Image.LANCZOS).save(ASSETS / "icon-48.png")

    base.save(ASSETS / "icon.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES])

    print("图标已生成：")
    for p in sorted(ASSETS.iterdir()):
        print(f"  {p.name}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
