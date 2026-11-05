# -*- coding: utf-8 -*-
"""
小游戏和小玩具：接小鱼干、丢球、捉迷藏、吹泡泡。

每个掉落物 / 泡泡 / 球都是一个几十像素的小透明窗口：移动窗口不用重画内容，
比铺一层全屏覆盖窗口省得多；游戏结束就全部关掉，平时不占任何资源。
"""
import math
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import (QPainter, QColor, QFont, QPixmap, QRadialGradient, QPen,
                           QPainterPath, QCursor, QLinearGradient)
from PySide6.QtWidgets import QWidget, QApplication

TICK_S = 0.02
EMOJI_FONT = "Segoe UI Emoji"
UI_FONT = "Microsoft YaHei UI"


# ======================================================================== 小窗口
class SpriteWindow(QWidget):
    """一张小图的透明置顶窗口。clickthrough=True 时鼠标直接穿过它。"""

    def __init__(self, pix, clickthrough=True, on_press=None, pad=6):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        if clickthrough:
            flags |= Qt.WindowType.WindowTransparentForInput
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.pix = pix
        self.scale = 1.0
        self.alpha = 1.0
        self.angle = 0.0
        self.on_press = on_press
        side = int(max(pix.width(), pix.height()) * 1.45) + pad
        self.setFixedSize(side, side)

    def place(self, cx, cy):
        self.move(int(cx - self.width() / 2), int(cy - self.height() / 2))

    def center(self):
        return self.x() + self.width() / 2.0, self.y() + self.height() / 2.0

    def set_look(self, scale=None, alpha=None, angle=None):
        changed = False
        for name, val in (("scale", scale), ("alpha", alpha), ("angle", angle)):
            if val is not None and abs(getattr(self, name) - val) > 1e-3:
                setattr(self, name, val)
                changed = True
        if changed:
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(max(0.0, min(1.0, self.alpha)))
        p.translate(self.width() / 2.0, self.height() / 2.0)
        if self.angle:
            p.rotate(self.angle)
        if self.scale != 1.0:
            p.scale(self.scale, self.scale)
        p.drawPixmap(QPointF(-self.pix.width() / 2.0, -self.pix.height() / 2.0), self.pix)

    def mousePressEvent(self, e):
        if self.on_press is not None:
            self.on_press(self, e)


def emoji_pix(text, size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont(EMOJI_FONT)
    f.setPixelSize(int(size * 0.78))
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return pm


def busy_cloud_pix(w=128, h=58):
    """DeepSeek 名梗：服务器繁忙，请稍后再试。"""
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    body = QPainterPath()
    body.addRoundedRect(QRectF(3, 20, w - 6, h - 25), 15, 15)
    for cx, cy, r in ((30, 22, 13), (56, 16, 16), (84, 18, 14), (104, 24, 11)):
        bump = QPainterPath()
        bump.addEllipse(QPointF(cx, cy), r, r)
        body = body.united(bump)                       # 真正合并成一朵云，里面没有交叉线
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0.0, QColor(214, 219, 230, 245))
    g.setColorAt(1.0, QColor(176, 183, 199, 245))
    p.setPen(QPen(QColor(92, 101, 122, 235), 1.8))
    p.setBrush(g)
    p.drawPath(body)
    f = QFont(UI_FONT)
    f.setPixelSize(14)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(64, 72, 94))
    p.drawText(QRectF(0, 22, w, h - 27), Qt.AlignmentFlag.AlignCenter, "服务器繁忙")
    p.end()
    return pm


def _heart_path(cx, cy, r):
    path = QPainterPath()
    path.moveTo(cx, cy - r * 0.35)
    path.cubicTo(cx - r * 0.55, cy - r * 0.95, cx - r * 1.05, cy - r * 0.25, cx, cy + r * 0.75)
    path.cubicTo(cx + r * 1.05, cy - r * 0.25, cx + r * 0.55, cy - r * 0.95, cx, cy - r * 0.35)
    return path


def text_pix(text, color, px=18, bold=True):
    f = QFont(UI_FONT)
    f.setPixelSize(px)
    f.setBold(bold)
    from PySide6.QtGui import QFontMetrics
    fm = QFontMetrics(f)
    w, h = fm.horizontalAdvance(text) + 8, fm.height() + 4
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 230))
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        p.drawText(QRectF(dx, dy, w, h), Qt.AlignmentFlag.AlignCenter, text)
    p.setPen(color)
    p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return pm


class FloatText:
    """接到东西时冒出来的 +2 之类，飘一下就消失。"""

    def __init__(self, text, color, x, y):
        self.win = SpriteWindow(text_pix(text, color))
        self.x, self.y = x, y
        self.born = time.time()
        self.win.place(x, y)
        self.win.show()

    def tick(self):
        age = time.time() - self.born
        if age > 0.8:
            self.win.close()
            return False
        self.win.place(self.x, self.y - age * 60)
        self.win.set_look(alpha=1.0 - age / 0.8)
        return True


class Hud(QWidget):
    def __init__(self):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                 | Qt.WindowType.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(300, 44)
        self.state = None

    def set_state(self, score, lives, seconds):
        st = (score, lives, seconds)
        if st != self.state:
            self.state = st
            self.update()

    def paintEvent(self, _):
        if self.state is None:
            return
        score, lives, seconds = self.state
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 36, 64, 190))
        p.drawRoundedRect(QRectF(2, 2, self.width() - 4, self.height() - 4), 14, 14)
        f = QFont(UI_FONT)
        f.setPixelSize(17)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        h = self.height()
        p.drawText(QRectF(14, 0, 110, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   f"🐟 {score}")
        # 三颗命：手画红心 / 灰心（字体里的 ♡ 在部分系统上会变成乱码）
        for i in range(3):
            path = _heart_path(132 + i * 24, h / 2 + 1, 9.5)
            if i < lives:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 82, 120))
            else:
                p.setPen(QPen(QColor(255, 255, 255, 120), 1.4))
                p.setBrush(QColor(255, 255, 255, 30))
            p.drawPath(path)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(196, 0, 94, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   f"⏱ {seconds}s")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _reward(pet, coins=0, exp=0, counter=None, affection=0):
    st = pet.pet_state
    if coins:
        st["fish_coins"] = min(getattr(pet, "COIN_CAP", 99), int(st.get("fish_coins", 0)) + coins)
    if affection:
        st["affection"] = min(100, int(st.get("affection", 0)) + affection)
    if counter:
        pet._bump_counter(counter)
    if exp:
        pet.add_exp(exp)
    pet._update_status_label()
    pet._save_pet_state()


