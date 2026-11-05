# -*- coding: utf-8 -*-
"""
把三视图（正面 / 侧面 / 背面）扩展成会转身、会动的 3D 形象，离线预渲染成帧。

只在换形象时运行一次；桌宠运行时只是贴预渲染好的图，几乎不占 CPU。

做法：
  1. 体积：正面轮廓 × 侧面轮廓求视觉外壳（每行一个超椭圆截面），再做照片一致性雕刻，
     呆毛和耳鳍单独建模——得到一个圆润的 Q 版手办体积；
  2. 浮雕：从体积里量出每张原画的平滑深度（正面看过去每个像素离相机多远）；
  3. 转身：把“离当前朝向最近的那张原画”按它自己的深度在 3D 里转过去
     （0~45° 用正面，60~135° 用侧面，150~180° 用背面），线条和五官始终完整，不拼贴；
  4. 灵动：像 Live2D 一样对原画做平滑形变——头发摆、尾巴拍、呆毛弹、耳鳍扇、
     走路迈脚、眨眼 / 眯眼——烘焙进待机、走路循环；
  5. 输出 sprites3d/：每个动作一张横条 PNG + meta.json（锚点、叠加层、帧率）。

依赖（仅构建时）：pip install numpy pillow
运行：python tools/build_3d.py [--preview]
"""
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sprites")
OUT = os.path.join(ROOT, "sprites3d")

H = 340              # 原画高度
SS = 2               # 输出超采样
SUB = 4              # 原画细分（每个像素拆成 SUB×SUB 个采样点再投出去）
CANVAS_W = 360       # 渲染画布宽度（1x），转轴在中线，最后统一裁边
SUPER_P = 2.2
ALPHA_T = 0.5

HAIR_AMP = 4.6       # 头发摆幅（原画像素；迷你尺寸下约 2 像素）
AHOGE_AMP = 12.0     # 呆毛弹动角度
EAR_AMP = 6.0        # 耳鳍扇动角度
TAIL_AMP = 11.0      # 尾巴拍动角度
IDLE_FRAMES = 16     # 待机循环帧数（3.2 秒一圈）
WALK_FRAMES = 12     # 一个步态周期
TURN_YAWS = [0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180]
IDLE_YAWS = [0, 20, 90, 180]
WALK_YAWS = [0, 90, 180]
WALK_CYCLE = 0.48 * H        # 与桌宠 WALK_CYCLE_FACTOR 一致：一个步态周期的位移
WALK_STANCE = 0.62


# ================================================================== 工具
def load_rgba(name):
    im = Image.open(os.path.join(SRC, name)).convert("RGBA")
    return np.asarray(im).astype(np.float32) / 255.0


def to_image(img):
    return Image.fromarray(np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8), "RGBA")


def _lum(c):
    return c[..., 0] * 0.30 + c[..., 1] * 0.59 + c[..., 2] * 0.11


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def runs_1d(mask_row):
    idx = np.flatnonzero(mask_row)
    if idx.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate(([idx[0]], idx[breaks + 1]))
    ends = np.concatenate((idx[breaks], [idx[-1]]))
    return list(zip(starts.tolist(), ends.tolist()))


def box_blur2(a, r, passes=3):
    out = a.astype(np.float32)
    for _ in range(passes):
        for axis in (0, 1):
            c = np.cumsum(out, axis=axis, dtype=np.float32)
            pad = [(0, 0), (0, 0)]
            pad[axis] = (1, 0)
            c = np.pad(c, pad)
            n = out.shape[axis]
            hi = np.clip(np.arange(n) + r + 1, 0, n)
            lo = np.clip(np.arange(n) - r, 0, n)
            num = np.take(c, hi, axis=axis) - np.take(c, lo, axis=axis)
            den = (hi - lo).astype(np.float32)
            out = num / (den[:, None] if axis == 0 else den[None, :])
    return out


def poly_mask(shape, polys):
    im = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    for poly in polys:
        d.polygon([tuple(p) for p in poly], fill=255, outline=255)
    return np.asarray(im) > 127


def resample(img, scale, out_h, out_w, oy, ox):
    """img 缩放 scale 后放到 (out_h, out_w) 画布 (oy, ox) 处（双线性，预乘 alpha）。"""
    h, w = img.shape[:2]
    ys = (np.arange(out_h) - oy) / scale
    xs = (np.arange(out_w) - ox) / scale
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = (ys - y0)[:, None, None]
    fx = (xs - x0)[None, :, None]
    pm = img.copy()
    pm[..., :3] *= pm[..., 3:4]

    def tap(yy, xx):
        valid = ((yy >= 0) & (yy < h))[:, None] & ((xx >= 0) & (xx < w))[None, :]
        return pm[np.clip(yy, 0, h - 1)][:, np.clip(xx, 0, w - 1)] * valid[..., None]

    out = (tap(y0, x0) * (1 - fy) * (1 - fx) + tap(y0, x0 + 1) * (1 - fy) * fx
           + tap(y0 + 1, x0) * fy * (1 - fx) + tap(y0 + 1, x0 + 1) * fy * fx)
    a = out[..., 3:4]
    out[..., :3] = np.where(a > 1e-4, out[..., :3] / np.maximum(a, 1e-4), 0)
    return out


