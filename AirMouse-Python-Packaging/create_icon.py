#!/usr/bin/env python3
"""
create_icon.py — 生成 Air Mouse 应用图标
输出：assets/icon.icns（macOS 图标格式）
      assets/icon.png（1024×1024 原始图）
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
ASSETS.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1. 确保 Pillow 可用
# ─────────────────────────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pillow", "-q"], check=True)
    from PIL import Image, ImageDraw  # type: ignore


def _draw_icon(size: int) -> Image.Image:
    """
    绘制 Air Mouse 图标：
    · 深色圆形背景
    · 白色简化手型轮廓
    · 蓝色食指尖高亮（代表点击手势）
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    s = size / 128.0   # 缩放基准

    # ── 背景圆 ──
    pad = size * 0.04
    d.ellipse(
        [pad, pad, size - pad, size - pad],
        fill=(28, 28, 32, 255),
    )

    # ── 手型轮廓（简化为 5 根手指 + 手掌） ──
    cx = size * 0.50
    cy = size * 0.54

    def pt(dx, dy):
        return (cx + dx * s, cy + dy * s)

    # 手掌主体
    palm = [
        pt(-22, 30), pt(-22, 5),
        pt(-16, 5),  pt(-16, -14),
        pt(-8, -14), pt(-8, -28),
        pt(0, -28),  pt(0, -14),
        pt(8, -14),  pt(8, -30),
        pt(16, -30), pt(16, -14),
        pt(22, -14), pt(22, -6),
        pt(28, -6),  pt(28, 8),
        pt(22, 12),  pt(22, 30),
    ]
    d.polygon(palm, fill=(240, 240, 245, 255))

    # 拇指
    thumb = [
        pt(-22, 5), pt(-34, -8), pt(-36, -16),
        pt(-28, -20), pt(-20, -12), pt(-16, -4),
    ]
    d.polygon(thumb, fill=(240, 240, 245, 255))

    # ── 食指尖蓝色高亮（代表捏合点击手势）──
    d.ellipse(
        [pt(-9, -38)[0], pt(-9, -38)[1], pt(9, -22)[0], pt(9, -22)[1]],
        fill=(10, 132, 255, 255),
    )

    # ── 轮廓描边（深色，增加清晰度）──
    d.polygon(palm, outline=(60, 60, 70, 180), width=max(1, int(s * 1.5)))

    return img


# ─────────────────────────────────────────────────────────────────────────────
# 2. 生成 PNG 和 ICNS
# ─────────────────────────────────────────────────────────────────────────────
def build_icns() -> None:
    # 保存高分辨率 PNG（用于 Windows 也可复用）
    png_path = ASSETS / "icon.png"
    _draw_icon(1024).save(str(png_path))
    print(f"✓ 图标 PNG：{png_path}")

    # 仅在 macOS 上生成 ICNS
    if sys.platform != "darwin":
        print("⚠  非 macOS 环境，跳过 ICNS 生成（构建时再运行）")
        return

    sizes = [16, 32, 64, 128, 256, 512, 1024]

    with tempfile.TemporaryDirectory() as tmp:
        iconset_dir = os.path.join(tmp, "icon.iconset")
        os.makedirs(iconset_dir)

        for sz in sizes:
            img = _draw_icon(sz)
            img.save(os.path.join(iconset_dir, f"icon_{sz}x{sz}.png"))
            if sz <= 512:
                img2x = _draw_icon(sz * 2)
                img2x.save(os.path.join(iconset_dir, f"icon_{sz}x{sz}@2x.png"))

        icns_path = str(ASSETS / "icon.icns")
        subprocess.run(
            ["iconutil", "-c", "icns", iconset_dir, "-o", icns_path],
            check=True,
        )
        print(f"✓ 图标 ICNS：{icns_path}")


if __name__ == "__main__":
    build_icns()