def _happy(pet, seconds=1.6, hearts=2):
    now = time.time()
    pet._happy_until = now + seconds
    for i in range(hearts):
        pet._hearts.append((now + i * 0.15, random.uniform(-0.12, 0.12), random.uniform(-14, 14)))


class _PetDriver:
    """游戏里替桌宠走路：设置 target / 朝向 / 步态相位，3D 帧会自动切成走路。"""

    def __init__(self, pet):
        self.pet = pet
        self.vx = 0.0
        self.vy = 0.0

    def floor_top(self):
        geo = (self.pet.screen() or QApplication.primaryScreen()).availableGeometry()
        return geo.bottom() - self.pet.height()

    def cx(self):
        return self.pet.x() + self.pet.width() / 2.0

    def run_to(self, tx, max_speed, accel=5200.0, y=None):
        """沿水平方向朝 tx 跑（带加减速），返回剩余距离。"""
        pet = self.pet
        dx = tx - self.cx()
        want = _clamp(dx * 9.0, -max_speed, max_speed)
        if abs(dx) < 3:
            want = 0.0
        dv = _clamp(want - self.vx, -accel * TICK_S, accel * TICK_S)
        self.vx += dv
        step = self.vx * TICK_S
        ny = pet.y()
        if y is not None:
            if pet.y() < y - 1:
                # 悬在半空（被拖到别处放下）：先自由落体落到地上
                self.vy += 2400.0 * TICK_S
                ny = min(y, pet.y() + self.vy * TICK_S)
                if ny >= y:
                    self.vy = 0.0
                    pet._squash = max(pet._squash, 0.5)
            else:
                ny, self.vy = y, 0.0
        if abs(self.vx) > 18:
            pet.move(int(round(pet.x() + step)), int(ny))
            pet.target = (tx, ny + pet.height() / 2)
            pet.dir = "left" if self.vx < 0 else "right"
            cycle = max(46.0, 0.48 * pet.cur_h)
            pet._walk_phase = (pet._walk_phase + abs(step) / cycle) % 1.0
        else:
            self.vx = 0.0 if abs(dx) < 3 else self.vx
            if y is not None and pet.y() != int(ny):
                pet.move(pet.x(), int(ny))
            pet.target = None
        return dx

    def facing_yaw(self):
        if self.pet.target is None:
            return None
        return 90.0 if self.pet.dir == "left" else -90.0