def fit_back(front, back):
    """背面原画没有呆毛，统一高度时被拉大了：搜索缩放 + 平移，让轮廓和正面重合。"""
    fm = front[..., 3] > ALPHA_T
    wb = back.shape[1]

    def score(top, dx):
        s = (H - top) / H
        ox = (front.shape[1] - wb * s) / 2 + dx
        bm = resample(back, s, H, front.shape[1], top, ox)[..., 3] > ALPHA_T
        return (fm & bm).sum() / max(1, (fm | bm).sum()), s, ox

    best = max(((score(t, d)[0], t, d) for t in range(0, 31, 2) for d in range(-14, 15, 2)))
    _, top, dx = best
    best = max(((score(t, d)[0], t, d) for t in (top - 1, top, top + 1) for d in (dx - 1, dx, dx + 1)))
    iou, top, dx = best
    _, s, ox = score(top, dx)
    print(f"[对齐] 背面缩放 {s:.3f} 顶部偏移 {top} 水平 {dx:+d} IoU={iou:.3f}")
    return resample(back, s, H, front.shape[1], top, ox), (s, top, ox)


# ================================================================== 体积
# 单独建模的部件（原画像素坐标）。三视图里它们的位置互相对不上，整体外壳会把它们抹在头上。
PARTS = {
    "ahoge": {
        "F": [[(55, 36), (56, 25), (62, 15), (72, 6), (85, 1), (100, 0), (112, 4), (120, 12),
               (125, 22), (123, 27), (116, 27), (114, 18), (109, 10), (100, 6), (88, 7), (77, 12),
               (69, 20), (65, 28), (63, 37)]],
        "S": [[(24, 37), (25, 24), (31, 13), (41, 5), (55, 0), (67, 3), (75, 10), (79, 18),
               (77, 24), (71, 23), (69, 15), (62, 8), (53, 7), (44, 11), (37, 18), (33, 27), (32, 38)]],
        "dark_only": True,
        "pair": "rank",
    },
    "ear": {
        "F": [[(0, 148), (12, 142), (25, 136), (36, 135), (44, 141), (44, 157), (33, 162),
               (15, 163), (2, 159)],
              [(181, 133), (205, 132), (230, 139), (251, 146), (246, 154), (236, 161),
               (215, 167), (194, 167), (183, 160)]],
        "S": [[(97, 133), (112, 125), (135, 126), (153, 131), (168, 141), (161, 148),
               (150, 153), (135, 160), (114, 161), (101, 157), (95, 146)]],
        "dark_only": False,
        "pair": "all",
    },
}


def _nearest_row(rows, y):
    i = np.searchsorted(rows, y)
    cands = [rows[j] for j in (i - 1, i) if 0 <= j < len(rows)]
    return min(cands, key=lambda r: abs(r - y))


def build_part_hull(pf, ps, nx, nz, pairing, p=2.0):
    occ = np.zeros((H, nx, nz), dtype=bool)
    rows_f = np.flatnonzero(pf.any(axis=1))
    rows_s = np.flatnonzero(ps.any(axis=1))
    if rows_f.size == 0 or rows_s.size == 0:
        return occ
    for y in range(min(rows_f[0], rows_s[0]), max(rows_f[-1], rows_s[-1]) + 1):
        yf = y if pf[y].any() else _nearest_row(rows_f, y)
        ys = y if ps[y].any() else _nearest_row(rows_s, y)
        if abs(yf - y) > 4 or abs(ys - y) > 4:
            continue
        xr, zr = runs_1d(pf[yf]), runs_1d(ps[ys])
        pairs = list(zip(xr, zr)) if pairing == "rank" and len(xr) == len(zr) else \
            [(a, b) for a in xr for b in zr]
        for (x0, x1), (z0, z1) in pairs:
            cx, rx = (x0 + x1) / 2.0, (x1 - x0 + 1) / 2.0 + 0.5
            cz, rz = (z0 + z1) / 2.0, (z1 - z0 + 1) / 2.0 + 0.5
            dx = np.abs((np.arange(x0, x1 + 1) - cx) / rx) ** p
            dz = np.abs((np.arange(z0, z1 + 1) - cz) / rz) ** p
            occ[y, x0:x1 + 1, z0:z1 + 1] |= (dx[:, None] + dz[None, :]) <= 1.0
    return occ


def build_hull(fmask, smask, fext, sext, p=SUPER_P):
    """每行一个整体超椭圆截面（大小由去掉部件后的轮廓决定），再用完整轮廓逐像素雕刻。"""
    nx, nz = fmask.shape[1], smask.shape[1]
    occ = np.zeros((H, nx, nz), dtype=bool)
    for y in range(H):
        xs, zs = np.flatnonzero(fext[y]), np.flatnonzero(sext[y])
        if xs.size == 0 or zs.size == 0:
            continue
        x0, x1, z0, z1 = xs[0], xs[-1], zs[0], zs[-1]
        cx, rx = (x0 + x1) / 2.0, (x1 - x0 + 1) / 2.0 + 0.5
        cz, rz = (z0 + z1) / 2.0, (z1 - z0 + 1) / 2.0 + 0.5
        dx = np.abs((np.arange(x0, x1 + 1) - cx) / rx) ** p
        dz = np.abs((np.arange(z0, z1 + 1) - cz) / rz) ** p
        ell = (dx[:, None] + dz[None, :]) <= 1.0
        ell &= fmask[y, x0:x1 + 1][:, None]
        ell &= smask[y, z0:z1 + 1][None, :]
        occ[y, x0:x1 + 1, z0:z1 + 1] = ell
    return occ


