# -*- coding: utf-8 -*-
"""
3D 形象运行时：加载 tools/build_3d.py 预渲染好的帧，按朝向 / 动作挑一张贴上去。

运行时不做任何 3D 计算——转身、待机摆动、走路、眨眼全是现成的图，
所以开 3D 形象几乎不增加 CPU。
"""
import json
import os

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QImage, QPixmap

IDLE_YAWS = (0, 20, 90, 180)
WALK_YAWS = (0, 90, 180)
EYE_YAWS = (0, 20, 90)


class Pet3D:
    def __init__(self, folder):
        self.folder = folder
        self.meta = None
        self.ok = False
        self.h = 0
        self.scale = 1.0
        self.frame_w = 0
        self.axis = 0.0
        self.turn = []
        self.turn_yaws = []
        self.idle = {}
        self.walk = {}
        self.overlays = {}
        self.sleep = None
        self.idle_fps = 5.0
        try:
            with open(os.path.join(folder, "meta.json"), "r", encoding="utf-8") as f:
                meta = json.load(f)
            if int(meta.get("version", 0)) >= 3:
                self.meta = meta
                self.ok = True
        except Exception:
            self.ok = False

    # ------------------------------------------------------------ 加载
    def _strip(self, key, h):
        spec = self.meta["anims"][key]
        img = QImage(os.path.join(self.folder, spec["file"]))
        if img.isNull():
            raise IOError(spec["file"])
        fw, fh = self.meta["frame_w"], self.meta["frame_h"]
        out_w = max(1, round(fw * h / fh))
        frames = []
        for i in range(spec["frames"]):
            one = img.copy(i * fw, 0, fw, fh).scaled(
                out_w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            frames.append(QPixmap.fromImage(one))
        return frames

    def load(self, h):
        """按显示高度 h 加载并缩放所有帧；失败时 ok=False，桌宠自动退回 2D。"""
        if self.meta is None:
            self.ok = False
            return False
        try:
            m = self.meta
            self.h = h
            self.scale = h / float(m["frame_h"])
            self.frame_w = max(1, round(m["frame_w"] * self.scale))
            self.axis = m["axis_x"] * self.scale
            self.idle_fps = float(m.get("idle_fps", 5.0))
            self.turn = self._strip("turn", h)
            self.turn_yaws = list(m["anims"]["turn"]["yaws"])
            self.idle = {y: self._strip(f"idle_{y:03d}", h) for y in IDLE_YAWS
                         if f"idle_{y:03d}" in m["anims"]}
            self.walk = {y: self._strip(f"walk_{y:03d}", h) for y in WALK_YAWS
                         if f"walk_{y:03d}" in m["anims"]}
            self.overlays = {}
            for key, spec in m.get("overlays", {}).items():
                img = QImage(os.path.join(self.folder, spec["file"]))
                if img.isNull():
                    continue
                w = max(1, round(img.width() * self.scale))
                hh = max(1, round(img.height() * self.scale))
                pix = QPixmap.fromImage(img.scaled(w, hh, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
                self.overlays[key] = (pix, QPointF(spec["x"] * self.scale, spec["y"] * self.scale))
            sp = m.get("sleep", {})
            img = QImage(os.path.join(self.folder, sp.get("file", "sleep.png")))
            if not img.isNull():
                w = max(1, round(img.width() * self.scale))
                hh = max(1, round(img.height() * self.scale))
                self.sleep = QPixmap.fromImage(img.scaled(w, hh, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                          Qt.TransformationMode.SmoothTransformation))
            self.ok = bool(self.turn and self.idle.get(0))
        except Exception:
            self.ok = False
        return self.ok

    # ------------------------------------------------------------ 查询
    def turn_index(self, yaw_abs):
        best, bi = 1e9, 0
        for i, y in enumerate(self.turn_yaws):
            d = abs(y - yaw_abs)
            if d < best:
                best, bi = d, i
        return bi

    def idle_frames(self, yaw_abs):
        return self.idle.get(yaw_abs) or self.idle.get(0)

    def walk_frames(self, yaw_abs):
        return self.walk.get(yaw_abs)

    def overlay(self, kind, yaw_abs):
        return self.overlays.get(f"{kind}_{yaw_abs}")

    def anchors(self, yaw_abs):
        if not self.meta:
            return {}
        an = self.meta.get("anchors", {})
        key = str(int(yaw_abs))
        if key in an:
            return an[key]
        # 取最近的朝向
        best = min(an.keys(), key=lambda k: abs(int(k) - yaw_abs), default=None)
        return an.get(best, {}) if best is not None else {}

    @property
    def sleep_w(self):
        return self.sleep.width() if self.sleep is not None else 0