# ======================================================================== 接小鱼干
class CatchFishGame:
    DURATION = 45.0
    ITEMS = (  # 名字, 分值, 权重, 尺寸
        ("🐟", 1, 46, 40), ("🦐", 2, 18, 38), ("🍣", 3, 10, 40), ("💎", 5, 4, 36),
        ("BUSY", -1, 14, 0), ("🐛", -1, 8, 36),
    )

    def __init__(self, pet):
        self.pet = pet
        self.drv = _PetDriver(pet)
        self.items = []
        self.effects = []
        self.score = 0
        self.lives = 3
        self.combo = 0
        self.stun_until = 0.0
        self.hud = None
        self.cache = {}
        self.done = False

    def _pix(self, name, size):
        key = (name, size)
        if key not in self.cache:
            self.cache[key] = busy_cloud_pix() if name == "BUSY" else emoji_pix(name, size)
        return self.cache[key]

    def start(self):
        pet = self.pet
        geo = (pet.screen() or QApplication.primaryScreen()).availableGeometry()
        self.geo = geo
        half = min(700, geo.width() // 2 - 40)
        cx = _clamp(self.drv.cx(), geo.left() + half, geo.right() - half)
        self.left, self.right = cx - half, cx + half
        now = time.time()
        self.t0 = now
        self.t_end = now + self.DURATION
        self.next_spawn = now + 1.2
        self.hud = Hud()
        self.hud.move(int(cx - self.hud.width() / 2), geo.top() + 14)
        self.hud.show()
        self._hud()
        pet.say("接小鱼干！鼠标左右移动带我跑～")
        pet.speak("接小鱼干！")

    def desired_yaw(self):
        y = self.drv.facing_yaw()
        return 0.0 if y is None else y

    def on_pet_pressed(self):
        return True                      # 游戏中点她不触发聊天/拖拽

    def _hud(self):
        left = max(0, int(self.t_end - time.time() + 0.99))
        self.hud.set_state(self.score, max(0, self.lives), left)

    def _spawn(self):
        names = [it for it in self.ITEMS]
        weights = [it[2] for it in names]
        name, value, _, size = random.choices(names, weights)[0]
        progress = (time.time() - self.t0) / self.DURATION
        x = random.uniform(self.left + 30, self.right - 30)
        win = SpriteWindow(self._pix(name, size))
        speed = random.uniform(230, 330) * (1.0 + 0.55 * progress)
        item = {"name": name, "value": value, "x": x, "y": self.geo.top() - 20.0, "v": speed,
                "win": win, "phase": random.uniform(0, 6.28), "dying": 0.0}
        win.place(x, item["y"])
        win.show()
        self.items.append(item)

    def tick(self):
        if self.done:
            return
        now = time.time()
        pet = self.pet
        # 跟着鼠标的 x 跑
        cur = QCursor.pos()
        half_w = pet.width() / 2.0
        tx = _clamp(cur.x(), self.left + half_w * 0.4, self.right - half_w * 0.4)
        if now < self.stun_until:
            self.drv.vx *= 0.8
            tx = self.drv.cx()
        self.drv.run_to(tx, 1150.0, y=self.drv.floor_top())
        # 出新东西
        if now >= self.next_spawn and now < self.t_end - 1.0:
            self._spawn()
            progress = (now - self.t0) / self.DURATION
            self.next_spawn = now + random.uniform(0.42, 0.85) * (1.0 - 0.35 * progress)
        # 掉落 + 碰撞
        cx, top, foot = pet.sprite_geometry()
        mouth_y = top + pet.cur_h * 0.40
        reach = pet.cur_h * 0.30
        keep = []
        for it in self.items:
            if it["dying"]:
                it["dying"] += TICK_S
                k = it["dying"] / 0.25
                it["win"].set_look(scale=1.0 + 0.6 * k, alpha=1.0 - k)
                if k >= 1.0:
                    it["win"].close()
                    continue
                keep.append(it)
                continue
            it["y"] += it["v"] * TICK_S
            x = it["x"] + math.sin(now * 2.2 + it["phase"]) * 6.0
            it["win"].place(x, it["y"])
            if abs(x - cx) < reach and mouth_y - 30 <= it["y"] <= mouth_y + 40:
                self._caught(it, x)
                it["dying"] = TICK_S
                keep.append(it)
                continue
            if it["y"] > self.geo.bottom() + 10:
                if it["value"] > 0:
                    self.combo = 0
                it["win"].close()
                continue
            keep.append(it)
        self.items = keep
        self.effects = [e for e in self.effects if e.tick()]
        if self.pet.t % 10 == 0:
            self._hud()
        if now >= self.t_end or self.lives <= 0:
            self.finish()

    def _caught(self, it, x):
        pet = self.pet
        _, top, _ = pet.sprite_geometry()
        if it["value"] > 0:
            self.combo += 1
            bonus = 1 if self.combo and self.combo % 5 == 0 else 0
            gain = it["value"] + bonus
            self.score += gain
            pet.action, pet.action_t = "eat", 1.0
            _happy(pet, 0.9, hearts=1 if it["value"] < 3 else 2)
            txt = f"+{gain}" + ("  连击!" if bonus else "")
            self.effects.append(FloatText(txt, QColor(255, 120, 60), x, top))
            if random.random() < 0.18:
                pet.say(random.choice(["嗷呜！", "好吃！", "再来！", "咔嚓咔嚓"]))
        else:
            self.lives -= 1
            self.combo = 0
            self.stun_until = time.time() + 1.0
            pet._dizzy_until = time.time() + 1.2
            pet.jump_t = 0.5
            line = "服务器繁忙…请稍后再试" if it["name"] == "BUSY" else "呸呸，是 bug！"
            pet.say(line)
            self.effects.append(FloatText("-❤", QColor(220, 60, 90), x, top))
        self._hud()

    def finish(self):
        if self.done:
            return
        self.done = True
        pet = self.pet
        st = pet.pet_state
        best = int(st.get("catch_best", 0))
        new_best = self.score > best
        if new_best:
            st["catch_best"] = self.score
        coins = min(5, self.score // 8)
        _reward(pet, coins=coins, exp=5 + self.score // 2, counter="catch_game", affection=1)
        msg = f"接到 {self.score} 分" + (f"，奖励 {coins} 条小鱼干！" if coins else "！")
        if new_best and self.score:
            msg += " 新纪录！"
        pet.say(msg)
        pet.speak(msg)
        _happy(pet, 2.0, hearts=3 if coins else 1)
        pet._check_achievements()
        pet.end_game()

    def stop(self):
        self.done = True
        for it in self.items:
            it["win"].close()
        self.items = []
        for e in self.effects:
            e.win.close()
        self.effects = []
        if self.hud is not None:
            self.hud.close()
            self.hud = None


# ======================================================================== 丢球
def ball_pix(d=40):
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = d / 2.0 - 1.5
    c = QPointF(d / 2.0, d / 2.0)
    clip = QPainterPath()
    clip.addEllipse(c, r, r)
    p.setClipPath(clip)
    cols = (QColor(255, 92, 120), QColor(255, 255, 255), QColor(90, 160, 255),
            QColor(255, 255, 255), QColor(255, 206, 80), QColor(255, 255, 255))
    for i, col in enumerate(cols):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPie(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), int(i * 60 * 16), int(60 * 16))
    shade = QRadialGradient(QPointF(d * 0.36, d * 0.32), r * 1.25)
    shade.setColorAt(0.0, QColor(255, 255, 255, 120))
    shade.setColorAt(0.55, QColor(255, 255, 255, 0))
    shade.setColorAt(1.0, QColor(20, 30, 70, 90))
    p.setBrush(shade)
    p.drawEllipse(c, r, r)
    p.setClipping(False)
    p.setPen(QPen(QColor(60, 60, 90, 160), 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, r, r)
    p.end()
    return pm


class FetchGame:
    """拖住球甩出去 → 她跑过去叼起来 → 送回到鼠标旁边。"""
    GRAVITY = 2100.0

    def __init__(self, pet):
        self.pet = pet
        self.drv = _PetDriver(pet)
        self.ball = None
        self.state = "free"        # free / held / carried
        self.vx = self.vy = 0.0
        self.x = self.y = 0.0
        self.samples = []
        self.idle_since = time.time()
        self.fetches = 0
        self.thrown = False        # 只有主人扔出去 / 摆放过的球她才去追（送回来后就乖乖等下一次）
        self.done = False

    def start(self):
        pet = self.pet
        geo = (pet.screen() or QApplication.primaryScreen()).availableGeometry()
        self.geo = geo
        self.ball = SpriteWindow(ball_pix(), clickthrough=False, on_press=self._on_ball_press)
        self.ball.mouseMoveEvent = self._on_ball_move
        self.ball.mouseReleaseEvent = self._on_ball_release
        self.ball.setCursor(Qt.CursorShape.OpenHandCursor)
        cx, top, foot = pet.sprite_geometry()
        side = -1 if cx > geo.center().x() else 1
        self.x = cx + side * pet.cur_h * 0.9
        self.y = top + pet.cur_h * 0.3
        self.vy = -300.0
        self.ball.place(self.x, self.y)
        self.ball.show()
        pet.say("丢球！按住球甩出去～")

    def desired_yaw(self):
        y = self.drv.facing_yaw()
        if y is not None:
            return y
        return self.ball_yaw()

    def on_pet_pressed(self):
        return False                     # 允许照常拖她

    # ---- 球的拖拽
    def _on_ball_press(self, win, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.state = "held"
            self.samples = [(time.time(), e.globalPosition().x(), e.globalPosition().y())]
            self.grab = QPointF(e.globalPosition().x() - self.x, e.globalPosition().y() - self.y)
            self.ball.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.idle_since = time.time()
        elif e.button() == Qt.MouseButton.RightButton:
            self.pet.end_game()

    def _on_ball_move(self, e):
        if self.state != "held":
            return
        gx, gy = e.globalPosition().x(), e.globalPosition().y()
        self.x, self.y = gx - self.grab.x(), gy - self.grab.y()
        now = time.time()
        self.samples.append((now, gx, gy))
        self.samples = [s for s in self.samples if now - s[0] < 0.1]
        self.ball.place(self.x, self.y)

    def _on_ball_release(self, e):
        if self.state != "held":
            return
        self.state = "free"
        self.thrown = True
        self.ball.setCursor(Qt.CursorShape.OpenHandCursor)
        if len(self.samples) >= 2:
            (t0, x0, y0), (t1, x1, y1) = self.samples[0], self.samples[-1]
            dt = max(0.016, t1 - t0)
            self.vx = _clamp((x1 - x0) / dt, -2600, 2600)
            self.vy = _clamp((y1 - y0) / dt, -2600, 2600)
        if abs(self.vx) + abs(self.vy) > 400 and random.random() < 0.5:
            self.pet.say(random.choice(["我来啦！", "看我的！", "冲鸭——"]))

    # ---- 每帧
    def tick(self):
        if self.done:
            return
        pet = self.pet
        geo = self.geo
        now = time.time()
        r = self.ball.pix.width() / 2.0
        floor = geo.bottom() - r
        cx, top, foot = pet.sprite_geometry()
        if self.state == "free":
            self.vy += self.GRAVITY * TICK_S
            self.x += self.vx * TICK_S
            self.y += self.vy * TICK_S
            if self.x < geo.left() + r:
                self.x, self.vx = geo.left() + r, abs(self.vx) * 0.6
            elif self.x > geo.right() - r:
                self.x, self.vx = geo.right() - r, -abs(self.vx) * 0.6
            if self.y < geo.top() + r:
                self.y, self.vy = geo.top() + r, abs(self.vy) * 0.5
            if self.y >= floor:
                self.y = floor
                if abs(self.vy) > 120:
                    self.vy = -abs(self.vy) * 0.55
                else:
                    self.vy = 0.0
                self.vx *= 0.972                 # 地面摩擦：滚一段就停，不会滚过整个屏幕
                if abs(self.vx) < 8:
                    self.vx = 0.0
            self.ball.set_look(angle=(self.ball.angle + self.vx * TICK_S * 2.2) % 360)
            self.ball.place(self.x, self.y)
            if not self.thrown:
                # 球是她刚送回来的：站在旁边等主人再扔，眼睛盯着球
                self.drv.run_to(self.drv.cx(), 400.0, y=self.drv.floor_top())
                return self._maybe_bored(now)
            # 球落到下半屏、速度不快时就全速去追
            near_floor = self.y > geo.bottom() - pet.cur_h * 0.9
            if near_floor or abs(self.vy) < 60:
                self.drv.run_to(self.x, 760.0, y=self.drv.floor_top())
            else:
                self.drv.run_to(self.x, 420.0, y=self.drv.floor_top())
            if abs(self.x - cx) < pet.cur_h * 0.22 and self.y > foot - pet.cur_h * 0.55:
                self.state = "carried"
                pet.jump_t = 0.6
                _happy(pet, 0.8, hearts=0)
                if random.random() < 0.4:
                    pet.say(random.choice(["抓到了！", "嘿嘿～", "我的了！"]))
        elif self.state == "carried":
            cur = QCursor.pos()
            dest = _clamp(cur.x(), geo.left() + pet.width() / 2, geo.right() - pet.width() / 2)
            rest = self.drv.run_to(dest, 620.0, y=self.drv.floor_top())
            facing = -1 if pet.dir == "left" else 1
            cx, top, foot = pet.sprite_geometry()
            bob = math.sin(now * 14) * 2 if pet.target is not None else 0.0
            self.x = cx + facing * pet.cur_h * 0.16
            self.y = top + pet.cur_h * 0.52 + bob
            self.ball.place(self.x, self.y)
            if abs(rest) < 30:
                self.state = "free"
                self.thrown = False
                self.vx = facing * 70.0          # 轻轻放在鼠标前面
                self.vy = -360.0
                self.fetches += 1
                self.idle_since = now
                _happy(pet, 1.8, hearts=2)
                _reward(pet, exp=2, counter="fetch", affection=1 if self.fetches % 2 else 0)
                pet._check_achievements()
                line = random.choice(["给你！再扔一次～", "捡回来啦！夸我！", "还要还要！"])
                pet.say(line)
                pet.speak(line)
        else:
            self.drv.run_to(self.drv.cx(), 400.0)
        self._maybe_bored(now)

    def _maybe_bored(self, now):
        if self.state != "held" and self.vx == 0 and self.vy == 0 and now - self.idle_since > 60:
            self.pet.say("不玩啦？那我把球收起来咯")
            self.pet.end_game()

    def ball_yaw(self):
        """站着等的时候朝球那边侧着看。"""
        if self.ball is None:
            return 0.0
        dx = self.x - self.drv.cx()
        if abs(dx) < self.pet.cur_h * 0.3:
            return 0.0
        return 20.0 if dx < 0 else -20.0

    def stop(self):
        self.done = True
        if self.ball is not None:
            self.ball.close()
            self.ball = None


# ======================================================================== 捉迷藏
class HideSeekGame:
    TIME_LIMIT = 30.0

    def __init__(self, pet):
        self.pet = pet
        self.phase = "count"
        self.spot = None
        self.done = False
        self.hint_said = False
        self.anim = None

    def start(self):
        pet = self.pet
        pet.target = None
        self.home = pet.pos()
        self.t_phase = time.time() + 1.8
        pet.say("我数到三就藏好～ 你来找我！")
        pet.speak("一、二、三！")

    def desired_yaw(self):
        if self.phase == "hide" and self.spot:
            return self.spot["yaw"]
        return None

    def _hide(self):
        if self.done:                       # 淡出途中游戏已被结束
            return
        pet = self.pet
        scr = pet.screen() or QApplication.primaryScreen()
        full, geo = scr.geometry(), scr.availableGeometry()
        h = pet.height()
        fw = pet.width() - 2 * pet.win_mx                  # 精灵本身的宽度
        # 躲在屏幕左 / 右边缘外面，只探出小半个身子（朝屏幕里侧着看）
        y = random.randint(geo.top() + 60, max(geo.top() + 61, geo.bottom() - h))
        spots = [
            {"pos": (full.left() - pet.win_mx - int(fw * 0.56), y), "yaw": -20.0},
            {"pos": (full.right() + 1 - pet.win_mx - int(fw * 0.44), y), "yaw": 20.0},
        ]
        cur = QCursor.pos()
        spots.sort(key=lambda s: -abs(s["pos"][0] + pet.width() / 2 - cur.x()))
        self.spot = spots[0] if random.random() < 0.7 else spots[1]   # 多半躲在离鼠标远的那边
        pet.setWindowOpacity(0.0)
        pet.move(*self.spot["pos"])
        self.anim = QPropertyAnimation(pet, b"windowOpacity", pet)
        self.anim.setDuration(380)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.phase = "hide"
        self.t_phase = time.time() + self.TIME_LIMIT
        self.hidden_at = time.time()

    def tick(self):
        if self.done:
            return
        pet = self.pet
        now = time.time()
        if self.phase == "count":
            if now >= self.t_phase:
                self._fade_out_then_hide()
        elif self.phase == "fading":
            if now >= self.t_phase:          # 按时间推进，不依赖动画回调
                self._hide()
        elif self.phase == "hide":
            if not self.hint_said and now - self.hidden_at > 12:
                self.hint_said = True
                pet.say("嘻嘻……", inner=True)
            if now >= self.t_phase:
                self._reveal(False)

    def _fade_out_then_hide(self):
        self.phase = "fading"
        self.t_phase = time.time() + 0.28
        self.anim = QPropertyAnimation(self.pet, b"windowOpacity", self.pet)
        self.anim.setDuration(260)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()

    def on_pet_pressed(self):
        if self.phase == "hide":
            self._reveal(True)
        return True

    def _reveal(self, found):
        if self.done:
            return
        self.done = True
        pet = self.pet
        geo = (pet.screen() or QApplication.primaryScreen()).availableGeometry()
        x = _clamp(pet.x(), geo.left(), geo.right() - pet.width())
        y = _clamp(pet.y(), geo.top(), geo.bottom() - pet.height())
        self.anim = QPropertyAnimation(pet, b"pos", pet)
        self.anim.setDuration(420)
        self.anim.setStartValue(pet.pos())
        self.anim.setEndValue(QPoint(int(x), int(y)))
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.start()
        if found:
            spent = time.time() - self.hidden_at
            coins = 2 if spent < 8 else 1
            _reward(pet, coins=coins, exp=6, counter="found", affection=1)
            _happy(pet, 2.0, hearts=3)
            line = random.choice(["被你找到了！", "这都能找到？！", "哼，下次藏更好"]) + f" 奖励 {coins} 条小鱼干"
        else:
            _happy(pet, 1.2, hearts=0)
            line = random.choice(["笨蛋～我在这儿呢！", "找不到吧～嘿嘿", "时间到！我赢啦"])
        pet._check_achievements()
        pet.say(line)
        pet.speak(line)
        pet.jump_t = 1.0
        pet.home_x, pet.home_y = int(x), int(y)
        pet.end_game()

    def stop(self):
        was_hiding = self.phase in ("fading", "hide") and not self.done
        self.done = True
        if self.anim is not None and self.anim.propertyName() == b"windowOpacity":
            self.anim.stop()
        self.pet.setWindowOpacity(1.0)
        if was_hiding:
            # 从菜单中途结束：把她从屏幕边缘请回来
            geo = (self.pet.screen() or QApplication.primaryScreen()).availableGeometry()
            self.pet.move(int(_clamp(self.pet.x(), geo.left(), geo.right() - self.pet.width())),
                          int(_clamp(self.pet.y(), geo.top(), geo.bottom() - self.pet.height())))


# ======================================================================== 性感舞蹈秀
def _ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class DanceShow:
    """约 20 秒的舞台秀：聚光灯 + 3D 转身编舞；在节拍上点她 = 打拍子，结束按跟拍成绩给奖励。

    编舞全部由时间算出来（每拍 60/BPM 秒），桌宠绘制时读 pose() 拿当前姿势，
    转身角度直接设给 3D 形象（不走平滑转向，转圈才够利落）。"""
    BPM = 112
    MOVES = (("intro", 2), ("sway", 4), ("spin", 2), ("wink", 2), ("sway_fast", 4), ("hairflip", 2),
             ("lookback", 2), ("bounce", 4), ("spin_rev", 2), ("heart", 2), ("sway_slow", 4),
             ("finale", 2))
    OUTRO = 3
    LINES = {
        "intro": ["要开始咯～跟着节拍点我！", "音乐，起！看好了～"],
        "spin": ["转个圈～", "看我转！"],
        "wink": ["Wink～", "电到你了吗？"],
        "hairflip": ["甩个头发～", "帅不帅？"],
        "lookback": ["回眸一笑～", "这段只跳给你看"],
        "heart": ["比心！", "给你一个大爱心～"],
        "sway_slow": ["慢下来……别眨眼", "扭～扭～"],
        "finale": ["最后一个 pose！", "定格！"],
    }

    def __init__(self, pet):
        self.pet = pet
        self.beat = 60.0 / self.BPM
        self.total = sum(n for _, n in self.MOVES)
        self.hits = {}                 # 拍号 -> "perfect" / "good"
        self.combo = 0
        self.best_combo = 0
        self.effects = []
        self.fired = set()
        self.direct_yaw = 0.0
        self.cur = {}
        self.done = False
        self.heart_t0 = None

    # ---------------------------------------------------------------- 流程
    def start(self):
        pet = self.pet
        self._look_before = pet.look
        pet.look = "cute"                 # 跳舞用可爱形象（不切粉紫滤镜），结束后恢复原来的形象
        pet.target = None
        pet.action = None
        self.t0 = time.time() + 0.9
        line = random.choice(self.LINES["intro"])
        pet.say(line)
        pet.speak(line)

    def desired_yaw(self):
        return None

    def _segment(self, b):
        acc = 0
        for name, n in self.MOVES:
            if b < acc + n:
                return name, b - acc, n
            acc += n
        return "bow", b - acc, self.OUTRO

    def tick(self):
        if self.done:
            return
        now = time.time()
        b = (now - self.t0) / self.beat
        if b < 0:
            self.cur = {"yaw": 0.0, "dy": -abs(math.sin(now * 6)) * 2}
            self.direct_yaw = 0.0
        elif b >= self.total + self.OUTRO:
            self.finish()
            return
        else:
            name, lb, n = self._segment(b)
            self.cur = self._pose(name, lb, b)
            self.direct_yaw = self.cur.get("yaw", 0.0)
            bi = int(b)
            if bi not in self.fired:
                self.fired.add(bi)
                self._on_beat(bi, name, int(lb))
        self.effects = [e for e in self.effects if e.tick()]

    def _on_beat(self, bi, name, local_beat):
        pet = self.pet
        if local_beat == 0 and name in self.LINES and name != "intro" and random.random() < 0.8:
            pet.say(random.choice(self.LINES[name]))
        if name in ("wink", "lookback") and local_beat == 1:
            pet._hearts.append((time.time(), random.uniform(-0.08, 0.08), random.uniform(-10, 10)))
        if name == "heart" and local_beat == 0:
            self.heart_t0 = time.time()
        if name == "finale" and local_beat == 1:
            for i in range(4):
                pet._hearts.append((time.time() + i * 0.08, random.uniform(-0.15, 0.15), random.uniform(-16, 16)))
        if name == "bow" and local_beat == 0:
            self._show_result()
        # 漏拍：上一拍没点到就断连击
        if bi - 1 >= 0 and bi - 1 < self.total and (bi - 1) not in self.hits and bi - 1 >= 2:
            self.combo = 0

    def _pose(self, name, lb, b):
        """返回当前姿势：yaw 朝向、rot 身体倾斜、dx/dy 位移、sx/sy 缩放增量、eyes 表情。"""
        u = lb % 1.0
        bounce = -abs(math.sin(math.pi * u)) * 6.0
        p = {"yaw": 0.0, "rot": 0.0, "dx": 0.0, "dy": 0.0, "sx": 0.0, "sy": 0.0, "eyes": None}
        if name == "intro":
            p.update(dy=bounce * 0.6, sy=0.02 * math.sin(math.pi * u))
        elif name == "sway":
            s = math.sin(math.pi * lb)
            p.update(yaw=30 * s, rot=6 * s, dx=8 * s, dy=bounce, sx=0.03 * math.sin(2 * math.pi * lb))
        elif name == "spin":
            t = lb / 2.0
            p.update(yaw=360.0 * _ease(t), dy=-math.sin(math.pi * t) * 22, sy=0.05 * math.sin(math.pi * t),
                     sx=-0.03 * math.sin(math.pi * t))
        elif name == "wink":
            tilt = _ease(min(1.0, lb * 2))
            p.update(yaw=20.0, rot=-7 * tilt, dy=bounce * 0.4,
                     eyes="wink" if 0.25 <= lb <= 1.7 else None)
        elif name == "sway_fast":
            s = math.sin(2 * math.pi * lb / 2.0 * 2)
            p.update(yaw=38 * s, rot=7 * s, dx=11 * s, dy=bounce)
        elif name == "hairflip":
            if lb < 1.0:
                p.update(yaw=90.0 * _ease(lb / 0.5), rot=-14 * math.sin(math.pi * lb))
            else:
                p.update(yaw=90.0 * (1 - _ease(lb - 1.0)), rot=6 * math.sin(math.pi * (lb - 1.0)))
        elif name == "lookback":
            if lb < 1.0:
                p.update(yaw=160.0 * _ease(lb / 0.6), rot=-4 * math.sin(math.pi * lb))
            else:
                k = _ease((lb - 1.0) / 0.4)
                p.update(yaw=160.0 * (1 - k), eyes="wink" if lb > 1.45 else None)
        elif name == "bounce":
            beat_i = int(lb)
            land = max(0.0, 1.0 - u * 4.0)
            p.update(yaw=15.0 * (1 if beat_i % 2 else -1), dy=-math.sin(math.pi * u) * 16,
                     sy=0.05 * math.sin(math.pi * u) - 0.08 * land, sx=0.05 * land)
        elif name == "spin_rev":
            t = lb / 2.0
            p.update(yaw=-360.0 * _ease(t), dy=-math.sin(math.pi * t) * 22, sy=0.05 * math.sin(math.pi * t))
        elif name == "heart":
            p.update(dy=bounce * 0.3, eyes="happy")
        elif name == "sway_slow":
            s = math.sin(math.pi * lb / 2.0)
            p.update(yaw=25 * s, rot=10 * s, dx=14 * s, dy=-abs(math.sin(math.pi * lb)) * 5,
                     sx=0.04 * math.sin(math.pi * lb))
        elif name == "finale":
            if lb < 1.0:
                p.update(yaw=360.0 * _ease(lb), dy=-math.sin(math.pi * lb) * 24)
            else:
                k = _ease((lb - 1.0) * 2)
                p.update(yaw=20.0 * k, rot=-6 * k, sy=0.06 * k, eyes="wink")
        elif name == "bow":
            k = math.sin(math.pi * min(1.0, lb / 2.0))
            p.update(sy=-0.09 * k, eyes="happy")
        return p

    def pose(self):
        return self.cur

    # ---------------------------------------------------------------- 打拍子
    def on_pet_pressed(self):
        now = time.time()
        b = (now - self.t0) / self.beat
        nearest = int(round(b))
        _, top, _ = self.pet.sprite_geometry()
        cx = self.pet.x() + self.pet.width() / 2.0
        if 0 <= nearest < self.total and nearest not in self.hits:
            err = abs(b - nearest) * self.beat
            if err <= 0.10:
                self.hits[nearest] = "perfect"
                txt, col = "完美!", QColor(255, 90, 160)
            elif err <= 0.20:
                self.hits[nearest] = "good"
                txt, col = "不错", QColor(255, 160, 60)
            else:
                txt, col = "没踩上～", QColor(140, 140, 170)
            if nearest in self.hits:
                self.combo += 1
                self.best_combo = max(self.best_combo, self.combo)
                if self.combo >= 4:
                    txt += f" ×{self.combo}"
                if self.hits[nearest] == "perfect":
                    self.pet._hearts.append((now, random.uniform(-0.1, 0.1), random.uniform(-12, 12)))
            else:
                self.combo = 0
            self.effects.append(FloatText(txt, col, cx + random.uniform(-20, 20), top - 6))
        return True                      # 舞台上点她只算打拍子，不拖拽也不弹聊天

    # ---------------------------------------------------------------- 结束
    def _show_result(self):
        perfect = sum(1 for v in self.hits.values() if v == "perfect")
        good = sum(1 for v in self.hits.values() if v == "good")
        self.score = perfect * 2 + good
        self.perfect, self.good = perfect, good
        if perfect + good == 0:
            line = "谢谢观看～下次跟着节拍点我嘛"
        else:
            line = f"谢幕～跟拍 {perfect + good}/{self.total}，完美 {perfect} 次"
        self.pet.say(line)
        self.pet.speak(line)

    def finish(self):
        if self.done:
            return
        pet = self.pet
        if not hasattr(self, "score"):
            self._show_result()
        st = pet.pet_state
        best = int(st.get("dance_best", 0))
        if self.score > best:
            st["dance_best"] = self.score
        coins = min(5, self.score // 12)
        _reward(pet, coins=coins, exp=6 + self.score // 2, counter="dance_show",
                affection=2 + min(3, self.score // 20))
        _happy(pet, 2.0, hearts=3 if self.score >= 20 else 1)
        if coins:
            pet._queue_say(f"跳得开心，奖励 {coins} 条小鱼干！" + (" 新纪录！" if self.score > best else ""))
        pet._check_achievements()
        self.done = True
        pet.end_game()

    def stop(self):
        self.done = True
        self.pet.look = getattr(self, "_look_before", self.pet.look)
        for e in self.effects:
            e.win.close()
        self.effects = []

    # ---------------------------------------------------------------- 舞台特效（画在桌宠自己的窗口里，克制一点）
    def paint_fx(self, p, cx, ground, h, layer):
        now = time.time()
        b = (now - self.t0) / self.beat
        if b < 0:
            return
        k = b % 1.0
        pulse = math.exp(-k * 6.0)
        if layer == "back":
            # 脚下一小圈柔光，踩点时亮一下（不再在身后铺一大团光晕）
            g = QRadialGradient(QPointF(0, 0), h * 0.30)
            g.setColorAt(0.0, QColor(255, 170, 215, int(60 + 90 * pulse)))
            g.setColorAt(1.0, QColor(255, 170, 215, 0))
            p.save()
            p.translate(cx, ground - 2)
            p.scale(1.0, 0.2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(0, 0), h * 0.30, h * 0.30)
            p.restore()
            # 节拍提示：一圈很淡的细光环往外扩
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 140, 195, int(120 * (1 - k))), 1.3))
            p.drawEllipse(QPointF(cx, ground - 2), h * (0.17 + 0.20 * k), h * (0.032 + 0.03 * k))
        else:
            # 每两拍在身边闪几颗小亮片
            group = int(b // 2)
            local = (b % 2.0) / 2.0
            rnd = random.Random(group * 7919)
            for _ in range(3):
                sx = cx + rnd.uniform(-0.42, 0.42) * h
                sy = ground - rnd.uniform(0.35, 1.0) * h
                tw = math.sin(math.pi * min(1.0, local * 1.6))
                if tw <= 0.02:
                    continue
                r = h * rnd.uniform(0.018, 0.03) * (0.6 + 0.4 * tw)
                star = QPainterPath()
                star.moveTo(sx, sy - r)
                for ang in range(1, 8):
                    rr = r if ang % 2 == 0 else r * 0.28
                    a = math.radians(ang * 45 - 90)
                    star.lineTo(sx + rr * math.cos(a), sy + rr * math.sin(a))
                star.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 244, 214, int(230 * tw)))
                p.drawPath(star)
            # 一个淡淡的音符从旁边飘起
            f = QFont("Segoe UI Symbol")
            f.setPixelSize(max(9, int(h * 0.085)))
            p.setFont(f)
            kk = (b * 0.35) % 1.0
            side = -1 if int(b * 0.35) % 2 == 0 else 1
            p.setPen(QColor(235, 120, 180, int(150 * math.sin(math.pi * kk))))
            p.drawText(QPointF(cx + side * h * 0.38, ground - h * (0.35 + 0.6 * kk)), "♪")
            # 比心：头顶冒出一颗大爱心
            if self.heart_t0 is not None:
                age = now - self.heart_t0
                if age < 2.4:
                    k = min(1.0, age / 0.5)
                    fade = 1.0 if age < 1.8 else max(0.0, 1 - (age - 1.8) / 0.6)
                    path = QPainterPath()
                    r = h * 0.12 * (0.4 + 0.6 * _ease(k)) * (1 + 0.06 * math.sin(age * 12))
                    hx, hy = cx, ground - h * 1.05
                    path.moveTo(hx, hy - r * 0.35)
                    path.cubicTo(hx - r * 0.55, hy - r * 0.95, hx - r * 1.05, hy - r * 0.25, hx, hy + r * 0.75)
                    path.cubicTo(hx + r * 1.05, hy - r * 0.25, hx + r * 0.55, hy - r * 0.95, hx, hy - r * 0.35)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(255, 70, 130, int(235 * fade)))
                    p.drawPath(path)


# ======================================================================== 吹泡泡
def bubble_pix(d, golden=False):
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QPointF(d / 2.0, d / 2.0)
    r = d / 2.0 - 1.5
    g = QRadialGradient(c, r)
    if golden:
        g.setColorAt(0.0, QColor(255, 236, 160, 40))
        g.setColorAt(0.72, QColor(255, 214, 90, 70))
        g.setColorAt(1.0, QColor(255, 180, 40, 210))
    else:
        g.setColorAt(0.0, QColor(200, 235, 255, 26))
        g.setColorAt(0.70, QColor(170, 215, 255, 52))
        g.setColorAt(0.92, QColor(255, 170, 230, 120))
        g.setColorAt(1.0, QColor(120, 190, 255, 200))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(c, r, r)
    p.setBrush(QColor(255, 255, 255, 210))
    p.drawEllipse(QPointF(d * 0.34, d * 0.32), d * 0.09, d * 0.06)
    p.setPen(QPen(QColor(255, 255, 255, 170), max(1.0, d * 0.04)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(d * 0.18, d * 0.18, d * 0.64, d * 0.64), 100 * 16, 60 * 16)
    p.end()
    return pm


class BubbleBurst:
    """她吹出一串泡泡往上飘，点破有经验，金泡泡给小鱼干。"""

    def __init__(self, pet):
        self.pet = pet
        self.bubbles = []
        self.to_spawn = random.randint(4, 7)
        self.next_spawn = time.time() + 0.25
        self.done = False
        pet.say(random.choice(["噗噜噗噜～", "吹泡泡咯，快戳！", "泡泡来啦～"]))

    def _spawn(self):
        pet = self.pet
        cx, top, foot = pet.sprite_geometry()
        golden = random.random() < 0.12
        d = random.randint(28, 46) if not golden else 40
        b = {"x": cx + random.uniform(-8, 8), "y": top + pet.cur_h * 0.42, "vx": random.uniform(-55, 55),
             "vy": -random.uniform(55, 105), "born": time.time(), "phase": random.uniform(0, 6.28),
             "golden": golden, "pop": 0.0}
        win = SpriteWindow(bubble_pix(d, golden), clickthrough=False,
                           on_press=lambda w, e, bb=b: self._pop(bb, by_user=True))
        win.setCursor(Qt.CursorShape.PointingHandCursor)
        b["win"] = win
        win.place(b["x"], b["y"])
        win.set_look(scale=0.3)
        win.show()
        self.bubbles.append(b)

    def _pop(self, b, by_user=False):
        if b["pop"]:
            return
        b["pop"] = TICK_S
        if by_user:
            pet = self.pet
            if b["golden"]:
                _reward(pet, coins=1, exp=2, counter="bubble")
                pet.say("金泡泡！小鱼干 +1")
                _happy(pet, 1.2, hearts=1)
            else:
                _reward(pet, exp=1, counter="bubble")
            pet._check_achievements()

    def tick(self):
        now = time.time()
        if self.to_spawn > 0 and now >= self.next_spawn:
            self._spawn()
            self.to_spawn -= 1
            self.next_spawn = now + random.uniform(0.25, 0.5)
        # 泡泡飘得慢，每秒移动 25 次就够了（每个泡泡都是一个小窗口，移动太勤会白白吃 CPU）
        self._odd = not getattr(self, "_odd", False)
        if self._odd and not any(b["pop"] for b in self.bubbles):
            return
        dt = TICK_S * 2
        geo = (self.pet.screen() or QApplication.primaryScreen()).availableGeometry()
        keep = []
        for b in self.bubbles:
            win = b["win"]
            if b["pop"]:
                b["pop"] += TICK_S
                k = b["pop"] / 0.18
                win.set_look(scale=1.0 + 0.5 * k, alpha=1.0 - k)
                if k >= 1.0:
                    win.close()
                    continue
                keep.append(b)
                continue
            if self._odd:
                keep.append(b)
                continue
            age = now - b["born"]
            b["vy"] = max(-150.0, b["vy"] - 8.0 * dt)
            b["x"] += (b["vx"] + math.sin(now * 2.4 + b["phase"]) * 28) * dt
            b["y"] += b["vy"] * dt
            b["vx"] *= 0.99
            win.place(b["x"], b["y"])
            if age < 0.35:
                # 冒出来时放大：只分 4 档，少重画几次
                win.set_look(scale=round((0.3 + 0.7 * age / 0.35) * 4) / 4.0)
            elif win.scale != 1.0:
                win.set_look(scale=1.0)
            if age > 9.0 or b["y"] < geo.top() + 10:
                self._pop(b)
            keep.append(b)
        self.bubbles = keep
        if self.to_spawn <= 0 and not self.bubbles:
            self.close_toy()

    def close_toy(self):
        for b in self.bubbles:
            b["win"].close()
        self.bubbles = []
        if self in self.pet.toys:
            self.pet.toys.remove(self)