def _inconsistent(c1, c2):
    ok = (c1[..., 3] > ALPHA_T) & (c2[..., 3] > ALPHA_T)
    l1, l2 = _lum(c1), _lum(c2)
    ok &= (l1 > 0.22) & (l2 > 0.22)                 # 深色描边随视角变化，不算矛盾
    diff = np.sqrt(((c1[..., :3] - c2[..., :3]) ** 2 * np.array([0.35, 0.45, 0.2])).sum(-1))
    return ok & ((diff > 0.30) | (np.abs(l1 - l2) > 0.33))


def carve(occ, F, S, B, max_iter=48):
    """照片一致性雕刻：正面 / 背面与侧面同时看得到、颜色却明显矛盾的表面体素挖掉。
    每条视线至少保留体素，0°/90° 的轮廓不变。"""
    occ = occ.copy()
    nz, nx = occ.shape[2], occ.shape[1]
    cnt_f, cnt_s = occ.sum(axis=2), occ.sum(axis=1)
    removed = 0
    for it in range(max_iter):
        any_x, any_z = cnt_f > 0, cnt_s > 0
        ff = np.where(any_x, occ.argmax(axis=2), -1)
        bb = np.where(any_x, nz - 1 - occ[:, :, ::-1].argmax(axis=2), -1)
        ll = np.where(any_z, nx - 1 - occ[:, ::-1, :].argmax(axis=1), -1)
        rr = np.where(any_z, occ.argmax(axis=1), -1)
        kill = np.zeros_like(occ)
        ys, xs = np.nonzero(any_x)
        for zmap, img in ((ff, F), (bb, B)):
            z = zmap[ys, xs]
            c_view = img[ys, xs]
            for sidemap in (ll, rr):
                also = sidemap[ys, z] == xs
                if not also.any():
                    continue
                bad = _inconsistent(c_view[also], S[ys[also], z[also]])
                yy, xx, zz = ys[also][bad], xs[also][bad], z[also][bad]
                keep = (cnt_f[yy, xx] > 2) & (cnt_s[yy, zz] > 2)
                kill[yy[keep], xx[keep], zz[keep]] = True
        n = int(kill.sum())
        if n == 0:
            break
        occ &= ~kill
        cnt_f -= kill.sum(axis=2)
        cnt_s -= kill.sum(axis=1)
        removed += n
    print(f"[雕刻] {it + 1} 轮，挖掉 {removed:,} 个体素")
    return occ


def limit_slope(d, mask, g=2.0, rounds=2):
    """Lipschitz 下包络：相邻像素深度差不超过 g（只压低“悬崖”的高侧）。
    耳鳍这类突然凸出的部位会变成平滑的坡，转身时不会撕开。"""
    big = 1e6
    out = np.where(mask, d, big).astype(np.float32)
    h, w = out.shape
    for _ in range(rounds):
        for j in range(1, w):
            np.minimum(out[:, j], out[:, j - 1] + g, out=out[:, j])
        for j in range(w - 2, -1, -1):
            np.minimum(out[:, j], out[:, j + 1] + g, out=out[:, j])
        for i in range(1, h):
            np.minimum(out[i], out[i - 1] + g, out=out[i])
        for i in range(h - 2, -1, -1):
            np.minimum(out[i], out[i + 1] + g, out=out[i])
    return np.where(mask, out, d).astype(np.float32)


def smooth_relief(depth, valid, alpha, r=3):
    """在轮廓内做归一化模糊：得到平滑浮雕，并把深度外推到半透明的描边像素上。"""
    m = valid.astype(np.float32)
    num = box_blur2(np.where(valid, depth, 0.0), r)
    den = box_blur2(m, r)
    out = np.where(den > 1e-3, num / np.maximum(den, 1e-3), np.nan)
    # 仍然缺的（离体积很远的半透明像素）用整行均值兜底
    if np.isnan(out).any():
        row_mean = np.nanmean(np.where(valid, depth, np.nan), axis=1)
        row_mean = np.where(np.isnan(row_mean), 0.0, row_mean)
        out = np.where(np.isnan(out), row_mean[:, None], out)
    out = limit_slope(out, alpha > 0.02, g=2.0)
    out = box_blur2(out, 1, passes=1) * (alpha > 0.02) + out * (alpha <= 0.02)
    return out.astype(np.float32)


