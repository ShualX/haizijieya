#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成自动解压工具的精美图标"""
from PIL import Image, ImageDraw, ImageFilter
import math, os

def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(len(c1)))

def draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2*radius, y0 + 2*radius], fill=fill)
    draw.ellipse([x1 - 2*radius, y0, x1, y0 + 2*radius], fill=fill)
    draw.ellipse([x0, y1 - 2*radius, x0 + 2*radius, y1], fill=fill)
    draw.ellipse([x1 - 2*radius, y1 - 2*radius, x1, y1], fill=fill)

def make_icon(size=512):
    S = size
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── 背景：深蓝渐变圆角矩形 ──
    bg_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    # 多层渐变模拟
    steps = 60
    for i in range(steps):
        t = i / steps
        c = lerp_color((15, 23, 58), (26, 35, 80), t)
        pad = int(i * (S * 0.02 / steps))
        r = int(S * 0.18 - i * 0.5)
        draw_rounded_rect(bg_draw,
                          [pad, pad, S - pad, S - pad],
                          max(r, int(S*0.12)), c + (255,))
    img = Image.alpha_composite(img, bg_layer)
    draw = ImageDraw.Draw(img)

    # ── 光晕背景（中心橙色辉光）──
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy = S // 2, int(S * 0.46)
    for r in range(int(S * 0.38), 0, -1):
        alpha = int(40 * (1 - r / (S * 0.38)) ** 1.8)
        glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                           fill=(255, 160, 50, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.04))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # ── 锁身（圆角矩形，金色渐变）──
    lw = int(S * 0.38)   # 锁体宽
    lh = int(S * 0.30)   # 锁体高
    lx = (S - lw) // 2
    ly = int(S * 0.46)
    lock_r = int(S * 0.07)

    # 阴影
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    draw_rounded_rect(sd,
                      [lx + 4, ly + 6, lx + lw + 4, ly + lh + 6],
                      lock_r, (0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(S * 0.015))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    # 锁体渐变（逐行）
    for row in range(lh):
        t = row / lh
        c = lerp_color((255, 195, 40), (220, 140, 20), t)
        y_row = ly + row
        if row < lock_r:
            arc_offset = int(lock_r - math.sqrt(max(0, lock_r**2 - (lock_r - row)**2)))
            draw.line([lx + arc_offset, y_row, lx + lw - arc_offset, y_row], fill=c + (255,), width=1)
        elif row > lh - lock_r:
            r2 = lh - row
            arc_offset = int(lock_r - math.sqrt(max(0, lock_r**2 - (lock_r - r2)**2)))
            draw.line([lx + arc_offset, y_row, lx + lw - arc_offset, y_row], fill=c + (255,), width=1)
        else:
            draw.line([lx, y_row, lx + lw, y_row], fill=c + (255,), width=1)

    # 锁体高光
    hl_w = int(lw * 0.55)
    hl_h = int(lh * 0.35)
    hl_x = lx + (lw - hl_w) // 2
    hl_y = ly + int(lh * 0.08)
    for row in range(hl_h):
        t = row / hl_h
        alpha = int(120 * (1 - t))
        draw.line([hl_x, hl_y + row, hl_x + hl_w, hl_y + row],
                   fill=(255, 255, 255, alpha), width=1)

    # ── 钥匙孔 ──
    kx, ky = S // 2, ly + int(lh * 0.42)
    kr = int(S * 0.048)
    # 圆形部分
    draw.ellipse([kx - kr, ky - kr, kx + kr, ky + kr], fill=(30, 20, 0, 255))
    # 下方矩形槽
    slot_w = int(kr * 0.8)
    slot_h = int(kr * 1.4)
    draw.rectangle([kx - slot_w // 2, ky, kx + slot_w // 2, ky + slot_h],
                    fill=(30, 20, 0, 255))

    # ── 锁梁（U形，打开状态偏右上）──
    arc_cx = S // 2 + int(S * 0.09)
    arc_cy = ly - int(S * 0.01)
    arc_outer = int(S * 0.155)
    arc_inner = int(S * 0.095)
    thick = arc_outer - arc_inner

    shackle = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(shackle)

    # 画U形（从180°到360°的半圆 + 两条竖线，打开状态右边抬起）
    # 用多圆环模拟粗线
    for dr in range(-thick // 2, thick // 2 + 1):
        r = arc_inner + thick // 2 + dr
        # 半圆：180° -> 360°（下半部分，即U形顶部）
        sh_draw.arc([arc_cx - r, arc_cy - r, arc_cx + r, arc_cy + r],
                     start=195, end=360,
                     fill=(255, 200, 50, 255), width=max(1, thick // 4))

    # 更干净地画：用多次arc叠加
    for w_extra in range(int(thick * 0.6)):
        r = arc_outer - w_extra
        shackle_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        sl_draw = ImageDraw.Draw(shackle_layer)
        alpha = 255 - int(w_extra * 2)
        sl_draw.arc([arc_cx - r, arc_cy - r, arc_cx + r, arc_cy + r],
                     start=195, end=360,
                     fill=(255, 200, 50, alpha),
                     width=2)
        img = Image.alpha_composite(img, shackle_layer)

    # 右侧竖线（锁梁右臂，插入锁体）
    arm_x = arc_cx + int(arc_inner * math.cos(math.radians(0)))
    arm_top_y = arc_cy
    arm_bot_y = ly + int(lh * 0.15)
    arm_thick = thick
    for i in range(arm_thick):
        x_off = i - arm_thick // 2
        c_t = lerp_color((255, 210, 60), (200, 140, 20), i / arm_thick)
        img_draw = ImageDraw.Draw(img)
        img_draw.line([arm_x + x_off, arm_top_y, arm_x + x_off, arm_bot_y],
                       fill=c_t + (255,), width=1)

    draw = ImageDraw.Draw(img)

    # ── 向下箭头（解压/提取符号）──
    arr_cx = S // 2
    arr_top = int(S * 0.27)
    arr_bot = int(S * 0.41)
    arr_w = int(S * 0.13)
    arr_stem_w = int(S * 0.065)

    # 箭头渐变（青色到白色）
    arrow_img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ar_draw = ImageDraw.Draw(arrow_img)

    # 箭头竖杆
    for row in range(arr_top, arr_bot - int(arr_w * 0.6)):
        t = (row - arr_top) / (arr_bot - arr_top)
        c = lerp_color((100, 230, 255), (200, 245, 255), t)
        ar_draw.line([arr_cx - arr_stem_w // 2, row,
                       arr_cx + arr_stem_w // 2, row],
                      fill=c + (245,), width=1)

    # 箭头头部（三角）
    tri_top = arr_bot - int(arr_w * 0.65)
    tri_bot = arr_bot
    for row in range(tri_top, tri_bot):
        t_tri = (row - tri_top) / max(1, tri_bot - tri_top)
        half_w = int(arr_w * t_tri)
        t_color = (row - arr_top) / (arr_bot - arr_top)
        c = lerp_color((100, 230, 255), (255, 255, 255), t_color)
        if half_w > 0:
            ar_draw.line([arr_cx - half_w, row, arr_cx + half_w, row],
                          fill=c + (240,), width=1)

    # 箭头发光
    arrow_glow = arrow_img.filter(ImageFilter.GaussianBlur(S * 0.012))
    img = Image.alpha_composite(img, arrow_glow)
    img = Image.alpha_composite(img, arrow_img)
    draw = ImageDraw.Draw(img)

    # ── 底部装饰线（文件层叠感）──
    bar_y_start = int(S * 0.835)
    bar_colors = [
        (80, 140, 220, 160),
        (60, 110, 190, 120),
        (40, 85, 160, 80),
    ]
    bar_heights = [int(S * 0.028), int(S * 0.022), int(S * 0.016)]
    bar_pads = [int(S * 0.12), int(S * 0.16), int(S * 0.21)]

    for i, (bc, bh, bp) in enumerate(zip(bar_colors, bar_heights, bar_pads)):
        by = bar_y_start + i * int(S * 0.036)
        draw_rounded_rect(draw,
                          [bp, by, S - bp, by + bh],
                          bh // 2, bc)

    # ── 最终发光边缘 ──
    edge_glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    eg_draw = ImageDraw.Draw(edge_glow)
    for i in range(6):
        alpha = 25 - i * 4
        if alpha > 0:
            r = int(S * 0.18) - i * 2
            draw_rounded_rect(eg_draw,
                              [i * 2, i * 2, S - i * 2, S - i * 2],
                              r, (100, 160, 255, alpha))
    img = Image.alpha_composite(img, edge_glow)

    return img


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("正在生成图标...")
    img_512 = make_icon(512)

    # 保存 PNG
    png_path = os.path.join(out_dir, "app_icon.png")
    img_512.save(png_path, "PNG")
    print(f"PNG 已保存: {png_path}")

    # 生成多尺寸 ICO（Windows 标准尺寸）
    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_imgs = []
    for s in sizes:
        resized = img_512.resize((s, s), Image.LANCZOS)
        ico_imgs.append(resized)

    ico_path = os.path.join(out_dir, "app_icon.ico")
    ico_imgs[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=ico_imgs[1:]
    )
    print(f"ICO 已保存: {ico_path}")
    print("图标生成完成！")


if __name__ == "__main__":
    main()