# ================================================================== 形变（Live2D 式）
def _rot_disp(h, w, pivot, angle_deg, weight):
    """绕 pivot 旋转 angle 的位移场 × 权重。"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.radians(angle_deg)
    px, py = pivot
    rx, ry = xx - px, yy - py
    nx_ = rx * math.cos(a) - ry * math.sin(a)
    ny_ = rx * math.sin(a) + ry * math.cos(a)
    return (nx_ - rx) * weight, (ny_ - ry) * weight


def _part_weight(shape, polys, pivot, alpha, ramp=12.0, extra=None, blur=2):
    m = poly_mask(shape, polys) & (alpha > 0.02)
    if extra is not None:
        m &= extra
    w = box_blur2(m.astype(np.float32), blur, passes=2)
    w = np.clip(w * 1.6, 0, 1)
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]].astype(np.float32)
    dist = np.hypot(xx - pivot[0], yy - pivot[1])
    return w * smoothstep(0.0, ramp, dist)


class View:
    """一张原画 + 它的浮雕深度 + 形变部件。"""

    def __init__(self, key, img, depth, axis_col, src_yaw, mirror_turn=False):
        self.key = key
        self.img = img
        self.depth = depth
        self.axis = axis_col
        self.src_yaw = src_yaw
        self.mirror_turn = mirror_turn
        self.h, self.w = img.shape[:2]
        self.parts = []            # (name, pivot, weight, amp_deg, freq, phase)
        self.hair = None           # 头发摆动权重
        self.hair_dir = 1.0
        self.feet = []             # 正/背面：[(weight, phase_offset)]

    def disp(self, t=0.0, walk=None):
        """t：待机循环进度 0..1；walk：步态相位 0..1（None=不走路）。返回 (dx, dy)。"""
        dx = np.zeros((self.h, self.w), np.float32)
        dy = np.zeros((self.h, self.w), np.float32)
        if walk is None:
            for name, pivot, wgt, amp, freq, phase in self.parts:
                ang = amp * math.sin(2 * math.pi * (freq * t) + phase)
                ddx, ddy = _rot_disp(self.h, self.w, pivot, ang, wgt)
                dx += ddx
                dy += ddy
            if self.hair is not None:
                yy = np.arange(self.h, dtype=np.float32)[:, None]
                ph = 2 * math.pi * t - 1.6 * (yy - 180) / 100.0
                dx += self.hair * HAIR_AMP * np.sin(ph) * self.hair_dir
        else:
            # 走路：尾巴 / 呆毛随步子轻拍，头发一步一颠
            for name, pivot, wgt, amp, freq, phase in self.parts:
                ang = 0.8 * amp * math.sin(2 * math.pi * 2 * walk + phase)
                ddx, ddy = _rot_disp(self.h, self.w, pivot, ang, wgt)
                dx += ddx
                dy += ddy
            if self.hair is not None:
                yy = np.arange(self.h, dtype=np.float32)[:, None]
                dx += self.hair * 1.8 * math.sin(2 * math.pi * walk - 0.6) * self.hair_dir
                dy += self.hair * (-1.2) * abs(math.sin(2 * math.pi * walk + 0.4)) * (yy > 0)
            for wgt, off in self.feet:
                q = (walk + off) % 1.0
                if q >= WALK_STANCE:
                    s = (q - WALK_STANCE) / (1 - WALK_STANCE)
                    dy -= wgt * 0.026 * H * math.sin(math.pi * s)
        return dx, dy


# ================================================================== 眼睛（眨眼 / 眯眼笑）
# 每只眼：沿睫毛上缘和下眼睑描的多边形（避开刘海），闭眼线的左右端点，外眼角在哪边
EYES = {
    "F": [
        {"poly": [(65, 148), (69, 141), (79, 136.5), (92, 136.5), (101, 140), (104, 146), (104, 157),
                  (100, 166), (91, 171), (78, 169.5), (70, 162)],
         "line": ((68.5, 155.5), (102.5, 154.0)), "outer": -1},
        {"poly": [(133, 147), (137, 140), (148, 136), (161, 136), (171, 140.5), (177, 148), (175, 158),
                  (167, 168), (152, 172), (139, 169), (134, 160)],
         "line": ((135.5, 154.0), (174.5, 155.5)), "outer": 1},
    ],
    "S": [
        {"poly": [(37, 134), (45, 130), (58, 130.5), (64.5, 137), (62, 151), (57.5, 165), (48, 169.5),
                  (41, 165), (38, 150)],
         "line": ((39.5, 152.5), (62.5, 150.0)), "outer": 1},
    ],
}


def _inpaint_skin(rgb, region, iters=220):
    """区域内用周围“像皮肤的”像素做扩散填充，腮红渐变也能自然接上。"""
    lum = rgb[..., 0] * 0.3 + rgb[..., 1] * 0.59 + rgb[..., 2] * 0.11
    src = (~region) & (lum > 0.78) & (rgb[..., 0] > rgb[..., 2])      # 暖色、够亮：皮肤 / 腮红
    known = src.astype(np.float32)
    val = rgb * known[..., None]
    if src.any():
        med = np.median(rgb[src], axis=0)
    else:
        med = np.array([0.98, 0.9, 0.86], np.float32)
    cur = np.where(region[..., None], med, val)
    w = np.where(region, 1.0, known)
    for _ in range(iters):
        acc = np.zeros_like(cur)
        cnt = np.zeros(region.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc += np.roll(cur * w[..., None], (dy, dx), axis=(0, 1))
            cnt += np.roll(w, (dy, dx), axis=(0, 1))
        upd = acc / np.maximum(cnt, 1e-6)[..., None]
        cur = np.where(region[..., None] & (cnt[..., None] > 0), upd, cur)
    return cur


def paint_eyes(img, key, kind):
    """把眼睛改画成闭眼（closed：下弯）或眯眼笑（happy：上弯），返回新图。"""
    K = 4
    h, w = img.shape[:2]
    rgb = img[..., :3].copy()
    out = img.copy()
    for eye in EYES[key]:
        # 软边遮罩（4x 画再缩）
        m = Image.new("L", (w * K, h * K), 0)
        ImageDraw.Draw(m).polygon([(x * K, y * K) for x, y in eye["poly"]], fill=255)
        soft = np.asarray(m.resize((w, h), Image.LANCZOS)).astype(np.float32) / 255.0
        hard = soft > 0.02
        grown = box_blur2(hard.astype(np.float32), 1, 1) > 0.01
        fill = _inpaint_skin(rgb, grown)
        a = np.clip(soft * 1.25, 0, 1)[..., None]
        out[..., :3] = out[..., :3] * (1 - a) + fill * a
        rgb = out[..., :3].copy()

    # 眼睑线：中间粗、两头细，外眼角带两根小睫毛
    over = Image.new("RGBA", (w * K, h * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    line_col = (52, 42, 88, 255)
    lash_col = (96, 52, 70, 255)
    for eye in EYES[key]:
        (x0, y0), (x1, y1) = eye["line"]
        n = 32
        pts = []
        for i in range(n + 1):
            f = i / n
            bend = math.sin(math.pi * f)
            x = x0 + (x1 - x0) * f
            y = y0 + (y1 - y0) * f + (3.4 * bend if kind == "closed" else -4.6 * bend + 1.8)
            pts.append((x, y, 0.9 + 2.0 * bend ** 0.7))
        for (xa, ya, wa), (xb, yb, wb) in zip(pts[:-1], pts[1:]):
            wd = (wa + wb) / 2
            d.line([(xa * K, ya * K), (xb * K, yb * K)], fill=line_col, width=max(1, int(wd * K)))
            r = wd * K / 2
            d.ellipse([xb * K - r, yb * K - r, xb * K + r, yb * K + r], fill=line_col)
        ex, ey, _ = pts[0] if eye["outer"] < 0 else pts[-1]
        sg = eye["outer"]
        if kind == "closed":
            for k, (lx, ly) in enumerate(((2.6, 2.6), (1.2, 3.4))):
                d.line([(ex - sg * 1.5 * k) * K, (ey + 0.5) * K, (ex + sg * lx - sg * 1.5 * k) * K,
                        (ey + ly) * K], fill=lash_col, width=int(1.2 * K))
        else:
            d.line([ex * K, ey * K, (ex + sg * 3.0) * K, (ey - 1.4) * K], fill=lash_col, width=int(1.3 * K))
    over = np.asarray(over.resize((w, h), Image.LANCZOS)).astype(np.float32) / 255.0
    oa = over[..., 3:4]
    out[..., :3] = over[..., :3] * oa + out[..., :3] * (1 - oa)
    out[..., 3] = img[..., 3]
    return out


# ================================================================== 渲染（浮雕旋转 + 形变，正投影）
def _up(a, sub, resample_mode=Image.BILINEAR):
    h, w = a.shape
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((w * sub, h * sub), resample_mode))


def warp(view, yaw, img=None, disp=None, canvas_w=CANVAS_W, hide=None):
    """把 view 的原画按浮雕深度转到 yaw，返回 SS 倍分辨率的预乘 RGBA 和深度。"""
    img = view.img if img is None else img
    h, w = view.h, view.w
    delta = yaw - view.src_yaw
    if view.mirror_turn:
        delta = -delta
    th = math.radians(delta)
    ct, st = math.cos(th), math.sin(th)
    alpha = img[..., 3]
    if hide is not None:
        alpha = alpha * (1.0 - hide)
    pm = img[..., :3] * alpha[..., None]
    A = _up(alpha, SUB)
    keep = A > 0.015
    cols = [_up(pm[..., c], SUB)[keep] for c in range(3)]
    A = A[keep]
    D = _up(view.depth, SUB)[keep]
    gy, gx = np.nonzero(keep)
    sx = (gx + 0.5) / SUB - 0.5
    sy = (gy + 0.5) / SUB - 0.5
    if disp is not None:
        dx, dy = disp
        sx = sx + _up(dx, SUB)[keep]
        sy = sy + _up(dy, SUB)[keep]
    a = sx - view.axis
    u = a * ct - D * st
    dep = a * st + D * ct
    U = np.floor((u + canvas_w / 2.0 + 0.5) * SS).astype(np.int64)
    V = np.floor((sy + 0.5) * SS).astype(np.int64)
    W, HH = canvas_w * SS, H * SS
    ok = (U >= 0) & (U < W) & (V >= 0) & (V < HH)
    pid = V[ok] * W + U[ok]
    dep = dep[ok]
    order = np.lexsort((-dep, pid))
    pid, dep = pid[order], dep[order]
    first = np.ones(len(pid), bool)
    first[1:] = pid[1:] != pid[:-1]
    sel = np.flatnonzero(ok)[order][first]
    pid = pid[first]
    out = np.zeros((HH * W, 4), np.float32)
    for c in range(3):
        out[pid, c] = cols[c][sel]
    out[pid, 3] = A[sel]
    zb = np.full(HH * W, -1e9, np.float32)
    zb[pid] = dep[first]
    out = fill_gaps(out.reshape(HH, W, 4))
    return out, zb.reshape(HH, W)


def fill_gaps(pm, max_gap=6):
    """水平方向的小缝（拉伸处采样不够密）用左右两侧插值补上。"""
    a = pm[..., 3] > 0.01
    HH, W = a.shape
    idx = np.arange(W)[None, :].repeat(HH, 0)
    left = np.where(a, idx, -1)
    left = np.maximum.accumulate(left, axis=1)
    right = np.where(a, idx, W)
    right = np.minimum.accumulate(right[:, ::-1], axis=1)[:, ::-1]
    gap = ~a & (left >= 0) & (right < W) & ((right - left) <= max_gap)
    if not gap.any():
        return pm
    yy, xx = np.nonzero(gap)
    l, r = left[yy, xx], right[yy, xx]
    f = ((xx - l) / np.maximum(r - l, 1))[:, None]
    pm = pm.copy()
    pm[yy, xx] = pm[yy, l] * (1 - f) + pm[yy, r] * f
    return pm


def composite(layers):
    """预乘图层从后往前叠。"""
    out = np.zeros_like(layers[0])
    for lay in layers:
        out = lay + out * (1.0 - lay[..., 3:4])
    return out


def finish(pm):
    """SS 下采样 → straight RGBA（1x）。"""
    h, w = pm.shape[0] // SS, pm.shape[1] // SS
    p = pm.reshape(h, SS, w, SS, 4).mean(axis=(1, 3))
    a = p[..., 3:4]
    p[..., :3] = np.where(a > 1e-4, p[..., :3] / np.maximum(a, 1e-4), 0)
    return p


# ================================================================== 模型
class Model:
    def __init__(self):
        t0 = time.time()
        F = load_rgba("正面.png")
        S = load_rgba("侧面.png")
        B, self.back_tf = fit_back(F, load_rgba("背面.png"))
        fm, sm = F[..., 3] > ALPHA_T, S[..., 3] > ALPHA_T
        nx, nz = fm.shape[1], sm.shape[1]
        feet_f = np.flatnonzero(fm[H - 12:].any(axis=0))
        feet_s = np.flatnonzero(sm[H - 12:].any(axis=0))
        self.ax = float(round((feet_f.min() + feet_f.max()) / 2.0))
        self.az = float(round((feet_s.min() + feet_s.max()) / 2.0))
        print(f"[体积] 转轴 正面列 {self.ax:.0f} 侧面列 {self.az:.0f}")

        part_f, part_s = {}, {}
        for name, spec in PARTS.items():
            pf = poly_mask(fm.shape, spec["F"]) & fm
            ps = poly_mask(sm.shape, spec["S"]) & sm
            if spec.get("dark_only"):
                pf &= _lum(F) < 0.62
                ps &= _lum(S) < 0.62
            part_f[name], part_s[name] = pf, ps
        fext = fm & ~np.any(list(part_f.values()), axis=0)
        sext = sm & ~np.any(list(part_s.values()), axis=0)
        occ = carve(build_hull(fm, sm, fext, sext), F, S, B)
        for name in PARTS:
            occ |= build_part_hull(part_f[name], part_s[name], nx, nz, PARTS[name]["pair"])
        print(f"[体积] 体素 {int(occ.sum()):,}")

        any_x, any_z = occ.any(axis=2), occ.any(axis=1)
        first_iz = occ.argmax(axis=2)
        last_iz = nz - 1 - occ[:, :, ::-1].argmax(axis=2)
        last_ix = nx - 1 - occ[:, ::-1, :].argmax(axis=1)
        dF = smooth_relief(self.az - first_iz, any_x, F[..., 3])
        dB = smooth_relief(last_iz - self.az, any_x, B[..., 3])
        dS = smooth_relief(last_ix - self.ax, any_z, S[..., 3])

        self.views = {
            "F": View("F", F, dF, self.ax, 0.0),
            "S": View("S", S, dS, self.az, 90.0),
            "B": View("B", B, dB, self.ax, 180.0, mirror_turn=True),
        }
        self._setup_parts()
        self.eyes = {
            ("F", "closed"): paint_eyes(F, "F", "closed"),
            ("F", "happy"): paint_eyes(F, "F", "happy"),
            ("S", "closed"): paint_eyes(S, "S", "closed"),
            ("S", "happy"): paint_eyes(S, "S", "happy"),
        }
        print(f"[模型] 完成 {time.time() - t0:.1f}s")

    def _setup_parts(self):
        F, S, B = (self.views[k] for k in "FSB")
        s, top, ox = self.back_tf

        def bpoly(pts):
            return [(x * s + ox, y * s + top) for x, y in pts]

        def bpt(p):
            return (p[0] * s + ox, p[1] * s + top)

        # ---- 正面
        fa = F.img[..., 3]
        dark = _lum(F.img) < 0.62
        F.parts = [
            ("ahoge", (118, 27), _part_weight(fa.shape, PARTS["ahoge"]["F"], (118, 27), fa, 14, dark),
             AHOGE_AMP, 2, 0.9),
            ("ear_l", (44, 150), _part_weight(fa.shape, [PARTS["ear"]["F"][0]], (44, 150), fa, 10),
             EAR_AMP, 1, 2.0),
            ("ear_r", (183, 150), _part_weight(fa.shape, [PARTS["ear"]["F"][1]], (183, 150), fa, 10),
             -EAR_AMP, 1, 2.0),
            ("tail", (207, 244), _part_weight(fa.shape, [TAIL_F], (207, 244), fa, 12), TAIL_AMP * 0.8, 2, 0.0),
        ]
        yy, xx = np.mgrid[0:F.h, 0:F.w].astype(np.float32)
        side = np.clip((56 - xx) / 10, 0, 1) + np.clip((xx - 200) / 10, 0, 1)
        tail_w = poly_mask(fa.shape, [TAIL_F]).astype(np.float32)
        F.hair = (fa > 0.02) * smoothstep(186, 282, yy) * np.clip(side, 0, 1) * (1 - box_blur2(tail_w, 2, 2))
        F.feet = [(self._feet_weight(F.img, xx < self.ax), 0.0), (self._feet_weight(F.img, xx >= self.ax), 0.5)]

        # ---- 侧面
        sa = S.img[..., 3]
        sdark = _lum(S.img) < 0.62
        S.parts = [
            ("ahoge", (73, 22), _part_weight(sa.shape, PARTS["ahoge"]["S"], (73, 22), sa, 14, sdark),
             AHOGE_AMP, 2, 0.9),
            ("ear", (100, 146), _part_weight(sa.shape, PARTS["ear"]["S"], (100, 146), sa, 10),
             EAR_AMP * 0.8, 1, 2.0),
            ("tail", (137, 272), _part_weight(sa.shape, [TAIL_S], (137, 272), sa, 12), -TAIL_AMP, 2, 0.0),
        ]
        yy, xx = np.mgrid[0:S.h, 0:S.w].astype(np.float32)
        tail_w = poly_mask(sa.shape, [TAIL_S]).astype(np.float32)
        S.hair = (sa > 0.02) * smoothstep(176, 284, yy) * np.clip((xx - 112) / 16, 0, 1) * (1 - box_blur2(tail_w, 2, 2))
        S.hair_dir = 1.0

        # ---- 背面（对齐后的坐标）
        ba = B.img[..., 3]
        B.parts = [
            ("tail", bpt((170, 250)), _part_weight(ba.shape, [bpoly(TAIL_B)], bpt((170, 250)), ba, 12),
             -TAIL_AMP * 0.8, 2, 0.0),
        ]
        yy, xx = np.mgrid[0:B.h, 0:B.w].astype(np.float32)
        tail_w = poly_mask(ba.shape, [bpoly(TAIL_B)]).astype(np.float32)
        B.hair = ((ba > 0.02) * smoothstep(150, 272, yy) * (1 - smoothstep(284, 300, yy))
                  * (1 - box_blur2(tail_w, 2, 2)))
        B.feet = [(self._feet_weight(B.img, xx < self.ax), 0.5), (self._feet_weight(B.img, xx >= self.ax), 0.0)]

    @staticmethod
    def _feet_weight(img, side_mask):
        yy = np.arange(img.shape[0], dtype=np.float32)[:, None]
        return (img[..., 3] > 0.01) * smoothstep(309, 316, yy) * side_mask

    # -------------------------------------------------------------- 帧
    def view_for(self, yaw):
        if yaw <= 45:
            return self.views["F"]
        if yaw <= 135:
            return self.views["S"]
        return self.views["B"]

    def frame(self, yaw, t=0.0, walk=None, eyes=None, still=False):
        v = self.view_for(yaw)
        img = v.img
        if eyes and (v.key, eyes) in self.eyes:
            img = self.eyes[(v.key, eyes)]
        disp = None if still else v.disp(t, walk)
        if walk is not None and v.key == "S":
            return finish(self._side_walk(v, img, disp, walk))
        pm, _ = warp(v, yaw, img=img, disp=disp)
        return finish(pm)

    def _side_walk(self, v, img, disp, walk):
        """侧面走路：把鞋从原画里抠出来，远脚（压暗）和近脚分别迈步，裙摆盖住袜口。"""
        foot = poly_mask(img.shape, [FOOT_S]) & (img[..., 3] > 0.01)
        body, _ = warp(v, 90, img=img, disp=disp, hide=foot.astype(np.float32))
        layers = []
        stride = WALK_STANCE * WALK_CYCLE
        for k, (off, dark) in enumerate(((0.5, True), (0.0, False))):
            q = (walk + off) % 1.0
            if q < WALK_STANCE:
                tt = q / WALK_STANCE
                shift = stride * (-0.5 + tt)
                lift = 0.0
                toe = 6.0 * max(0.0, (tt - 0.72) / 0.28)
            else:
                tt = (q - WALK_STANCE) / (1 - WALK_STANCE)
                ease = tt * tt * (3 - 2 * tt)
                shift = stride * (0.5 - ease)
                lift = -0.03 * H * math.sin(math.pi * tt)
                toe = 7.0 * math.sin(math.pi * tt)
            fimg = img.copy()
            fimg[..., 3] = img[..., 3] * foot
            if dark:
                fimg[..., :3] = fimg[..., :3] * 0.78 + np.array([18, 22, 46]) / 255.0 * 0.22
            fx, fy = _rot_disp(img.shape[0], img.shape[1], (80, 333), toe, 1.0)
            pm, _ = warp(v, 90, img=fimg, disp=(fx + shift, fy + lift - k * 1.0))
            layers.append(pm)
        return composite(layers + [body])


TAIL_F = [(204, 240), (214, 236), (222, 245), (228, 262), (244, 272), (240, 280), (225, 290),
          (205, 292), (200, 280), (202, 262)]
TAIL_S = [(134, 262), (150, 266), (170, 272), (190, 274), (200, 278), (196, 288), (180, 296),
          (160, 301), (140, 302), (124, 298), (120, 284)]
TAIL_B = [(160, 245), (170, 236), (180, 245), (186, 265), (205, 268), (232, 272), (236, 278),
          (215, 290), (195, 300), (175, 302), (160, 290), (158, 270)]
FOOT_S = [(64, 314), (99, 314), (99, 321), (102, 324), (102, 334), (98, 340), (59, 340),
          (55, 337), (55, 331), (63, 323), (63, 318)]


# ================================================================== 锚点（可爱/性感装饰跟着 3D 头走）
ANCHORS_SRC = {
    "F": {"heart": (127, 75), "sparkles": [(76, 102), (178, 116)], "cheeks": [(92, 176), (152, 176)],
          "mouth": (119, 181)},
    "S": {"heart": (73, 75), "sparkles": [(40, 109), (93, 102)], "cheeks": [(56, 170)],
          "mouth": (31, 176)},
    "B": {"heart": (127, 75), "sparkles": [(76, 109), (178, 129)], "cheeks": [], "mouth": None},
}


def project_anchor(model, yaw, pt):
    v = model.view_for(yaw)
    x, y = pt
    d = float(v.depth[int(min(max(y, 0), v.h - 1)), int(min(max(x, 0), v.w - 1))])
    delta = yaw - v.src_yaw
    if v.mirror_turn:
        delta = -delta
    th = math.radians(delta)
    a = x - v.axis
    u = a * math.cos(th) - d * math.sin(th)
    return u + CANVAS_W / 2.0, float(y)


# ================================================================== 主流程
def build(out_dir, preview=False):
    os.makedirs(out_dir, exist_ok=True)
    m = Model()
    t0 = time.time()
    anims = {}   # name -> list of (yaw, [frames])

    def add(name, yaw, frames):
        anims.setdefault(name, []).append((yaw, frames))

    add("turn", None, [m.frame(y, still=True) for y in TURN_YAWS])
    print(f"[帧] 转身 {len(TURN_YAWS)} 帧")
    for yaw in IDLE_YAWS:
        add("idle", yaw, [m.frame(yaw, t=i / IDLE_FRAMES) for i in range(IDLE_FRAMES)])
        print(f"[帧] 待机 yaw={yaw}")
    for yaw in WALK_YAWS:
        add("walk", yaw, [m.frame(yaw, walk=i / WALK_FRAMES) for i in range(WALK_FRAMES)])
        print(f"[帧] 走路 yaw={yaw}")
    overlays = {}
    for kind in ("closed", "happy"):
        for yaw in (0, 20, 90):
            base = m.frame(yaw, still=True)
            alt = m.frame(yaw, eyes=kind, still=True)
            diff = np.abs(alt - base).max(axis=2) > 0.02
            ys, xs = np.nonzero(diff)
            if ys.size == 0:
                continue
            y0, y1 = max(0, ys.min() - 2), min(H, ys.max() + 3)
            x0, x1 = max(0, xs.min() - 2), min(CANVAS_W, xs.max() + 3)
            overlays[f"{kind}_{yaw}"] = (alt[y0:y1, x0:x1], (x0, y0))
    # 睡觉：侧面闭眼，顺时针转 90°，肚皮朝天
    sleep = m.frame(90, eyes="closed", still=True)
    sleep_img = to_image(sleep).rotate(-90, expand=True, resample=Image.BICUBIC)
    print(f"[帧] 渲染耗时 {time.time() - t0:.1f}s")

    # ---- 统一裁边（所有帧共用同一个框，转轴位置不变）
    all_frames = [f for lst in anims.values() for _, fr in lst for f in fr]
    alpha_union = np.zeros((H, CANVAS_W), bool)
    for f in all_frames:
        alpha_union |= f[..., 3] > 0.01
    xs = np.flatnonzero(alpha_union.any(axis=0))
    pad = 6
    cx0, cx1 = max(0, xs.min() - pad), min(CANVAS_W, xs.max() + 1 + pad)
    fw = cx1 - cx0
    axis_x = CANVAS_W / 2.0 - cx0
    meta = {
        "version": 3,
        "frame_w": int(fw),
        "frame_h": H,
        "axis_x": axis_x,
        "anims": {},
        "overlays": {},
        "anchors": {},
        "sleep": {"file": "sleep.png"},
        "idle_fps": 5.0,
    }
    for name, lst in anims.items():
        for yaw, frames in lst:
            fname = f"{name}.png" if yaw is None else f"{name}_{yaw:03d}.png"
            strip = Image.new("RGBA", (fw * len(frames), H), (0, 0, 0, 0))
            for i, f in enumerate(frames):
                strip.paste(to_image(f[:, cx0:cx1]), (i * fw, 0))
            strip.save(os.path.join(out_dir, fname), optimize=True)
            key = name if yaw is None else f"{name}_{yaw:03d}"
            meta["anims"][key] = {"file": fname, "frames": len(frames),
                                  "yaws": TURN_YAWS if yaw is None else [yaw]}
    for key, (img, (x0, y0)) in overlays.items():
        fname = f"eyes_{key}.png"
        to_image(img).save(os.path.join(out_dir, fname), optimize=True)
        meta["overlays"][key] = {"file": fname, "x": int(x0 - cx0), "y": int(y0)}
    sleep_img = sleep_img.crop(sleep_img.getbbox())
    sleep_img.save(os.path.join(out_dir, "sleep.png"), optimize=True)
    meta["sleep"].update({"w": sleep_img.width, "h": sleep_img.height})
    for yaw in sorted(set(TURN_YAWS + IDLE_YAWS)):
        src = ANCHORS_SRC[m.view_for(yaw).key]
        an = {}
        for k, val in src.items():
            if val is None:
                continue
            if isinstance(val, list):
                an[k] = [[(project_anchor(m, yaw, p)[0] - cx0) / fw, p[1] / H] for p in val]
            else:
                ux, uy = project_anchor(m, yaw, val)
                an[k] = [(ux - cx0) / fw, uy / H]
        meta["anchors"][str(yaw)] = an
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"[输出] {out_dir}  帧宽 {fw}  转轴 {axis_x:.1f}")

    if preview:
        rows = [[f for f in anims["turn"][0][1]]]
        for _, fr in anims["idle"]:
            rows.append(fr[::2])
        for _, fr in anims["walk"]:
            rows.append(fr)
        cols = max(len(r) for r in rows)
        sheet = Image.new("RGBA", (fw * cols, H * len(rows)), (236, 240, 248, 255))
        for r, row in enumerate(rows):
            for c, f in enumerate(row):
                sheet.alpha_composite(to_image(f[:, cx0:cx1]), (c * fw, r * H))
        sheet.save(os.path.join(out_dir, "_preview.png"))
        print("[预览]", os.path.join(out_dir, "_preview.png"))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build(args[0] if args else OUT, preview="--preview" in sys.argv)
