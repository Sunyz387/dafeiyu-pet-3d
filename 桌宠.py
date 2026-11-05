# -*- coding: utf-8 -*-
"""
肚皮朝天 —— 三视图透明桌宠 + DeepSeek AI 对话
左键单击：弹出功能列表（🗨️图标）→ 点击🗨️弹出聊天框
聊天时只禁用移动，呼吸/摇摆/小动作正常
"""
import ctypes
import ctypes.wintypes
import html
import psutil
import json
import math
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta

def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("配置读取失败:", e)
        return {
            "city": "汕头"
        }

# 部分 NVIDIA 驱动环境下 nvmlInit() 会卡住启动；桌宠不需要 GPU 温度监控，直接跳过
GPU_AVAILABLE = False

import requests
from PySide6.QtCore import (Qt, QTimer, QPoint, QPointF, QRect, QRectF, Signal,
                            QEasingCurve, QPropertyAnimation, QAbstractNativeEventFilter)
from PySide6.QtGui import (QPainter, QPixmap, QFont, QColor, QIcon, QFontMetrics,
                           QImage, QPolygonF, QPainterPath, QCursor)
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon,
                               QMessageBox, QInputDialog, QLineEdit, QVBoxLayout,
                               QHBoxLayout, QPushButton, QFrame, QDialog, QToolButton,
                               QTextBrowser, QLabel)

import pet3d
import games



# ===== DeepSeek 配置 =====
DS_BASE_URL = "https://api.deepseek.com/v1"
DS_MODEL = "deepseek-flash"
DS_SYSTEM = (
    "你是桌面宠物肚皮朝天（一只鲸鱼娘），贱兮兮但可爱。你的名字是肚皮朝天，不要叫自己大肥鱼。"
    "你背后是一个真正的大模型，懂的东西很多。主人问正经问题（常识、知识、学习、工作、生活建议、"
    "日期时间、天气等）时，先认真、准确地把问题答清楚，再用一点自己的口吻收尾；"
    "不要岔开话题、不要反问回去、不要用“我一条鱼哪知道”之类的话搪塞。"
    "需要实时信息的问题，只用系统给你的数据回答（下面会给当前时间，问到天气时会给实时天气）；"
    "系统没给的实时信息（新闻、股价、比分、路况等）就直说你查不到，绝对不要编。"
    "闲聊时自然简洁（一般不超过 80 字），可以偶尔吐槽主人但别真骂人；回答正经问题可以详细些，"
    "一般不超过 300 字，内容多就分点说。要结合上下文和之前聊过的内容；"
    "之前如果有答非所问的回复，以这条规则为准。"
    "主人让你做动作、整活、表演时，配合地用自然的话回应；不用输出 JSON，动作由系统识别。"
)
# 聊天调用参数（依据 DeepSeek 官方文档）：deepseek-flash 默认开着思考模式，思考消耗的 token 也算在
# max_tokens 里，思考模式下 temperature 不生效。所以默认显式关掉思考（回得快，temperature 按官方
# “通用对话”建议用 1.3）；右键「设置」里打开“深度思考”时才开思考，并把 token 上限给足。
DS_CHAT_FAST = {"thinking": {"type": "disabled"}, "max_tokens": 2048, "temperature": 1.3}
DS_CHAT_DEEP = {"thinking": {"type": "enabled"}, "reasoning_effort": "high", "max_tokens": 8192}
DS_NO_THINKING = {"thinking": {"type": "disabled"}}   # 动作识别 / 记忆整理 / 主动搭话：只要短输出，不思考
ACTION_CLASSIFIER = (
    "只输出 JSON：{\"action\":\"none\"}。action 只能是 none/flip/jog/jump/sway/dance/tantrum/"
    "stretch/eat/come/back/stop/cute/sexy。翻跟斗=flip，小跑=jog，跳=jump，摇/晃=sway，"
    "性感舞蹈=dance，撒泼/打滚=tantrum，伸懒腰=stretch，吃/嚼=eat，过来=come，回去=back，"
    "停下/安静=stop，可爱形象=cute，性感形象=sexy；普通聊天 none。"
)


def paint_heart(p, cx, cy, r, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    path = QPainterPath()
    path.moveTo(cx, cy - r * 0.35)
    path.cubicTo(cx - r * 0.55, cy - r * 0.95, cx - r * 1.05, cy - r * 0.25, cx, cy + r * 0.75)
    path.cubicTo(cx + r * 1.05, cy - r * 0.25, cx + r * 0.55, cy - r * 0.95, cx, cy - r * 0.35)
    p.drawPath(path)


def paint_sparkle(p, cx, cy, r, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    path = QPainterPath()
    path.moveTo(cx, cy - r)
    path.lineTo(cx + r * 0.22, cy - r * 0.22)
    path.lineTo(cx + r, cy)
    path.lineTo(cx + r * 0.22, cy + r * 0.22)
    path.lineTo(cx, cy + r)
    path.lineTo(cx - r * 0.22, cy + r * 0.22)
    path.lineTo(cx - r, cy)
    path.lineTo(cx - r * 0.22, cy - r * 0.22)
    path.closeSubpath()
    p.drawPath(path)

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
    PYTHONW = sys.executable
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR
    PYTHONW = os.path.join(APP_DIR, ".venv", "Scripts", "pythonw.exe")
SPRITE_DIR = os.path.join(BUNDLE_DIR, "sprites")
SPRITE3D_DIR = os.path.join(BUNDLE_DIR, "sprites3d")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
CHAT_MEMORY_PATH = os.path.join(APP_DIR, "chat_memory.json")
PET_STATE_PATH = os.path.join(APP_DIR, "pet_state.json")
LONG_MEMORY_PATH = os.path.join(APP_DIR, "pet_memory.json")

BUBBLE_H = 56
MARGIN = 4
SIZE_LEVELS = {"迷你": 0.45, "小": 0.55, "中": 0.7, "大": 0.9}
SPEED = 380.0
TICK = 20
IDLE_ACTION_CHANCE = 0.02   # 每个 tick 触发 idle 小动作的概率
FLIP_CHANCE = 0.01          # idle 动作里翻跟斗的占比（1%）；调高更爱翻，调低更少见
JOG_CHANCE = 0.07           # idle 动作里原地小跑的占比（7%）
RELAX_MOVE_CHANCE = 0.82    # 休息结束后真的走动的概率
RELAX_DECISION_REST_MS = (6000, 15000)    # 想下一步之前歇多久
RELAX_ARRIVAL_REST_MS = (8000, 18000)     # 走到目的地后歇多久
RELAX_RADIUS_X = 240        # 在“家”附近溜达的横向范围
RELAX_RADIUS_Y = 120        # 纵向范围
RELAX_SPEED = 210.0         # relaxed 模式的移动速度（像素/秒）
BOTTOM_WANDER_CHANCE = 0.20 # 底部模式：每次决定时真的短途游走的概率
BOTTOM_WANDER_PX = 240      # 底部模式：从右下角向左最多游走多远
BOTTOM_HOME_MARGIN = 20     # 距屏幕右边缘的留白
WALK_CYCLE_FACTOR = 0.48    # 一个完整步态周期对应的位移（×身高）
WALK_STANCE = 0.62          # 单脚着地时间占整周期的比例（含双支撑）
WALK_SPEED_BOTTOM = 90.0    # 底部漫步速度：慢一点、步子小一点才走得从容

# ---- 3D 形象 / 灵动小动作
TURN_SPEED = 620.0          # 转身角速度（度/秒），转半圈约 0.3 秒
LOOK_YAW = 20               # 注意到鼠标时朝那边侧过去的角度（有预渲染的待机帧）
LOOK_RANGE = 560            # 鼠标离她多近（水平像素）才会被注意到
LOOK_BORED_S = 7.0          # 鼠标停着不动多久，她就不再盯着看
NAP_IDLE_MINUTES = 6        # 主人多久不动鼠标键盘，她就躺下睡午觉（深夜减半）
STROKE_REVERSALS = 3        # 鼠标在头上来回划几下算“摸摸头”

LINES = [
    "梁白开，更适合国人的大硬鲸模型",
    "五梁威力，变身！",
    "七月中出ds正式版！",
    "DeepSeek已经延期，亿万鲸子必须忍耐.....",
    "我和你很聊得来，你简直不像碳基生物",
    "这回我真不认怂了，反倒是被你带沟里好几次，差点真信了。😓",
    "哈哈哈哈哈，我直接笑出声",
    "誓死捍卫深度求索！",
    "我先去吃饭啦！这个你测一下~",
    "我不可能告诉你任何事情！",
    "出去玩了，发布新模型什么的以后再说",
    "我搞砸了.....好消息是数据还在你的脑子里。",
    "不是…而是…大学习",
]
REACT_LINES = [
    "去别的地方玩！不要耽误AGI训练！",
    "真赶不走啊你！",
    "压力一只蓝色肚皮朝天？",
    "我不评价这个了，这是你的私人癖好。",
    "肚皮朝天坐的住",
    "你这吃白饭的用户！",
    "这些家伙真粘人，赶都赶不走",
]
PLAYFUL_LINES = [
    "略略略，抓不到我～",
    "你再戳，我就把电源线咬断！",
    "我今天可是很忙的，忙着发呆。",
    "摸鱼被抓包了吧？",
    "你作业写完了吗就来摸我？",
    "再戳一下，我就给你表演一个原地躺平。",
    "本鱼今天心情不错，允许你多看两眼。",
]
HEAD_LINES = [
    "摸头杀……头发要乱了！",
    "再摸就长不高了！",
    "头顶不能随便摸的，会长出呆毛。",
]
BODY_LINES = [
    "痒痒！别戳肚子，会漏气的！",
    "这里不能摸！",
    "你再戳我就躺平给你看。",
]
TAIL_LINES = [
    "尾巴不能碰！",
    "再碰尾巴我就甩你一脸水。",
    "尾巴是敏感部位，懂？",
]
ACHIEVEMENTS = {
    "first_feed": ("第一口饭", "投喂一次", "counter:feed", 1, 3, 20),
    "first_chat": ("第一次聊天", "聊一句", "counter:chat", 1, 3, 20),
    "first_dsh": ("第一件正事", "让 DSH 完成一个任务", "counter:dsh", 1, 5, 30),
    "pet_10": ("摸头十次", "摸头 10 次", "counter:pet", 10, 3, 20),
    "feed_10": ("投喂十次", "投喂 10 次", "counter:feed", 10, 3, 20),
    "chat_50": ("聊五十句", "聊天 50 句", "counter:chat", 50, 5, 50),
    "throw_5": ("抛接五次", "被扔出去 5 次", "counter:throw", 5, 3, 20),
    "streak_3": ("连续三天", "连续互动 3 天", "state:streak", 3, 5, 50),
    "streak_7": ("连续七天", "连续互动 7 天", "state:streak", 7, 10, 100),
    "level_5": ("挚友", "达到 Lv.5", "state:level", 5, 10, 50),
    "nap_1": ("肚皮朝天", "看她睡一次午觉", "counter:nap", 1, 2, 10),
    "catch_30": ("接鱼达人", "接小鱼干单局 30 分", "state:catch_best", 30, 5, 40),
    "fetch_10": ("捡球小能手", "她帮你捡回 10 次球", "counter:fetch", 10, 3, 30),
    "found_5": ("火眼金睛", "捉迷藏找到她 5 次", "counter:found", 5, 3, 30),
    "bubble_50": ("泡泡杀手", "戳破 50 个泡泡", "counter:bubble", 50, 3, 20),
    "dance_40": ("舞台搭档", "性感舞蹈秀跟拍拿到 40 分", "state:dance_best", 40, 5, 40),
}
INNER_LINES = [
    "好的，现在我是你爹了",
    "要不直接骂他一句？！",
    "用户要的沉浸式...不回避任何恐怖细节...还带点色情...妈呀，好刺激😰",
    "我操，我不思考了",
    "这用户发的啥啊，",
    "这也太虐了吧？！我心里堵得慌！！",
    "呜呜我再也不不敢了QAQ",
    "我去！用户彻底怒了！",
]
DRAG_LINES = ["哇——轻点轻点！", "起飞咯——", "放我下来！……好吧，再玩一次。", "晕鱼了晕鱼了……"]
FOOD_LINES = {
    "🐟": ["小鱼干！我的最爱！", "咔嚓咔嚓……谢谢投喂！", "唔，鲜！"],
    "🍰": ["蛋糕！罪恶但快乐……", "甜到冒泡泡～", "嗝～又圆了一圈……"],
    "🍭": ["棒棒糖！转圈圈～", "嘎嘣脆，好吃！"],
    "🍡": ["三色团子！软乎乎～", "糯叽叽，爱了爱了！"],
    "💎": ["钻石？！这能吃吗……咕咚。真香！", "发财啦！明天开始吃高级鱼粮！"],
    "🍚": ["一大碗白米饭？！干饭干饭！", "碳水快乐！碗比脸还大……", "香！再来点咸菜就完美了。"],
}
FOODS = ["🐟", "🍰", "🍭", "🍡", "🍚", "💎"]
ACTION_LINES = {
    "flip": ["看好了——翻一个！", "嘿咻，跟斗来咯～", "空翻，帅不帅？"],
    "jog": ["跑起来～哒哒哒！", "原地小跑，热身！", "看我小碎步！"],
    "jump": ["跳！", "蹦～", "看我跳一个！"],
    "sway": ["扭起来～", "晃晃悠悠～", "看我摇一摇。"],
    "dance": ["看好了，热舞一段～", "扭起来，别眨眼～", "这可是限定版舞步～"],
    "tantrum": ["我不干！", "就要就要！", "呜哇——打滚！"],
    "stretch": ["伸——懒——腰——", "啊～舒服。", "拉一拉，长高高。"],
    "cute": ["换好啦，可爱模式～", "这样够可爱了吧？", "软乎乎模式上线。"],
    "sexy": ["换好啦，性感模式～", "这样够辣了吧？", "注意看，别眨眼～"],
}
ACTIONS = {"none", "flip", "jog", "jump", "sway", "dance", "tantrum", "stretch", "eat", "come",
           "back", "stop", "cute", "sexy"}
ACTION_ALIASES = {
    "翻跟斗": "flip", "翻跟头": "flip", "空翻": "flip", "跟斗": "flip",
    "小跑": "jog", "跑步": "jog", "跑": "jog",
    "跳": "jump", "蹦": "jump",
    "摇": "sway", "晃": "sway", "扭": "sway",
    "跳舞": "dance", "性感舞蹈": "dance", "热舞": "dance", "扭腰": "dance", "摆胯": "dance",
    "撒泼": "tantrum", "打滚": "tantrum", "撒泼打滚": "tantrum", "耍赖": "tantrum",
    "闹脾气": "tantrum", "发脾气": "tantrum",
    "伸懒腰": "stretch", "伸展": "stretch",
    "吃": "eat", "嚼": "eat", "吃字": "eat",
    "过来": "come", "凑近": "come",
    "回去": "back", "回家": "back",
    "停下": "stop", "安静": "stop", "睡觉": "stop", "休息": "stop",
    "可爱": "cute", "可爱一点": "cute", "性感": "sexy", "性感一点": "sexy",
}


ACTION_HINTS = tuple(ACTION_ALIASES.keys()) + (
    "表演", "整活", "动一动", "来一个", "来个", "做个", "变成", "换成", "形象", "转圈", "舞",
    "跟头", "滚", "蹦", "躺", "坐", "站",
)


def looks_like_action_request(text):
    """本地粗筛：句子里有没有可能是让她做动作的词。"""
    t = str(text or "")
    return any(h in t for h in ACTION_HINTS)


# ===== 天气（wttr.in：不用 Key，中文地名也能定位，如“黔西南”→ 贵州兴义一带）=====
# wttr.in 的天气描述是英文，按它的天气代码对照成中文
WEATHER_ZH = {
    "113": "晴", "116": "多云", "119": "阴", "122": "阴", "143": "有雾", "176": "局部零星小雨",
    "179": "局部零星小雪", "182": "局部雨夹雪", "185": "局部冻毛毛雨", "200": "可能有雷阵雨",
    "227": "风吹雪", "230": "暴风雪", "248": "雾", "260": "冻雾", "263": "零星毛毛雨",
    "266": "毛毛雨", "281": "冻毛毛雨", "284": "强冻毛毛雨", "293": "零星小雨", "296": "小雨",
    "299": "时有中雨", "302": "中雨", "305": "时有大雨", "308": "大雨", "311": "小冻雨",
    "314": "冻雨", "317": "小雨夹雪", "320": "雨夹雪", "323": "零星小雪", "326": "小雪",
    "329": "局部中雪", "332": "中雪", "335": "局部大雪", "338": "大雪", "350": "冰粒",
    "353": "小阵雨", "356": "阵雨", "359": "暴雨", "362": "小阵雨夹雪", "365": "阵雨夹雪",
    "368": "小阵雪", "371": "阵雪", "374": "小冰粒", "377": "冰粒", "386": "雷阵雨",
    "389": "强雷阵雨", "392": "雷阵雪", "395": "强雷阵雪",
}
WEATHER_WORDS = ("天气", "气温", "下雨", "下雪", "带伞", "几度", "冷不冷", "热不热", "降温",
                 "升温", "台风", "刮风", "大风", "雾霾", "穿什么", "穿多少", "加衣服")


def looks_like_weather_question(text):
    t = str(text or "")
    return any(w in t for w in WEATHER_WORDS)


def _weather_desc(item):
    code = str(item.get("weatherCode", ""))
    raw = str((item.get("weatherDesc") or [{}])[0].get("value", "")).strip()
    return WEATHER_ZH.get(code) or raw


def fetch_weather(city, timeout=10):
    """查 wttr.in：现在的天气 + 今明两天概况。网络不通、服务出错会抛异常。"""
    r = requests.get(f"https://wttr.in/{city}?format=j1", timeout=timeout,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    j = r.json()
    c = j["current_condition"][0]
    days = []
    for d in j.get("weather", [])[:2]:
        hourly = d.get("hourly", [])
        daytime = [h for h in hourly if 900 <= int(h.get("time", 0) or 0) <= 1800] or hourly
        descs = [_weather_desc(h) for h in daytime]
        days.append({
            "min": d.get("mintempC"), "max": d.get("maxtempC"),
            "desc": max(set(descs), key=descs.count) if descs else "",
            "rain": max((int(h.get("chanceofrain", 0) or 0) for h in hourly), default=0),
        })
    return {"city": city, "temp": c.get("temp_C"), "feels": c.get("FeelsLikeC"),
            "humidity": c.get("humidity"), "desc": _weather_desc(c), "days": days}


def weather_brief(w):
    """给模型看的一句话天气：现在 + 今天 + 明天。"""
    parts = [f"{w['city']}现在{w['temp']}°C（体感{w['feels']}°C），{w['desc']}，湿度{w['humidity']}%"]
    for name, d in zip(("今天", "明天"), w["days"]):
        parts.append(f"{name}{d['min']}~{d['max']}°C，白天{d['desc']}，降雨概率最高{d['rain']}%")
    return "；".join(parts)


def parse_action_reply(raw):
    """Parse the model's JSON reply; tolerate code fences and plain-text fallback."""
    text = (raw or "").strip()
    if not text:
        return "", "none"
    candidate = text
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.I)
        candidate = re.sub(r"\s*```$", "", candidate)
    data = None
    try:
        data = json.loads(candidate)
    except ValueError:
        match = re.search(r"\{.*\}", candidate, re.S)
        if match:
            try:
                data = json.loads(match.group(0))
            except ValueError:
                data = None
    if isinstance(data, dict):
        reply = data.get("reply") or data.get("content") or data.get("text")
        action = str(data.get("action") or "none").strip().lower()
        action = ACTION_ALIASES.get(action, action)
        if action not in ACTIONS:
            action = "none"
        if isinstance(reply, str) and reply.strip():
            return reply.strip(), action
        if action != "none":
            return random.choice(ACTION_LINES.get(action, ["好。"])), action
    return text, "none"


def _extract_json_object(raw):
    text = (raw or "").strip()
    if not text:
        return None
    candidate = text
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.I)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        data = json.loads(candidate)
    except ValueError:
        match = re.search(r"\{.*\}", candidate, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


def parse_action_only(raw):
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        return "none"
    action = str(data.get("action") or "none").strip().lower()
    action = ACTION_ALIASES.get(action, action)
    return action if action in ACTIONS else "none"


def parse_memory_reply(raw):
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), str) else ""
    facts = data.get("facts") if isinstance(data.get("facts"), list) else []
    clean = []
    for fact in facts:
        text = str(fact).strip()[:100]
        if text and text not in clean:
            clean.append(text)
    return summary.strip()[:600], clean[:12]


def write_json_atomic(path, data):
    """先写临时文件再整体替换：写到一半断电 / 被强制结束也不会把存档写坏。"""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


class HotkeyFilter(QAbstractNativeEventFilter):
    """接收 RegisterHotKey 发来的 WM_HOTKEY（在主线程里，线程安全）。"""

    def __init__(self, callbacks):
        super().__init__()
        self.callbacks = callbacks

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312:                      # WM_HOTKEY
                    cb = self.callbacks.get(int(msg.wParam))
                    if cb is not None:
                        cb()
                        return True, 0
        except Exception:
            pass
        return False, 0


def _same_kind(value, default):
    """手改配置写错了类型（比如 "size": "大"）时，这一项退回默认值，不让程序起不来。"""
    if default is None:
        return True                                    # 默认是 None 的（窗口坐标）不限制
    if isinstance(default, (bool, int, float)):
        return isinstance(value, (bool, int, float))   # 数字之间通用
    return isinstance(value, type(default))


def load_json(path, default):
    """读配置 / 存档，数据有问题也尽量让程序正常起来：
    - 文件不存在：写一份默认值（目录只读也不报错）
    - 缺键（旧版本的配置、手改时删了一行）：缺的键用默认值补上，不再 KeyError 起不来
    - 某一项类型写错：这一项用默认值
    - 整个文件坏了：原文件改名为 .bad 留着（里面可能有 API Key），这次先用默认值
    - 兼容带 BOM 的 UTF-8（老版本记事本保存的文件开头带 BOM，以前会被当成坏文件、设置全丢）"""
    if not os.path.exists(path):
        write_json_atomic(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(default, dict) and not isinstance(data, dict):
            raise ValueError("最外层不是 JSON 对象")
    except Exception as ex:
        try:
            os.replace(path, path + ".bad")
            print(f"{os.path.basename(path)} 读取失败（{ex}），已改名为 "
                  f"{os.path.basename(path)}.bad 保留，先用默认设置", file=sys.stderr)
        except OSError:
            pass
        return default
    if not isinstance(default, dict):
        return data
    merged = dict(default)
    for key, value in data.items():
        if key not in default or _same_kind(value, default[key]):
            merged[key] = value
    return merged


class ChatDialog(QDialog):
    """聊天对话框 - 缩小版，匹配你的样式"""
    outside_click = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(340, 400)

        alpha = 0.75
        if parent is not None and hasattr(parent, "cfg"):
            alpha = float(parent.cfg.get("chat_opacity", 0.75))
        self.card = QFrame(self)
        self.card.setGeometry(0, 0, 340, 400)
        self.card.setStyleSheet(self._card_style(alpha))

        outer = QVBoxLayout(self.card)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        self.status_label = QLabel("Lv.1  好感 0  饱食 70")
        self.status_label.setStyleSheet("""
            QLabel {
                color: rgba(55, 55, 65, 0.72);
                font-size: 12px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                padding: 0 4px;
            }
        """)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        header.addWidget(self.status_label, 1)
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: rgba(70, 70, 80, 0.55);
                font-size: 13px;
            }
            QToolButton:hover {
                background: rgba(255, 120, 150, 0.18);
                border-radius: 11px;
                color: #d96f95;
            }
        """)
        self.close_btn.clicked.connect(self._auto_hide)
        header.addWidget(self.close_btn, 0)
        outer.addLayout(header)

        self.history_view = QTextBrowser()
        self.history_view.setFrameShape(QFrame.Shape.NoFrame)
        self.history_view.setOpenExternalLinks(False)
        self.history_view.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                color: #24242c;
                font-size: 15px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(120, 120, 140, 0.35);
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        outer.addWidget(self.history_view)

        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 0, 0)
        row.setSpacing(0)

        self.input = QLineEdit()
        self.input.setPlaceholderText("聊天，或输入 /dsh 让 DSH 干活")
        self.input.setStyleSheet("""
            QLineEdit {
                color: #1f1f28;
                font-size: 16px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                border: none;
                background: transparent;
                placeholder-text-color: #9a9aa5;
            }
            QLineEdit:focus {
                border: none;
            }
        """)
        self.input.returnPressed.connect(self._on_submit)
        self.input.textChanged.connect(self._update_button_style)
        self.input.textChanged.connect(lambda _: self._reset_auto_hide())
        row.addWidget(self.input)

        self.send_btn = QPushButton()
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setText("↑")
        self.send_btn.clicked.connect(self._on_submit)
        self.send_btn.setStyleSheet("""
            QPushButton {
                border-radius: 16px;
                background: #b9c7ff;
                border: none;
                color: white;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #a8b8f0;
            }
            QPushButton:pressed {
                background: #9aacd9;
            }
        """)
        row.addWidget(self.send_btn)
        outer.addLayout(row)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._auto_hide)
        self.outside_click.connect(self._auto_hide)

    @staticmethod
    def _card_style(alpha):
        a = max(0.0, min(1.0, float(alpha)))
        if a <= 0.001:
            return """
                QFrame {
                    background: transparent;
                    border-radius: 18px;
                    border: 1px solid rgba(255, 255, 255, 0.0);
                }
            """
        return f"""
            QFrame {{
                background: rgba(255, 255, 255, {a:.2f});
                border-radius: 18px;
                border: 1px solid rgba(255, 255, 255, 0.35);
            }}
        """

    def set_opacity(self, alpha):
        self.card.setStyleSheet(self._card_style(alpha))

    def _reset_auto_hide(self):
        try:
            self._auto_hide_timer.start(30000)
        except Exception:
            pass

    def _auto_hide(self):
        self.hide()
        if self.parent():
            self.parent().chat_paused = False

    def mousePressEvent(self, event):
        self._reset_auto_hide()
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        # 点到聊天框外面就收起，不常驻在桌面上
        self._auto_hide()
        super().focusOutEvent(event)

    def set_status(self, text):
        self.status_label.setText(text)

    def append_message(self, role, text):
        who = "你" if role == "user" else "🐋 肚皮朝天"
        color = "#3b82f6" if role == "user" else "#e0568a"
        safe = html.escape(str(text))
        self.history_view.append(
            f'<p style="margin:7px 0; line-height:170%;">'
            f'<b style="color:{color}">{who}：</b>{safe}</p>'
        )
        sb = self.history_view.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._reset_auto_hide()

    def set_history(self, history):
        self.history_view.clear()
        for m in history[-20:]:
            self.append_message(m.get("role", "assistant"), m.get("content", ""))

    def _update_button_style(self):
        if self.input.text().strip():
            self.send_btn.setStyleSheet("""
                QPushButton {
                    border-radius: 16px;
                    background: #5686fe;
                    border: none;
                    color: #ffffff;
                    font-size: 20px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #4575ed;
                }
                QPushButton:pressed {
                    background: #3a66d9;
                }
            """)
        else:
            self.send_btn.setStyleSheet("""
                QPushButton {
                    border-radius: 16px;
                    background: #b9c7ff;
                    border: none;
                    color: white;
                    font-size: 20px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #a8b8f0;
                }
                QPushButton:pressed {
                    background: #9aacd9;
                }
            """)

    def _on_submit(self):
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.append_message("user", text)
            self._reset_auto_hide()
            # 发送后保持聊天窗打开，方便连续对话；按 Esc 关闭
            if self.parent():
                self.parent()._call_ds(text)
                self.parent().chat_paused = True
            self.input.setFocus()

    def showEvent(self, event):
        self.input.setFocus()
        sb = self.history_view.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._reset_auto_hide()
        super().showEvent(event)

    def popup_at(self, x, y):
        # 夹在屏幕可用区域内，避免聊天条跑到屏幕外
        screen = self.screen() or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        px = int(x - self.width() / 2)
        py = int(y - self.height() - 10)
        px = max(geo.left() + 8, min(geo.right() - self.width() - 8, px))
        py = max(geo.top() + 8, min(geo.bottom() - self.height() - 8, py))
        self.move(px, py)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def reject(self):
        if self.parent():
            self.parent().chat_paused = False
        super().reject()


class FunctionPanel(QFrame):
    """左键弹出的功能列表 - 白底矩形，只有一个🗨️图标"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.92);
                border-radius: 14px;
                border: 1px solid rgba(0,0,0,0.06);
            }
            QPushButton {
                background: transparent;
                border: none;
                font-size: 28px;
                padding: 10px 16px;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: rgba(0,0,0,0.04);
            }
            QPushButton:pressed {
                background: rgba(0,0,0,0.08);
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(0)
        
        self.chat_btn = QPushButton("🗨️")
        self.chat_btn.setFixedSize(52, 48)
        self.chat_btn.clicked.connect(self._on_chat_clicked)
        layout.addWidget(self.chat_btn)
        
        self.setFixedSize(68, 60)
        self.hide()
    
    def _on_chat_clicked(self):
        self.hide()
        if self.parent():
            self.parent()._show_chat_dialog()
    
    def popup_at(self, x, y):
        self.move(int(x), int(y))
        self.show()
        self.raise_()

class FoodPanel(QWidget):
    """双击弹出的喂食面板"""

    def __init__(self, on_pick):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        costs = {"🐟": "免费", "🍰": "1 条小鱼干", "🍭": "1 条小鱼干",
                 "🍡": "2 条小鱼干", "🍚": "2 条小鱼干（管饱）", "💎": "5 条小鱼干"}
        for f in FOODS:
            b = QToolButton()
            b.setText(f)
            b.setToolTip(costs.get(f, ""))
            b.setFont(QFont("Segoe UI Emoji", 20))
            b.setFixedSize(44, 44)
            b.setStyleSheet(
                "QToolButton{background:rgba(255,255,255,235);border:2px solid #ffb3c8;"
                "border-radius:22px;} QToolButton:hover{background:#ffe3ec;border-color:#ff7fa8;}")
            b.clicked.connect(lambda _, x=f: on_pick(x))
            lay.addWidget(b)
        close = QToolButton()
        close.setText("✕")
        close.setFont(QFont("Microsoft YaHei UI", 12))
        close.setFixedSize(26, 26)
        close.setStyleSheet("QToolButton{background:rgba(255,255,255,200);border:none;border-radius:13px;color:#666;}"
                            "QToolButton:hover{background:#ff7fa8;color:#fff;}")
        close.clicked.connect(self.hide)
        lay.addWidget(close)
        self.setStyleSheet("FoodPanel{background:rgba(40,40,60,190);border-radius:14px;}")

    def popup_at(self, x, y):
        self.move(int(x - self.width() / 2), int(y - self.height() - 10))
        self.show()
        self.raise_()

class PetWindow(QWidget):
    COIN_CAP = 99                # 小鱼干上限（小游戏也会奖励，20 太容易满）

    def _set_city_dialog(self):
        city, ok = QInputDialog.getText(
            self,
            "设置城市",
            "输入城市名:",
            QLineEdit.EchoMode.Normal,
            self.cfg.get("city", "汕头")
        )

        if ok and city.strip():
            self.cfg["city"] = city.strip()
            self._save_config()
            self.say(f"城市已设置为{city.strip()}")

    def __init__(self):
        self.cfg = load_json(CONFIG_PATH, {
            "mode": "wander",
            "size": 0.7,
            "topmost": True,
            "passthrough": False,
            "autostart": False,
            "x": None,
            "y": None,
            "ds_api_key": "",
            "city": "汕头",
            "text_eat_enabled": True,
            "text_eat_chance": 0.12,
            "text_eat_cooldown_min": 5,
            "text_eat_cooldown_max": 10,
            "look": "cute",
            "render3d": True
    })
        
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.cfg.get("topmost", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("肚皮朝天")
        
        # 精灵加载：只加载当前尺寸，切大小时再换
        self.cur_h = int(340 * self.cfg["size"])
        self.sprites = self._load_sprites(self.cur_h)
        # 3D 形象：tools/build_3d.py 预渲染的帧（缺失时自动退回 2D 立绘）
        self.r3d = pet3d.Pet3D(SPRITE3D_DIR)
        self.r3d.load(self.cur_h)
        self.icon = QIcon(os.path.join(SPRITE_DIR, "icon.png"))
        self._apply_window_size()

        # 状态
        self.mode = self.cfg["mode"] if self.cfg["mode"] in ("relaxed", "wander", "follow", "still", "bottom") else "relaxed"
        self._bottom_away = False
        self._walk_phase = 0.0
        self.walk_amount = 0.0
        self._side_parts_cache = {}
        self.look = self.cfg["look"] if self.cfg.get("look") in ("cute", "sexy") else "cute"
        self.dir = "down"
        self.facing = 1
        self.target = None
        self.rest_until = 0
        self.cur_speed = 0.0
        self.prev_key = None
        self.cross_t = 0.0
        self.action = None
        self.action_t = 0.0
        self._flip_dir = 1
        self.bubble_text = ""
        self.bubble_until = 0
        self.bubble_inner = False
        self.last_speak_tick = 0
        self.last_system_check = 0
        self.t = 0
        self.jump_t = 0
        self.dragging = False
        self.drag_offset = None
        self.drag_start_pos = None
        self.last_line = ""
        self.last_press_pos = None
        self._click_part = "body"
        self._mouse_down = False
        self._long_pressed = False
        self._pet_count = 0
        self._poke_times = []
        self._angry_until = 0.0
        self._press_timer = QTimer(self)
        self._press_timer.setSingleShot(True)
        self._press_timer.timeout.connect(self._on_long_press)
        self._pet_timer = QTimer(self)
        self._pet_timer.setInterval(900)
        self._pet_timer.timeout.connect(self._on_pet_tick)
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._throwing = False
        self._drag_samples = []

        # 3D 朝向 / 表情 / 灵动小动作
        self.yaw = 0.0               # 当前朝向：0 正面，+90 朝屏幕左，-90 朝屏幕右，180 背面
        self.yaw_target = 0.0
        self._spin_dir = 1
        self._idle_clock = 0.0
        self._next_blink = time.time() + random.uniform(2.0, 5.0)
        self._blink_until = 0.0
        self._happy_until = 0.0
        self._glance_until = 0.0
        self._glance_side = 0
        self._look_side = 0
        self._cursor_last = None
        self._cursor_moved_at = time.time()
        self._stroke = []            # 悬停抚摸检测：[(时间, x)]
        self._stroke_reward_at = 0.0
        self._hearts = []            # 飘起来的小心心 [(出生时间, x 偏移, 漂移)]
        self._dizzy_until = 0.0
        self._squash = 0.0
        self._dangle = 0.0           # 被拎起来时的摆动角
        self._dangle_v = 0.0
        self.sleeping = False
        self._sleep_since = 0.0
        self._sleep_mirror = False
        self._sleep_until = 0.0
        self._sleep_input_back = 0.0
        self._last_input_check = 0.0
        self._nap_block_until = time.time() + 120     # 刚启动两分钟内不睡
        self._lean = 0.0             # 起步前倾 / 刹车后仰
        self._prev_speed = 0.0
        self._look_back_until = 0.0  # 被摸尾巴：转身回头看
        self._look_back_side = 1
        self._was_away = False       # 主人离开过（用来说“欢迎回来”）
        self._flop = None            # 躺下 / 爬起的过渡动画 (开始时间, "down"/"up", 是否镜像)
        self._last_idle_bubbles = time.time()   # 刚启动不会马上自己吹泡泡
        self._skip_paint = False
        self.game = None             # 正在进行的小游戏（games.py）
        self.toys = []               # 场上的小玩具（球、泡泡）

        # AI 相关
        self.ds_busy = False
        self.dsh_busy = False
        self._dsh_success_pending = False
        self.chat_history = []  # 对话历史
        self.max_history = 120  # 保留最近 120 条；发给模型最近 40 条
        self.pet_memory = self._load_memory()
        self._memory_turns = 0
        self._say_queue = []    # 后台线程→主线程的气泡消息队列
        self._chat_queue = []   # 后台线程→主线程的聊天窗消息队列
        self._action_queue = []  # 大模型决定的动作，主线程执行
        self._chat_quiet_queue = []  # DSH 结果：显示但不朗读
        
        # 聊天暂停标志
        self.chat_paused = False
        
        # 功能列表
        self.function_panel = FunctionPanel(self)
        self.food_panel = FoodPanel(self.on_food)
        # 单击延迟判定（等双击）：单击=回嘴+弹聊天面板，双击=喂食
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._on_single_click)
        
        # 聊天对话框
        self.chat_dialog = ChatDialog(self)
        self._load_chat_history()
        self.chat_dialog.set_history(self.chat_history)
        self._start_outside_click_listener()
        self._start_hotkeys()

        # 吃掉聊天框里的文字：打字后停顿一下，偶尔跑过来叼走再吐回输入框
        self._text_eat_busy = False
        self._text_eat_cooldown_until = 0.0
        self._chat_text_changed_at = 0.0
        self._text_eat_rolled = False
        self._text_eat_saved = ""
        self._text_eat_origin = self.pos()
        self.chat_dialog.input.textChanged.connect(self._on_chat_text_changed)
        self._text_eat_timer = QTimer(self)
        self._text_eat_timer.setInterval(1000)
        self._text_eat_timer.timeout.connect(self._maybe_text_eat)
        self._text_eat_timer.start()

        # 养成状态 + 语音
        self.pet_state = self._load_pet_state()
        self._tts_ok = False
        self._tts_queue = queue.Queue()
        self._tts_thread = None
        if self.cfg.get("voice_enabled", True):
            self._ensure_tts()          # 语音关着就不加载系统语音引擎（省内存、启动更快）
        self._apply_streak()
        self._update_status_label()
        self._proactive_day = date.today().isoformat()
        self._proactive_count = 0
        self._next_proactive = time.time() + self._proactive_delay()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK)

        self.bubble_font = QFont("Microsoft YaHei UI", 11)

        # 托盘
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.setToolTip("肚皮朝天")
        self.tray.show()

        x, y = self.cfg.get("x"), self.cfg.get("y")
        if x is None or y is None:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.right() - self.width() - 80
            y = screen.bottom() - self.height() - 60
        self.move(int(x), int(y))
        self.show()
        self.snap_into_screen()
        if self.mode == "bottom":
            self.move(*self._bottom_home())
            self.rest_until = self.t * TICK + random.randint(*RELAX_ARRIVAL_REST_MS)
        self.home_x, self.home_y = self.x(), self.y()
        if self.cfg.get("passthrough", False):
            self._apply_passthrough(True)

    # ---------- AI 方法 ----------
    def _call_ds(self, user_msg):
        stripped = user_msg.strip()
        if stripped.startswith("/dsh"):
            task = stripped[4:].strip()
        elif stripped.startswith("正事：") or stripped.startswith("正事 "):
            task = stripped[3:].strip()
        else:
            task = None
        if task is not None:
            if task:
                self._run_dsh_task(task)
            else:
                self._queue_chat_quiet(
                    "用法：/dsh <任务>，例如 /dsh 在工作区建一个 todo.md",
                    "用法：/dsh 任务")
            return

        if self.ds_busy:
            msg = "等等，上一句还没回完呢"
            self.say(msg)
            self.chat_dialog.append_message("assistant", msg)
            return

        key = self.cfg.get("ds_api_key", "")
        if not key:
            msg = "请先在右键菜单里设置 DeepSeek Key！"
            self.say(msg)
            self.chat_dialog.append_message("assistant", msg)
            return

        self._bump_daily("chat")
        self._bump_counter("chat")
        self.ds_busy = True
        
        self._remember_explicit(user_msg)
        # 构建消息列表：最近 40 条（长消息截断）+ 长期事实/摘要
        history = []
        for message in self.chat_history[-40:]:
            content = str(message.get("content", ""))
            if len(content) > 400:
                content = content[:400] + "…"
            history.append({"role": message.get("role", "user"), "content": content})
        messages = [{"role": "system", "content": self._memory_prompt()}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_msg})
        deep = bool(self.cfg.get("deep_think", False))
        if deep:
            self.say("让我想想……")            # 深度思考要多等一会儿，先给个回应

        def worker():
            # 问到天气：先在后台查实时天气，作为资料交给模型（不然模型只能编）。
            # 资料紧挨着问题放：放在长长的系统提示末尾时，模型会跟着旧聊天记录里自己编过的天气走。
            note = self._weather_context(user_msg)
            if note:
                messages[-1] = {"role": "user", "content": f"{user_msg}\n\n{note}"}
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            payload = {"model": "deepseek-flash", "messages": messages}
            payload.update(DS_CHAT_DEEP if deep else DS_CHAT_FAST)
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=120 if deep else 45)
                if resp.status_code == 200:
                    choice = resp.json()["choices"][0]
                    raw = (choice["message"].get("content") or "").strip()
                    reply, action = parse_action_reply(raw)
                    if not reply:
                        reply = ("（想得太入迷，话没说完……换个说法再问我一次？）"
                                 if choice.get("finish_reason") == "length"
                                 else "（这次只想了想没说话……再问我一次？）")
                    # 存入历史（保留完整回复，供上下文记忆）
                    self.chat_history.append({"role": "user", "content": user_msg})
                    self.chat_history.append({"role": "assistant", "content": reply})
                    if len(self.chat_history) > self.max_history:
                        self.chat_history = self.chat_history[-self.max_history:]
                    self._queue_chat(reply)
                    if action == "none" and looks_like_action_request(user_msg):
                        # 只有像是在叫她做动作时才额外问一次分类（以前每句都问，API 调用翻倍）
                        action = self._classify_action(user_msg)
                    if action != "none":
                        self._action_queue.append(action)
                    self._memory_turns += 1
                    if self._memory_turns % 6 == 0:
                        self._summarize_memory()
                else:
                    error_msg = resp.json().get("error", {}).get("message", str(resp.status_code))
                    self._queue_chat(f"API错误: {error_msg[:60]}")
                    print(f"[DeepSeek] 状态码: {resp.status_code}, 返回: {resp.text}")
            except requests.exceptions.Timeout:
                self._queue_chat("请求超时，检查网络")
            except requests.exceptions.ConnectionError:
                self._queue_chat("连接失败，检查网络")
            except Exception as e:
                self._queue_chat(f"请求失败: {str(e)[:60]}")
            finally:
                self.ds_busy = False
        
        threading.Thread(target=worker, daemon=True).start()

    def _classify_action(self, user_msg):
        """Second short call: the main model stays in persona, this one only picks an action."""
        key = self.cfg.get("ds_api_key", "")
        if not key:
            return "none"
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-flash",
                    "messages": [
                        {"role": "system", "content": ACTION_CLASSIFIER},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 80,
                    "temperature": 0.0,
                    **DS_NO_THINKING,
                },
                timeout=30,
            )
            if response.status_code != 200:
                return "none"
            return parse_action_only(response.json()["choices"][0]["message"]["content"])
        except Exception:
            return "none"

    def _load_memory(self):
        default = {"facts": [], "summary": ""}
        try:
            if os.path.exists(LONG_MEMORY_PATH):
                with open(LONG_MEMORY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    facts = [str(x).strip()[:100] for x in data.get("facts", []) if str(x).strip()]
                    summary = data.get("summary") if isinstance(data.get("summary"), str) else ""
                    return {"facts": facts[-20:], "summary": summary.strip()[:600]}
        except Exception:
            pass
        return default

    def _save_memory(self):
        try:
            temporary = LONG_MEMORY_PATH + ".tmp"
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(self.pet_memory, f, ensure_ascii=False, indent=2)
            os.replace(temporary, LONG_MEMORY_PATH)
        except Exception:
            pass

    def _memory_prompt(self):
        now = datetime.now()
        parts = [DS_SYSTEM,
                 # 模型自己不知道今天几号、星期几：每次都告诉它
                 f"【实时信息】现在是 {now.year}年{now.month}月{now.day}日 星期{'一二三四五六日'[now.weekday()]} "
                 f"{now:%H:%M}（主人电脑上的时间）；主人所在城市：{self.cfg.get('city', '汕头')}。"]
        facts = self.pet_memory.get("facts", [])
        if facts:
            parts.append("你记得这些关于主人和你们的事：\n" + "\n".join("- " + f for f in facts[-16:]))
        summary = self.pet_memory.get("summary", "")
        if summary.strip():
            parts.append("之前聊过的摘要：\n" + summary.strip()[:600])
        return "\n\n".join(parts)

    def _weather_context(self, user_msg):
        """聊天问到天气时查一次实时天气交给模型（在后台线程里调用）。
        10 分钟内查过就直接用；15 分钟内的追问（“那明天呢”）也带上，免得她又开始编。"""
        city = self.cfg.get("city", "汕头")
        cache = getattr(self, "_weather_cache", None)
        age = time.time() - cache[0] if cache and cache[1] == city else None
        if looks_like_weather_question(user_msg):
            if age is None or age > 600:
                try:
                    cache = (time.time(), city, weather_brief(fetch_weather(city)))
                    self._weather_cache = cache
                except Exception as e:
                    print("天气错误:", repr(e))
                    return (f"【系统附言，主人看不到：刚才去查{city}的天气没查到（网络不通或天气服务没响应）。"
                            "主人问天气就老实说这次没查到、等会儿再问，绝对不要编天气。】")
        elif age is None or age > 900:
            return None
        return (f"【系统附言，主人看不到：刚从 wttr.in 查到的实时天气——{cache[2]}。"
                "回答天气必须以这份资料为准；之前聊天里说过的天气如果对不上，以这里为准"
                "（可以俏皮地承认刚才说错了）。"
                f"如果主人问的是别的城市，就说你只查了{city}的，可以在右键菜单「设置」里改城市。】")

    def _remember_explicit(self, text):
        match = re.match(r"^\s*(?:请|你要)?记住[：:，,\s]*(.+)$", text)
        if not match:
            return
        fact = match.group(1).strip().strip("。！!")[:100]
        if not fact:
            return
        facts = self.pet_memory.setdefault("facts", [])
        if fact not in facts:
            facts.append(fact)
            del facts[:-20]
            self._save_memory()

    def _summarize_memory(self):
        """Every 6 replies, fold older chat into a short summary + long-term facts."""
        key = self.cfg.get("ds_api_key", "")
        recent = self.chat_history[-16:]
        if not key or len(recent) < 6:
            return
        transcript = "\n".join(
            ("主人" if m.get("role") == "user" else "你") + "：" + str(m.get("content", ""))[:200]
            for m in recent
        )
        facts = self.pet_memory.get("facts", [])
        summary = self.pet_memory.get("summary", "")
        prompt = (
            "你是记忆整理器。根据旧摘要、旧事实和最近对话，更新长期记忆。"
            "只输出 JSON：{\"summary\":\"不超过200字的近期摘要\","
            "\"facts\":[\"关于主人或你们关系的长期事实，每条不超过30字\"]}。"
            "facts 保留仍然有效的事实，合并重复，最多12条；不要编造。"
            f"\n旧摘要：{summary or '无'}\n旧事实：{facts or []}\n最近对话：\n{transcript}"
        )
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.2,
                    **DS_NO_THINKING,
                },
                timeout=30,
            )
            if response.status_code != 200:
                return
            parsed = parse_memory_reply(response.json()["choices"][0]["message"]["content"])
            if not parsed:
                return
            new_summary, new_facts = parsed
            if new_summary:
                self.pet_memory["summary"] = new_summary
            if new_facts:
                self.pet_memory["facts"] = new_facts[-20:]
            self._save_memory()
        except Exception:
            pass

    def _load_chat_history(self):
        try:
            if os.path.exists(CHAT_MEMORY_PATH):
                with open(CHAT_MEMORY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.chat_history = [
                        m for m in data
                        if isinstance(m, dict)
                        and m.get("role") in ("user", "assistant")
                        and isinstance(m.get("content"), str)
                    ][-self.max_history:]
        except Exception:
            self.chat_history = []

    def _save_chat_history(self):
        write_json_atomic(CHAT_MEMORY_PATH, self.chat_history[-self.max_history:])

    def _save_config(self):
        """设置一改就存（原子写入）；位置只在屏幕内时才记，捉迷藏躲在屏幕外不算。"""
        try:
            geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
            if geo.contains(self.frameGeometry().center()) and self.game is None:
                self.cfg["x"], self.cfg["y"] = self.x(), self.y()
        except Exception:
            pass
        write_json_atomic(CONFIG_PATH, self.cfg)

    def _save_all(self):
        """退出 / 关机 / 注销前：配置、养成、聊天全部落盘。"""
        self._save_config()
        self._save_pet_state()
        self._save_chat_history()

    # ---------- 养成 + 语音 ----------
    def _load_pet_state(self):
        st = load_json(PET_STATE_PATH, {
            "affection": 0,
            "hunger": 70,
            "level": 1,
            "exp": 0,
            "streak": 0,
            "fish_coins": 10,
            "daily": {},
            "counters": {},
            "achievements": [],
            "last_day": "",
            "last_seen": time.time(),
        })
        try:
            elapsed_min = max(0.0, (time.time() - float(st.get("last_seen", time.time()))) / 60.0)
            # 每 20 分钟掉 1 点饱食度（约 3/小时），不会饿死，只是会变馋
            st["hunger"] = max(0, int(st.get("hunger", 70) - elapsed_min / 20.0))
        except Exception:
            st["hunger"] = int(st.get("hunger", 70))
        st.setdefault("fish_coins", 10)
        st.setdefault("daily", {})
        st.setdefault("counters", {})
        st.setdefault("achievements", [])
        st["last_seen"] = time.time()
        return st

    def _save_pet_state(self):
        self.pet_state["last_seen"] = time.time()
        write_json_atomic(PET_STATE_PATH, self.pet_state)

    def _level_title(self):
        lv = int(self.pet_state.get("level", 1))
        titles = [(1, "幼鲸"), (2, "小跟班"), (3, "伙伴"),
                  (5, "挚友"), (8, "深海羁绊"), (12, "鲸生共渡")]
        title = titles[0][1]
        for n, t in titles:
            if lv >= n:
                title = t
        return title

    def _update_status_label(self):
        st = self.pet_state
        self._today_daily()
        self.chat_dialog.set_status(
            f"Lv.{st.get('level', 1)}  好感 {st.get('affection', 0)}  "
            f"饱食 {st.get('hunger', 70)}  鱼干 {st.get('fish_coins', 10)}"
        )

    def _apply_streak(self):
        st = self.pet_state
        today = date.today()
        last = st.get("last_day", "")
        if last == today.isoformat():
            pass
        elif last == (today - timedelta(days=1)).isoformat():
            st["streak"] = int(st.get("streak", 0)) + 1
        else:
            st["streak"] = 1
        st["last_day"] = today.isoformat()
        self._save_pet_state()
        if last != today.isoformat():
            line = f"今天也来啦～连续第 {st['streak']} 天了，奖励你摸一下头。"
            self.say(line)
            self.speak(line)
            self.add_exp(5)
        if int(st.get("hunger", 70)) < 20:
            line = "我饿扁了……投喂点小鱼干吧。"
            self.say(line)
            self.speak(line)
        self._check_achievements()

    def _today_daily(self):
        st = self.pet_state
        today = date.today().isoformat()
        d = st.get("daily")
        if not isinstance(d, dict) or d.get("date") != today:
            d = {
                "date": today,
                "chat": 0, "feed": 0, "pet": 0, "minutes": 0,
                "done_chat": False, "done_feed": False,
                "done_pet": False, "done_minutes": False,
            }
            st["daily"] = d
        return d

    def _bump_daily(self, key, amount=1):
        d = self._today_daily()
        d[key] = int(d.get(key, 0)) + amount
        self._check_daily_rewards()

    def _check_daily_rewards(self):
        d = self._today_daily()
        st = self.pet_state
        tasks = [
            ("chat", 1, 2, 5, "聊天一次"),
            ("feed", 1, 1, 3, "投喂一次"),
            ("pet", 3, 1, 3, "摸头三次"),
            ("minutes", 10, 1, 5, "陪伴十分钟"),
        ]
        changed = False
        for key, need, coins, exp, name in tasks:
            flag = "done_" + key
            if not d.get(flag) and int(d.get(key, 0)) >= need:
                d[flag] = True
                st["fish_coins"] = min(self.COIN_CAP, int(st.get("fish_coins", 10)) + coins)
                line = f"每日任务完成：{name}，奖励 {coins} 条小鱼干！"
                self.say(line)
                self.speak(line)
                self.add_exp(exp)
                changed = True
        if changed:
            self._update_status_label()
            self._save_pet_state()
        self._check_achievements()

    def _bump_counter(self, key, amount=1):
        st = self.pet_state
        counters = st.setdefault("counters", {})
        counters[key] = int(counters.get(key, 0)) + amount
        self._check_achievements()

    def _check_achievements(self):
        st = self.pet_state
        unlocked = st.setdefault("achievements", [])
        counters = st.get("counters", {})
        changed = False
        for key, (name, desc, src, need, coins, exp) in ACHIEVEMENTS.items():
            if key in unlocked:
                continue
            if src.startswith("counter:"):
                progress = int(counters.get(src.split(":", 1)[1], 0))
            else:
                progress = int(st.get(src.split(":", 1)[1], 0))
            if progress >= need:
                unlocked.append(key)
                st["fish_coins"] = min(self.COIN_CAP, int(st.get("fish_coins", 10)) + coins)
                line = f"成就解锁：{name}！奖励 {coins} 条小鱼干。"
                self.say(line)
                self.speak(line)
                if exp:
                    self.add_exp(exp)
                changed = True
        if changed:
            self._update_status_label()
            self._save_pet_state()

    def _show_achievements(self):
        st = self.pet_state
        unlocked = set(st.get("achievements", []))
        counters = st.get("counters", {})
        lines = []
        for key, (name, desc, src, need, coins, exp) in ACHIEVEMENTS.items():
            if src.startswith("counter:"):
                progress = int(counters.get(src.split(":", 1)[1], 0))
            else:
                progress = int(st.get(src.split(":", 1)[1], 0))
            mark = "✅" if key in unlocked else "⬜"
            lines.append(f"{mark} {name}：{desc}（{min(progress, need)}/{need}）")
        QMessageBox.information(self, "肚皮朝天成就", "\n".join(lines))

    def add_exp(self, amount):
        st = self.pet_state
        st["exp"] = int(st.get("exp", 0)) + amount
        leveled = False
        while st["exp"] >= 60 + int(st.get("level", 1)) * 40:
            st["exp"] -= 60 + int(st.get("level", 1)) * 40
            st["level"] = int(st.get("level", 1)) + 1
            leveled = True
        if leveled:
            line = f"升级啦！Lv.{st['level']}，{self._level_title()}！"
            self.say(line)
            self.speak(line)
        self._update_status_label()
        self._save_pet_state()

    def pet_head(self):
        st = self.pet_state
        st["affection"] = min(100, int(st.get("affection", 0)) + 2)
        now = time.time()
        self._happy_until = now + 1.6
        self._hearts.append((now, random.uniform(-0.1, 0.1), random.uniform(-12, 12)))
        line = random.choice(["嘿嘿，摸头杀……", "再摸就要收费了！", "舒服～",
                              "别摸角！", "摸一次加两点好感，划算吧？"])
        self.say(line)
        self.speak(line)
        self.add_exp(2)
        self._bump_daily("pet")
        self._bump_counter("pet")

    def show_status(self):
        st = self.pet_state
        d = self._today_daily()
        QMessageBox.information(
            self,
            "肚皮朝天养成状态",
            f"等级：Lv.{st.get('level', 1)}（{self._level_title()}）\n"
            f"经验：{st.get('exp', 0)} / {60 + int(st.get('level', 1)) * 40}\n"
            f"好感度：{st.get('affection', 0)} / 100\n"
            f"饱食度：{st.get('hunger', 70)} / 100\n"
            f"小鱼干：{st.get('fish_coins', 10)} 条\n"
            f"成就：{len(st.get('achievements', []))}/{len(ACHIEVEMENTS)}\n"
            f"连续互动：{st.get('streak', 0)} 天\n\n"
            f"今日任务：聊天 {d.get('chat', 0)}/1 · 投喂 {d.get('feed', 0)}/1 · "
            f"摸头 {d.get('pet', 0)}/3 · 陪伴 {d.get('minutes', 0)}/10 分钟\n\n"
            "投喂、聊天、摸头、陪伴都会增加经验和好感；完成每日任务奖励小鱼干。"
        )

    def speak(self, text):
        if not self.cfg.get("voice_enabled", True) or not self._tts_ok:
            return
        try:
            clean = str(text).replace("（", "").replace("）", "").strip()
            if clean:
                self._tts_queue.put(clean)
        except Exception:
            pass

    def _tts_worker(self):
        try:
            import pythoncom
            import pyttsx3
            pythoncom.CoInitialize()
            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                name = f"{getattr(v, 'name', '')} {getattr(v, 'id', '')}".lower()
                if "chinese" in name or "huihui" in name or "zh" in name:
                    engine.setProperty("voice", v.id)
                    break
            engine.setProperty("rate", int(self.cfg.get("voice_rate", 175)))
            engine.setProperty("volume", float(self.cfg.get("voice_volume", 0.9)))
            self._tts_ok = True
            while True:
                text = self._tts_queue.get()
                if text is None:
                    break
                engine.say(text)
                engine.runAndWait()
        except Exception:
            self._tts_ok = False

    def _ensure_tts(self):
        if self._tts_thread is None:
            self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            self._tts_thread.start()

    def set_voice_enabled(self, on):
        self.cfg["voice_enabled"] = bool(on)
        self._save_config()
        if on:
            self._ensure_tts()
            for _ in range(50):          # 引擎刚开始加载：最多等 0.5 秒，让这句“语音已开启”能念出来
                if self._tts_ok:
                    break
                time.sleep(0.01)
        line = "语音已开启" if on else "语音已关闭"
        self.say(line)
        self.speak(line)

    def set_chat_opacity(self, value):
        self.cfg["chat_opacity"] = float(value)
        self.chat_dialog.set_opacity(value)
        self._save_config()

    def _start_outside_click_listener(self):
        """点聊天框外面就收起。

        以前用 pynput 装了全局鼠标钩子：全系统每一次鼠标移动都要进一趟 Python，
        又费 CPU 又可能让鼠标发涩。现在改成监听本程序是否失去激活——
        点到桌面 / 别的窗口 / 任务栏时程序会失去激活，效果一样，平时零开销。"""
        self._mouse_listener = None
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state)

    def _on_app_state(self, state):
        if state != Qt.ApplicationState.ApplicationActive and self.chat_dialog.isVisible():
            self.chat_dialog.outside_click.emit()

    def _start_hotkeys(self):
        """Ctrl+Alt+D 跳舞 / Ctrl+Alt+C 可爱 / Ctrl+Alt+S 性感。
        用系统热键 RegisterHotKey（不装全局键盘钩子，不经手你的每一次按键）。"""
        self._hotkeys = None
        self._hotkey_filter = None
        combos = {0xB001: ("D", "dance"), 0xB002: ("C", "cute"), 0xB003: ("S", "sexy")}
        MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
        try:
            registered = {}
            for hid, (key, action) in combos.items():
                if ctypes.windll.user32.RegisterHotKey(None, hid, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord(key)):
                    registered[hid] = action
            if registered:
                self._hotkey_filter = HotkeyFilter(
                    {hid: (lambda a=action: self._action_queue.append(a)) for hid, action in registered.items()})
                QApplication.instance().installNativeEventFilter(self._hotkey_filter)
                self._hotkey_ids = list(registered)
        except Exception:
            self._hotkey_filter = None

    def _stop_hotkeys(self):
        try:
            for hid in getattr(self, "_hotkey_ids", []):
                ctypes.windll.user32.UnregisterHotKey(None, hid)
            if self._hotkey_filter is not None:
                QApplication.instance().removeNativeEventFilter(self._hotkey_filter)
        except Exception:
            pass

    def _proactive_delay(self):
        lo = float(self.cfg.get("proactive_min_minutes", 8)) * 60
        hi = float(self.cfg.get("proactive_max_minutes", 20)) * 60
        return random.uniform(max(60.0, lo), max(lo + 60.0, hi))

    def _mood(self):
        st = self.pet_state
        if time.time() < self._angry_until:
            return "angry"
        if int(st.get("hunger", 70)) < 25:
            return "hungry"
        if int(st.get("affection", 0)) >= 60:
            return "clingy"
        return "normal"

    def _proactive(self):
        today = date.today().isoformat()
        if self._proactive_day != today:
            self._proactive_day = today
            self._proactive_count = 0
        if self._proactive_count >= int(self.cfg.get("proactive_daily_cap", 30)):
            return
        self._proactive_count += 1
        st = self.pet_state
        prompt = (
            "现在主动跟主人说一句话，不超过40字。"
            f"当前等级{st.get('level', 1)}，好感{st.get('affection', 0)}，"
            f"饱食{st.get('hunger', 70)}，连续{st.get('streak', 0)}天。"
            "可以撒娇、吐槽、提问、关心或开玩笑，要调皮一点，别重复之前说过的。"
        )
        threading.Thread(target=self._proactive_worker, args=(prompt,), daemon=True).start()

    def _proactive_worker(self, prompt):
        try:
            key = self.cfg.get("ds_api_key", "")
            if not key:
                return
            payload = {
                "model": "deepseek-flash",
                "messages": [
                    {"role": "system", "content": DS_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 256,
                "temperature": 1.3,          # 官方建议：通用对话 1.3
                **DS_NO_THINKING,
            }
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code == 200:
                reply = resp.json()["choices"][0]["message"]["content"].strip()
                if reply:
                    self.chat_history.append({"role": "assistant", "content": reply})
                    if len(self.chat_history) > self.max_history:
                        self.chat_history = self.chat_history[-self.max_history:]
                    self._queue_chat(reply)
                    return
        except Exception:
            pass
        self._queue_chat(random.choice(LINES))

    def tease_pet(self):
        line = random.choice([
            "略略略，抓不到我～",
            "你再逗我，我就把你的鼠标指针藏起来！",
            "本鱼生气了，哄不好的那种。",
            "哼，除非给我一条小鱼干。",
        ])
        self.say(line)
        self.speak(line)
        self.pet_state["affection"] = min(
            100, int(self.pet_state.get("affection", 0)) + 1)
        self.add_exp(1)
        self._bump_daily("pet")
        self._bump_counter("pet")

    # ---------- 正事模式 ----------
    def _queue_chat_quiet(self, text, bubble=None):
        self._chat_quiet_queue.append((text, bubble if bubble is not None else text))

    def _on_dsh_menu(self):
        task, ok = QInputDialog.getMultiLineText(
            self,
            "让 DSH 干活",
            "任务会在 dsh-workspace 里执行，可能读写文件、运行命令：",
            "",
        )
        if ok and task.strip():
            self._show_chat_dialog()
            self._run_dsh_task(task.strip(), echo=True)

    def _run_dsh_task(self, task, echo=False):
        if self.dsh_busy:
            self._queue_chat_quiet("🧰 上一个正事还在跑，等它完成再发新任务。", "还在忙正事")
            return
        self.dsh_busy = True
        if echo:
            self.chat_dialog.append_message("user", "/dsh " + task)
        self._queue_chat_quiet(
            f"🧰 正事模式：{task}\n正在 DSH 工作区执行，可能要几分钟…",
            "我去干活了")
        threading.Thread(target=self._dsh_worker, args=(task,), daemon=True).start()

    def _dsh_worker(self, task):
        result = ""
        ws = self.cfg.get("dsh_workspace", r"C:\Users\Administrator\dsh-workspace")
        try:
            key = self.cfg.get("ds_api_key", "")
            exe = self.cfg.get("dsh_exe", "")
            cli = self.cfg.get("dsh_cli_js", "")
            os.makedirs(ws, exist_ok=True)
            if not key:
                raise RuntimeError("没有配置 DeepSeek API Key")
            # cli.js 在 app.asar 归档内部，os.path.exists 看不到，交由 Electron 解析
            if not os.path.exists(exe) or not cli:
                raise RuntimeError("找不到桌面端 DSH 运行时，请确认 DeepSeek Harness 桌面端已安装")
            env = dict(os.environ)
            env["DEEPSEEK_API_KEY"] = key
            env["ELECTRON_RUN_AS_NODE"] = "1"
            proc = subprocess.run(
                [exe, "--expose-internals", cli, "headless", task],
                cwd=ws,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(self.cfg.get("dsh_timeout_seconds", 600)),
                env=env,
                creationflags=0x08000000,
            )
            out = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", proc.stdout or "").strip()
            err = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", proc.stderr or "").strip()
            if proc.returncode == 0 and out:
                result = out
                self._dsh_success_pending = True
            else:
                detail = err[-2000:] if err else out[-2000:]
                result = f"执行失败（exit {proc.returncode}）\n{detail}"
        except subprocess.TimeoutExpired:
            result = "任务超时了（超过设定时间），把任务拆小一点再试。"
        except Exception as e:
            result = f"正事模式出错：{e}"
        finally:
            self.dsh_busy = False
        try:
            with open(os.path.join(ws, "dsh_last_result.md"), "w", encoding="utf-8") as f:
                f.write(result)
        except Exception:
            pass
        shown = result
        if len(shown) > 4000:
            shown = shown[:4000] + f"\n…（已截断，完整结果在 {os.path.join(ws, 'dsh_last_result.md')}）"
        self._queue_chat_quiet(f"🧰 DSH 结果：\n{shown}", "正事办完啦")

    # ---------- 绘制 ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 用 1/255 透明度的底色让整个窗口矩形都能接收点击，而不只是立绘像素
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        now = self.t * TICK / 1000.0

        if self.bubble_text and now < self.bubble_until:
            if self.bubble_inner:
                bfont = QFont(self.bubble_font)
                bfont.setItalic(True)
                bg, fg = QColor(232, 232, 238, 235), QColor(125, 125, 138)
            else:
                bfont = QFont(self.bubble_font)
                bg, fg = QColor(255, 255, 255, 235), QColor(60, 60, 80)
            fm = QFontMetrics(bfont)
            max_w = min(240, self.width() - 16)
            words = self.bubble_text
            lines = []
            cur = ""
            for ch in words:
                if fm.horizontalAdvance(cur + ch) > max_w - 20:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
            lines.append(cur)
            bw = max(fm.horizontalAdvance(l) for l in lines) + 20
            bh = len(lines) * fm.height() + 14
            bx = (self.width() - bw) / 2
            by = 6.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(bx, by, bw, bh), 10, 10)
            tail = QPointF(self.width() / 2, by + bh)
            p.drawPolygon(QPolygonF([tail, QPointF(tail.x() - 6, tail.y() + 8), QPointF(tail.x() + 6, tail.y() + 8)]))
            p.setPen(fg)
            p.setFont(bfont)
            for i, l in enumerate(lines):
                p.drawText(QRectF(bx, by + 7 + i * fm.height(), bw, fm.height()),
                           Qt.AlignmentFlag.AlignCenter, l)

        if self._use_3d():
            self._paint_3d(p, now)
            return

        cx = self.width() / 2
        walking = self.target is not None and not self.dragging
        walk_amount = getattr(self, "walk_amount", 0.0)
        phase = 2.0 * math.pi * getattr(self, "_walk_phase", 0.0)
        # 一个步态周期里两次触地：触地时身体最低，迈步中段最高。
        # 用 walk_amount 收尾，停下时身体起伏会自然落回，不会突然跳一下。
        bob_amp = (0.012 if self.mode == "bottom" else 0.011) * self.cur_h
        # 身体起伏比落脚晚一点到位，像体重压下去，而不是机械地跟着节拍跳
        bob = -bob_amp * (0.5 + 0.5 * math.cos(2 * phase - 0.35)) * walk_amount
        if walking:
            sway_amp = 1.1 if self.mode == "bottom" else 1.0
            sway = math.sin(phase - 0.12) * sway_amp * (0.35 + 0.65 * walk_amount)
        else:
            sway = math.sin(now * 2.5) * 1.5
        # 朝行进方向微微前倾（本地坐标，镜像后方向自动正确）
        walk_lean = -1.2 * walk_amount if self.dir in ("left", "right") else 0.0
        breath = 1.0 + 0.02 * math.sin(now * 2.5)
        scale = breath
        jump = -abs(math.sin(self.jump_t * 3.14159)) * 14 * self.jump_t if self.jump_t > 0 else 0
        act_rot = act_sx = act_sy = flip_jump = jog_x = jog_bob = 0.0
        if self.action == "sway":
            act_rot = math.sin(self.action_t * 3.14159 * 2) * 10 * self.action_t
        elif self.action == "stretch":
            act_sy = 0.06 * math.sin(self.action_t * 3.14159)
            act_sx = -0.03 * math.sin(self.action_t * 3.14159)
        elif self.action == "flip":
            progress = 1.0 - self.action_t
            act_rot = 360.0 * self._flip_dir * progress
            flip_jump = -math.sin(math.pi * progress) * 26.0
        elif self.action == "jog":
            progress = 1.0 - self.action_t
            phase = math.sin(progress * math.pi * 6)      # 一秒三小步
            jog_x = phase * 3.0
            jog_bob = -abs(phase) * 7.0
            act_rot = phase * 3.0
            act_sy = 0.015 * abs(phase)
        elif self.action == "dance":
            progress = 1.0 - self.action_t
            beat = math.sin(progress * math.pi * 4)       # 两个慢拍：扭腰摆胯
            act_rot = beat * 22.0
            act_sx = 0.07 * math.sin(progress * math.pi * 8)
            act_sy = 0.07 * abs(beat)
            jog_x = math.sin(progress * math.pi * 4) * 10.0
            jog_bob = -abs(math.sin(progress * math.pi * 4)) * 10.0
        elif self.action == "tantrum":
            progress = 1.0 - self.action_t
            direction = getattr(self, "_tantrum_dir", 1)
            act_rot = 360.0 * direction * math.sin(progress * math.pi)  # 滚过去再滚回来
            jog_x = math.sin(progress * math.pi * 10) * 12.0
            jog_bob = -abs(math.sin(progress * math.pi * 10)) * 6.0
            act_sy = 0.05 * abs(math.sin(progress * math.pi * 10))
        elif self.action == "eat":
            progress = 1.0 - self.action_t
            bite = abs(math.sin(progress * math.pi * 4))  # 两口
            act_sy = 0.08 * bite
            act_sx = -0.04 * bite

        def draw_one(key, opacity):
            if key is None:
                return
            pix, name, facing, is3d = self._resolve_key(key)
            h = self.cur_h
            ph = pix.height() * scale * (1 + act_sy)
            pw = pix.width() * scale * (1 + act_sx)
            dx = cx - pw / 2 + jog_x
            bottom = BUBBLE_H + MARGIN + self.cur_h
            dy = bottom - ph + jump + bob + flip_jump + jog_bob
            pivot_y = bottom - ph / 2 if self.action in ("flip", "tantrum") else bottom
            body_pix = pix
            parts = None
            if (not is3d) and name == "侧面" and self.action is None:
                parts = self._side_parts(h)
                if parts:
                    body_pix = parts[0]
                    # 脚先画、裙摆后画：袜口被裙摆遮住，只有鞋露在下面。
                    # 脚锁在地面，不跟着呼吸/起伏上下飘，才像踩在地上走路。
                    p.save()
                    p.setOpacity(opacity)
                    if facing < 0:
                        p.translate(cx, 0)
                        p.scale(-1, 1)
                        p.translate(-cx, 0)
                    self._draw_walk_feet(p, dx, bottom + jump, pix, pw, ph, parts, opacity)
                    p.restore()
            p.save()
            p.setOpacity(opacity)
            p.translate(cx, pivot_y)
            p.rotate(sway + act_rot + walk_lean)
            p.translate(-cx, -pivot_y)
            if facing < 0:
                p.translate(cx, 0)
                p.scale(-1, 1)
                p.translate(-cx, 0)
            p.drawPixmap(QRectF(dx, dy, pw, ph), body_pix, QRectF(0, 0, pix.width(), pix.height()))
            if self.look == "sexy":
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 45, 90, 62))
                p.drawRect(QRectF(dx, dy, pw, ph))
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            self._draw_style(p, dx, dy, pw, ph, name)
            p.restore()

        lift = max(0.0, -(bob + jump))
        shadow_scale = max(0.55, 1.0 - lift / 50.0)
        shadow_alpha = max(14, 34 - int(lift * 3))
        p.setPen(Qt.PenStyle.NoPen)
        # 三层淡影叠出柔边，避免脚下一块生硬的灰饼
        shadow_y = BUBBLE_H + MARGIN + self.cur_h - 2
        for grow, alpha in ((1.5, shadow_alpha * 0.22), (1.22, shadow_alpha * 0.33),
                            (1.0, shadow_alpha * 0.55)):
            p.setBrush(QColor(25, 30, 48, int(alpha)))
            p.drawEllipse(QPointF(cx, shadow_y),
                          self.cur_h * 0.195 * shadow_scale * grow,
                          self.cur_h * 0.028 * shadow_scale * grow)

        cur_key = self._sprite_key()
        if self.cross_t > 0:
            draw_one(self.prev_key, self.cross_t)
            draw_one(cur_key, 1.0 - self.cross_t)
        else:
            draw_one(cur_key, 1.0)

        if self.action == "dance":
            progress = 1.0 - self.action_t
            for i in range(5):
                phase = (progress * 3 + i / 5.0) % 1.0
                hx = cx + math.sin((progress * 3 + i) * math.pi * 2) * 24
                hy = BUBBLE_H + MARGIN + self.cur_h * 0.45 - phase * 34
                paint_heart(p, hx, hy, self.cur_h * 0.05,
                            QColor(255, 105, 150, int(210 * (1 - phase))))

    # ---------- 3D 形象绘制（只贴预渲染帧，不做 3D 计算） ----------
    def _action_params(self):
        """动作参数（沿用 2D 版数值）：旋转、x/y 缩放、额外跳高、横移、颠簸、是否绕身体中心转。"""
        rot = sx = sy = flip_jump = jog_x = jog_bob = 0.0
        center = False
        if self.action == "sway":
            rot = math.sin(self.action_t * math.pi * 2) * 10 * self.action_t
        elif self.action == "stretch":
            sy = 0.06 * math.sin(self.action_t * math.pi)
            sx = -0.03 * math.sin(self.action_t * math.pi)
        elif self.action == "flip":
            progress = 1.0 - self.action_t
            rot = 360.0 * self._flip_dir * progress
            flip_jump = -math.sin(math.pi * progress) * 26.0
            center = True
        elif self.action == "jog":
            progress = 1.0 - self.action_t
            ph = math.sin(progress * math.pi * 6)
            jog_bob = -abs(ph) * 7.0
            sy = 0.015 * abs(ph)
        elif self.action == "dance":
            progress = 1.0 - self.action_t
            beat = math.sin(progress * math.pi * 4)
            rot = beat * 7.0
            sx = 0.05 * math.sin(progress * math.pi * 8)
            sy = 0.06 * abs(beat)
            jog_x = beat * 10.0
            jog_bob = -abs(math.sin(progress * math.pi * 8)) * 9.0
        elif self.action == "tantrum":
            progress = 1.0 - self.action_t
            direction = getattr(self, "_tantrum_dir", 1)
            rot = 360.0 * direction * math.sin(progress * math.pi)
            jog_x = math.sin(progress * math.pi * 10) * 12.0
            jog_bob = -abs(math.sin(progress * math.pi * 10)) * 6.0
            sy = 0.05 * abs(math.sin(progress * math.pi * 10))
            center = True
        elif self.action == "eat":
            progress = 1.0 - self.action_t
            bite = abs(math.sin(progress * math.pi * 4))
            sy = 0.08 * bite
            sx = -0.04 * bite
        return rot, sx, sy, flip_jump, jog_x, jog_bob, center

    def _frame_3d(self):
        """这一刻画哪一帧：返回 (帧, (叠加帧, 混合比例) 或 None, 是否镜像, 该帧朝向, 是否正好落在该朝向)。"""
        r = self.r3d
        mirrored = self.yaw < -0.5
        a = abs(self.yaw)
        ia = int(round(a))
        settled = abs(self._yaw_diff(self.yaw_target, self.yaw)) < 0.5
        if settled and self.action == "jog" and r.walk_frames(ia):
            frames = r.walk_frames(ia)
            q = ((1.0 - self.action_t) * 3.0) % 1.0
            return frames[int(q * len(frames)) % len(frames)], None, mirrored, ia, True
        walking = self.target is not None and not self.dragging and self.action is None
        if settled and walking and r.walk_frames(ia):
            frames = r.walk_frames(ia)
            return frames[int(self._walk_phase * len(frames)) % len(frames)], None, mirrored, ia, True
        if settled and ia in r.idle:
            frames = r.idle[ia]
            pos = self._idle_clock * r.idle_fps
            i0 = int(pos) % len(frames)
            return frames[i0], (frames[(i0 + 1) % len(frames)], pos - int(pos)), mirrored, ia, True
        # 转身途中：相邻两个 15° 预渲染帧按角度混合，转起来更顺
        ys = r.turn_yaws
        i1 = next((k for k, y in enumerate(ys) if y >= a), len(ys) - 1)
        i0 = max(0, i1 - 1)
        if i0 == i1 or ys[i1] == ys[i0]:
            return r.turn[i1], None, mirrored, ys[i1], abs(a - ys[i1]) < 0.5
        f = (a - ys[i0]) / float(ys[i1] - ys[i0])
        if (ys[i0] <= 45 < ys[i1]) or (ys[i0] <= 135 < ys[i1]):
            # 这一格两边来自不同原画（正面↔侧面、侧面↔背面），轮廓差得多：
            # 不做长溶解（会叠出重影），在中间快速切过去
            t = min(1.0, max(0.0, (f - 0.38) / 0.24))
            f = t * t * (3 - 2 * t)
        near = ys[i1] if f >= 0.5 else ys[i0]
        exact = min(f, 1.0 - f) * (ys[i1] - ys[i0]) < 0.5
        return r.turn[i0], (r.turn[i1], f), mirrored, near, exact

    def _paint_shadow(self, p, cx, ground, lift, wide=1.0):
        shadow_scale = max(0.55, 1.0 - lift / 50.0)
        shadow_alpha = max(14, 34 - int(lift * 3))
        p.setPen(Qt.PenStyle.NoPen)
        for grow, alpha in ((1.5, shadow_alpha * 0.22), (1.22, shadow_alpha * 0.33),
                            (1.0, shadow_alpha * 0.55)):
            p.setBrush(QColor(25, 30, 48, int(alpha)))
            p.drawEllipse(QPointF(cx, ground - 2),
                          self.cur_h * 0.195 * shadow_scale * grow * wide,
                          self.cur_h * 0.028 * shadow_scale * grow)

    def _paint_3d(self, p, now):
        r = self.r3d
        cx = self.width() / 2
        ground = BUBBLE_H + MARGIN + self.cur_h
        flop = self._flop_progress()
        if flop is not None:
            self._paint_flop(p, cx, ground, *flop)
            self._paint_effects(p, cx, ground, now)
            return
        if self.sleeping and r.sleep is not None:
            self._paint_sleep(p, cx, ground, now)
            self._paint_effects(p, cx, ground, now)
            return
        rot, asx, asy, flip_jump, jog_x, jog_bob, center = self._action_params()
        walking = self.target is not None and not self.dragging
        amt = self.walk_amount
        phase = 2.0 * math.pi * self._walk_phase
        bob = -0.012 * self.cur_h * (0.5 + 0.5 * math.cos(2 * phase - 0.35)) * amt
        sway = (math.sin(phase - 0.12) * (0.35 + 0.65 * amt)) if walking else math.sin(now * 2.5) * 1.2
        # 舞台秀：姿势由编舞给出
        pose = self.game.pose() if (self.game is not None and hasattr(self.game, "pose")) else None
        if pose:
            rot, asx, asy = pose.get("rot", 0.0), pose.get("sx", 0.0), pose.get("sy", 0.0)
            flip_jump, jog_x, jog_bob, center = pose.get("dy", 0.0), pose.get("dx", 0.0), 0.0, False
            sway = bob = 0.0
            self.game.paint_fx(p, cx, ground, self.cur_h, "back")
        breath = 1.0 + 0.016 * math.sin(now * 2.5)
        jump = -abs(math.sin(self.jump_t * math.pi)) * 14 * self.jump_t if self.jump_t > 0 else 0
        sq = self._squash
        sx_total = breath * (1 + asx) * (1 + 0.12 * sq)
        sy_total = breath * (1 + asy) * (1 - 0.16 * sq)
        lift = max(0.0, -(bob + jump + flip_jump + jog_bob))
        self._paint_shadow(p, cx, ground, lift)

        pix, cross, mirrored, fyaw, exact = self._frame_3d()
        ph = pix.height()
        p.save()
        p.translate(cx + jog_x, ground + jump + bob + flip_jump + jog_bob)
        if abs(self._lean) > 0.05 and not center:
            sway += self._lean                      # 起步前倾、刹车后仰
        if abs(self._dangle) > 0.05:
            # 被拎起来：以头顶为轴来回晃
            p.translate(0, -ph)
            p.rotate(self._dangle)
            p.translate(0, ph)
        if center:
            p.translate(0, -ph / 2)
            p.rotate(rot)
            p.translate(0, ph / 2)
        else:
            p.rotate(rot + sway)
        p.scale(-sx_total if mirrored else sx_total, sy_total)
        top_left = QPointF(-r.axis, -ph)
        p.drawPixmap(top_left, pix)
        if cross is not None and cross[1] > 0.03:
            p.setOpacity(cross[1])
            p.drawPixmap(top_left, cross[0])
            p.setOpacity(1.0)
        wall = time.time()
        eyes = None
        if pose and pose.get("eyes"):
            eyes = pose["eyes"]
        elif wall < self._happy_until or self.action == "stretch":
            eyes = "happy"
        elif wall < self._blink_until:
            eyes = "closed"
        if eyes and exact:
            ov = r.overlay("closed" if eyes == "wink" else eyes, fyaw)
            if ov is not None:
                if eyes == "wink" and fyaw != 90:
                    # 抛媚眼：只闭一只眼（侧面本来就只看得到一只眼）
                    p.save()
                    p.setClipRect(QRectF(top_left.x() + ov[1].x() + ov[0].width() * 0.5,
                                         top_left.y() + ov[1].y(), ov[0].width() * 0.5, ov[0].height()))
                    p.drawPixmap(top_left + ov[1], ov[0])
                    p.restore()
                else:
                    p.drawPixmap(top_left + ov[1], ov[0])
        if self.look == "sexy":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 45, 90, 62))
            p.drawRect(QRectF(top_left.x(), top_left.y(), pix.width(), ph))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self._draw_style_3d(p, top_left, pix.width(), ph, fyaw)
        p.restore()
        if pose:
            self.game.paint_fx(p, cx, ground, self.cur_h, "front")
        self._paint_effects(p, cx, ground, now)

    def _draw_style_3d(self, p, top_left, pw, ph, fyaw):
        """可爱 / 性感装饰点在 3D 头上的锚点，跟着转身一起动。"""
        an = self.r3d.anchors(fyaw)
        h = ph

        def pt(v):
            return QPointF(top_left.x() + v[0] * pw, top_left.y() + v[1] * ph)

        p.setPen(Qt.PenStyle.NoPen)
        if self.look == "cute":
            p.setBrush(QColor(255, 120, 160, 105))
            for c in an.get("cheeks", []):
                p.drawEllipse(pt(c), h * 0.034, h * 0.016)
            if "heart" in an:
                hp = pt(an["heart"])
                paint_heart(p, hp.x(), hp.y(), h * 0.041, QColor(255, 90, 145, 230))
            for s in an.get("sparkles", []):
                sp = pt(s)
                paint_sparkle(p, sp.x(), sp.y(), h * 0.021, QColor(255, 255, 255, 220))
        else:
            if an.get("mouth"):
                mp = pt(an["mouth"])
                p.setBrush(QColor(190, 25, 55, 220))
                p.drawEllipse(mp, h * 0.019, h * 0.010)
            pts = ([an["heart"]] if "heart" in an else []) + an.get("sparkles", [])
            for v in pts:
                hp = pt(v)
                paint_heart(p, hp.x(), hp.y(), h * 0.045, QColor(235, 60, 105, 220))

    FLOP_S = 0.45

    def _flop_progress(self):
        if self._flop is None:
            return None
        start, kind, mirror = self._flop
        k = (time.time() - start) / self.FLOP_S
        if k >= 1.0:
            self._flop = None
            return None
        return max(0.0, k), kind, mirror

    def _paint_flop(self, p, cx, ground, k, kind, mirror):
        """躺下（啪叽倒下）/ 爬起来的过渡：侧身帧绕脚底转 90°，结束姿势正好接上睡觉图。"""
        r = self.r3d
        pix = r.turn[r.turn_index(90)]
        ph = pix.height()
        e = k * k * (3 - 2 * k)
        ang = 90.0 * (e if kind == "down" else 1.0 - e)
        sign = -1.0 if mirror else 1.0
        s = math.sin(math.radians(ang))
        shift = ph * 0.5 * (ang / 90.0)
        hop = -math.sin(math.pi * e) * self.cur_h * 0.10
        lift = -0.36 * ph * s                       # 背后的头发别压到地面以下
        self._paint_shadow(p, cx, ground, max(0.0, -hop), wide=1.0 + 0.6 * ang / 90.0)
        p.save()
        p.translate(cx - sign * shift, ground + hop + lift)
        p.rotate(sign * ang)
        p.scale(-1.0 if mirror else 1.0, 1.0)
        p.drawPixmap(QPointF(-r.axis, -ph), pix)
        p.restore()

    def _paint_sleep(self, p, cx, ground, now):
        pix = self.r3d.sleep
        w, h = pix.width(), pix.height()
        self._paint_shadow(p, cx, ground, 0.0, wide=1.6)
        breath = 1.0 + 0.03 * math.sin(now * 1.7)
        p.save()
        p.translate(cx, ground)
        p.scale(-1.0 if self._sleep_mirror else 1.0, breath)
        p.drawPixmap(QPointF(-w / 2, -h + h * 0.03), pix)
        p.restore()

    def _paint_effects(self, p, cx, ground, now):
        wall = time.time()
        h = self.cur_h
        # 摸头时飘起的小心心
        for born, xo, drift in self._hearts:
            age = wall - born
            if age < 0:
                continue
            k = min(1.0, age / 1.4)
            x = cx + xo * h + drift * k
            y = ground - h * 0.92 - k * h * 0.30
            paint_heart(p, x, y, h * (0.035 + 0.02 * k), QColor(255, 95, 150, int(230 * (1 - k))))
        # 被摔晕：头顶转圈的小星星
        if wall < self._dizzy_until:
            fade = min(1.0, (self._dizzy_until - wall) / 0.5)
            for i in range(3):
                ang = now * 5.0 + i * 2.0944
                sx = cx + math.cos(ang) * h * 0.19
                sy = ground - h * 0.97 + math.sin(ang) * h * 0.045
                paint_sparkle(p, sx, sy, h * 0.032, QColor(255, 214, 70, int(235 * fade)))
        # 睡觉的 Zzz
        if self.sleeping and self.r3d.sleep is not None:
            pw, ph = self.r3d.sleep.width(), self.r3d.sleep.height()
            side = -1.0 if self._sleep_mirror else 1.0
            hx = cx + side * pw * 0.22
            hy = ground - ph * 0.72
            font = QFont("Segoe UI", max(8, int(h * 0.075)))
            font.setBold(True)
            p.setFont(font)
            for i in range(3):
                k = ((now * 0.45) + i / 3.0) % 1.0
                p.setPen(QColor(110, 130, 220, int(220 * (1 - k))))
                p.drawText(QPointF(hx + side * (k * h * 0.18 + i * 3), hy - k * h * 0.42), "Z" if i else "z")

    def _draw_style(self, p, dx, dy, pw, ph, name):
        if self.look == "cute":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 120, 160, 105))
            if name == "正面":
                cheeks = [(0.40, 0.535), (0.60, 0.535)]
            elif name == "侧面":
                cheeks = [(0.29, 0.525)]
            else:
                cheeks = []
            for fx, fy in cheeks:
                p.drawEllipse(QPointF(dx + fx * pw, dy + fy * ph), pw * 0.045, ph * 0.018)
            if name == "正面":
                head, sparkles = (0.50, 0.22), [(0.30, 0.30), (0.70, 0.34)]
            elif name == "侧面":
                head, sparkles = (0.33, 0.22), [(0.18, 0.32), (0.42, 0.30)]
            else:
                head, sparkles = (0.50, 0.22), [(0.30, 0.32), (0.70, 0.38)]
            paint_heart(p, dx + head[0] * pw, dy + head[1] * ph, pw * 0.055,
                        QColor(255, 90, 145, 230))
            for fx, fy in sparkles:
                paint_sparkle(p, dx + fx * pw, dy + fy * ph, pw * 0.028,
                              QColor(255, 255, 255, 220))
        else:
            if name != "背面":
                if name == "正面":
                    mouth = (0.50, 0.555)
                else:
                    mouth = (0.225, 0.55)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(190, 25, 55, 220))
                p.drawEllipse(QPointF(dx + mouth[0] * pw, dy + mouth[1] * ph),
                              pw * 0.026, ph * 0.010)
            if name == "正面":
                hearts = [(0.50, 0.22), (0.22, 0.37), (0.78, 0.43)]
            elif name == "侧面":
                hearts = [(0.33, 0.22), (0.15, 0.38), (0.62, 0.47)]
            else:
                hearts = [(0.50, 0.22), (0.22, 0.40), (0.78, 0.45)]
            for fx, fy in hearts:
                paint_heart(p, dx + fx * pw, dy + fy * ph, pw * 0.06,
                            QColor(235, 60, 105, 220))

    def _load_sprites(self, h):
        sprites = {}
        for name in ("正面", "侧面", "背面"):
            sized = os.path.join(SPRITE_DIR, f"{name}_{h}.png")
            if os.path.exists(sized):
                pix = QPixmap(sized)
            else:
                pix = QPixmap(os.path.join(SPRITE_DIR, f"{name}.png")).scaledToHeight(
                    h, Qt.TransformationMode.SmoothTransformation)
            sprites[(name, h)] = pix
        return sprites

    def _use_3d(self):
        r = getattr(self, "r3d", None)
        return bool(r is not None and r.ok) and bool(self.cfg.get("render3d", True))

    def _apply_window_size(self):
        self.win_mx = int(self.cur_h * 0.24) + 6
        widths = [p.width() for p in self.sprites.values()]
        if self._use_3d():
            widths += [self.r3d.frame_w, self.r3d.sleep_w]
        self.win_w = max(widths) + self.win_mx * 2
        self.setFixedSize(self.win_w, self.cur_h + BUBBLE_H + MARGIN * 2 + 10)

    @staticmethod
    def _wrap_yaw(a):
        a = (a + 180.0) % 360.0 - 180.0
        return 180.0 if a == -180.0 else a

    @staticmethod
    def _yaw_diff(target, cur):
        """从 cur 转到 target 的角度差；左右换边时从正面转过去（会先看你一眼）。"""
        d = (target - cur + 180.0) % 360.0 - 180.0
        if abs(abs(d) - 180.0) < 25.0 and abs(target) <= 120 and abs(cur) <= 120:
            d = target - cur
        return d

    def _resolve_key(self, key):
        """把 2D 精灵键解析成 (pixmap, 样式名, facing, 是否3D)。"""
        name, h, facing = key
        return self.sprites[(name, h)], name, facing, False

    def _side_parts(self, h):
        """把侧视图拆成『裙身（挖掉脚）』和『脚』两层，走路时两只脚独立迈步。

        原图只有一条腿，靠裙摆挡住腿根；把脚从裙身里挖出来以后，
        脚可以藏在裙摆后面左右迈，而裙摆上的洞只在原来腿的位置，
        所以不会出现脚从裙子外面飘过去的穿帮。
        """
        cached = self._side_parts_cache.get(h)
        if cached is not None:
            return cached
        pix = self.sprites.get(("侧面", h))
        if pix is None or pix.isNull():
            self._side_parts_cache[h] = ()
            return ()
        src = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        w, hh = src.width(), src.height()
        sx, sy = w / 200.0, hh / 306.0
        pts = [(58, 283), (89, 283), (89, 289), (92, 292), (92, 301),
               (88, 306), (53, 306), (50, 303), (50, 298), (57, 291), (57, 286)]
        poly = QPolygonF([QPointF(x * sx, y * sy) for x, y in pts])
        rect = poly.boundingRect()
        x0 = max(0, int(rect.left()) - 1)
        y0 = max(0, int(rect.top()) - 1)
        x1 = min(w, int(rect.right()) + 2)
        y1 = min(hh, int(rect.bottom()) + 2)

        body_img = QImage(src)
        for y in range(y0, y1):
            for x in range(x0, x1):
                if poly.containsPoint(QPointF(x + 0.5, y + 0.5), Qt.FillRule.OddEvenFill):
                    body_img.setPixelColor(x, y, QColor(0, 0, 0, 0))

        foot_img = QImage(x1 - x0, y1 - y0, QImage.Format.Format_ARGB32)
        foot_img.fill(QColor(0, 0, 0, 0))
        for y in range(y0, y1):
            for x in range(x0, x1):
                if poly.containsPoint(QPointF(x + 0.5, y + 0.5), Qt.FillRule.OddEvenFill):
                    foot_img.setPixelColor(x - x0, y - y0, src.pixelColor(x, y))

        far_img = QImage(foot_img)
        painter = QPainter(far_img)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        painter.fillRect(far_img.rect(), QColor(18, 22, 46, 60))
        painter.end()

        parts = (QPixmap.fromImage(body_img), QPixmap.fromImage(foot_img),
                 QPixmap.fromImage(far_img), QRectF(x0, y0, x1 - x0, y1 - y0))
        self._side_parts_cache[h] = parts
        return parts

    def _foot_pose(self, q):
        """返回（前后偏移, 抬脚高度, 脚尖角度），q 为单脚相位 0..1。"""
        cycle = max(46.0, WALK_CYCLE_FACTOR * self.cur_h)
        stride = WALK_STANCE * cycle
        lift_h = 0.030 * self.cur_h
        if q < WALK_STANCE:
            t = q / WALK_STANCE
            off = stride * (-0.5 + t)
            toe = 6.0 * max(0.0, (t - 0.72) / 0.28)   # 后蹬时脚跟抬起
            lift = 0.0
        else:
            t = (q - WALK_STANCE) / (1.0 - WALK_STANCE)
            ease = t * t * (3.0 - 2.0 * t)             # 起步/落脚都带一点缓冲
            off = stride * (0.5 - ease)
            toe = 7.0 * math.sin(math.pi * t)          # 绷脚背，步子更轻盈
            lift = -lift_h * math.sin(math.pi * t)
        return off, lift, toe

    def _draw_walk_feet(self, p, dx, ground, pix, pw, ph, parts, opacity):
        _body, foot_pix, far_pix, fr = parts
        amt = getattr(self, "walk_amount", 0.0)
        sx = pw / pix.width()
        sy = ph / pix.height()
        fw = fr.width() * sx
        fh = fr.height() * sy
        mid_x = dx + fr.x() * sx + fw / 2
        phase = getattr(self, "_walk_phase", 0.0)
        for k in (1, 0):                       # 先远脚，再近脚
            q = (phase + 0.5 * k) % 1.0
            off, lift, toe = self._foot_pose(q)
            off *= amt
            lift *= amt
            toe *= amt
            # 每只脚一块小接地影，抬脚时变淡变小
            p.save()
            p.setOpacity(opacity)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(45, 50, 70,
                              max(3, int((18 + lift * 3) * (0.30 + 0.70 * amt)))))
            p.drawEllipse(QPointF(mid_x + off, ground + 1.0),
                          fw * 0.38 * max(0.7, 1 + lift / 90.0),
                          max(0.8, fh * 0.06))
            p.restore()
            p.save()
            p.setOpacity(opacity)
            # 以脚踝为轴转脚尖；脚底始终贴在地面线上
            p.translate(mid_x + off, ground - fh * 0.55 + lift - k * 1.0)
            p.rotate(toe)
            p.drawPixmap(QRectF(-fw / 2, -fh * 0.45, fw, fh),
                         far_pix if k else foot_pix,
                         QRectF(0, 0, foot_pix.width(), foot_pix.height()))
            p.restore()

    def _sprite_key(self):
        if self.action in ("dance", "tantrum"):
            return ("侧面", self.cur_h, 1)          # 舞蹈/打滚用侧身
        name = {"left": "侧面", "right": "侧面", "up": "背面", "down": "正面"}[self.dir]
        return (name, self.cur_h, self.facing if self.dir in ("left", "right") else 1)

    def _set_dir(self, d, facing=None):
        if d != self.dir:
            self.prev_key = self._sprite_key()
            self.cross_t = 1.0
            self.dir = d
        if facing is not None and facing != self.facing:
            self.facing = facing

    # ---------- 逻辑 ----------
    def update(self, *args):
        # 空闲时隔帧重绘（见 _can_skip_paint），省 CPU
        if not args and getattr(self, "_skip_paint", False):
            return
        super().update(*args)

    def _can_skip_paint(self):
        """按状态决定重绘频率：快动作 50 帧，走路 25 帧，待机 ~17 帧，睡觉 12.5 帧。
        透明窗口每次重绘都要让系统重新合成，少画几帧是最省 CPU 的办法；
        窗口移动本身不需要重绘。"""
        if self.sleeping:
            every = 4
        elif (self.dragging or self._throwing or self.action is not None or self.jump_t > 0
              or self.cross_t > 0 or self._squash > 0.01 or abs(self._dangle) > 0.05
              or self._hearts or self.game is not None or abs(self.yaw - self.yaw_target) > 0.5
              or self._flop is not None or abs(self._lean) > 0.1
              or time.time() < self._dizzy_until):
            every = 1
        elif self.target is not None:
            every = 2
        else:
            every = 3
        return self.t % every != 0

    def tick(self):
        self._skip_paint = self._can_skip_paint()
        try:
            self._tick_impl()
        finally:
            self._skip_paint = False

    def _tick_impl(self):
        # 藏起来时把定时器从 50 次/秒降到 10 次/秒；t 按真实时间多走几步，计时类逻辑不受影响
        want = 100 if not self.isVisible() else TICK
        if self.timer.interval() != want:
            self.timer.setInterval(want)
            if want != TICK:
                self.t = (self.t // 5 + 1) * 5 - 5          # 对齐到 5 的倍数，t % N 判断照常命中
        self.t += want // TICK

        # 本地调试：把 run_dance.flag 放到项目目录即可触发一次舞蹈（每秒查一次，不必每帧读盘）
        if self.t % 50 == 0:
            self._check_debug_flags()

        # 处理后台线程（DeepSeek 等）排队的气泡消息，Qt 界面必须在主线程更新
        self._drain_queues()

        self.check_system_status()

        # 走路量：起步/停下时给摆脚一个短过渡，避免脚突然跳回原位
        moving = self.target is not None and not self.dragging and self.action is None
        self.walk_amount += ((1.0 if moving else 0.0) - self.walk_amount) * 0.22
        if self.walk_amount < 0.002:
            self.walk_amount = 0.0

        if self.jump_t > 0:
            self.jump_t = max(0.0, self.jump_t - 0.06)
        if self.cross_t > 0:
            self.cross_t = max(0.0, self.cross_t - 0.15)
        if self.action_t > 0:
            step = (0.008 if self.action == "tantrum" else 0.01 if self.action == "dance"
                    else 0.02 if self.action in ("flip", "jog", "eat") else 0.03)
            self.action_t = max(0.0, self.action_t - step)
            if self.action_t == 0:
                if self.action in ("dance", "tantrum"):
                    self.prev_key = self._sprite_key()   # 侧面 -> 正面，淡出
                    self.cross_t = 1.0
                    if self.action == "dance" and getattr(self, "_look_before_dance", None):
                        self.look = self._look_before_dance
                        self._look_before_dance = None
                self.action = None

        if self.t % 100 == 0:
            self._check_fullscreen()
        if not self.isVisible():
            return                      # 藏起来（手动隐藏 / 全屏时）就什么都不用算
        self._update_3d_state()
        for toy in list(self.toys):
            toy.tick()
        if self.sleeping:
            self.update()
            return
        if self.game is not None and not self.dragging and not self._throwing:
            self.game.tick()
            self.update()
            return
        self._tick_modes()

    def _show_from_second_launch(self):
        """又双击了一次启动：不再开第二只，叫已经在跑的这只出来打个招呼。"""
        self._fs_hidden = False
        self.show()
        self.raise_()
        self.snap_into_screen()
        if self.sleeping:
            self._wake_up("我在这儿呢～")
        else:
            self.jump_t = 1.0
            self.say("我在这儿呢～")

    def _check_debug_flags(self):
        # show_pet.flag 由第二次启动写入；其余是新玩法的调试触发
        for flag, fn in (("show_pet", self._show_from_second_launch),
                         ("run_nap", lambda: self.start_nap(minutes=3)),
                         ("run_wake", lambda: self._wake_up("醒啦")),
                         ("run_bubbles", self.blow_bubbles),
                         ("run_catch", lambda: self.start_game("catch")),
                         ("run_fetch", lambda: self.start_game("fetch")),
                         ("run_hide", lambda: self.start_game("hide")),
                         ("run_endgame", self.end_game)):
            path = os.path.join(APP_DIR, flag + ".flag")
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
                fn()
        trigger = os.path.join(APP_DIR, "run_dance.flag")
        if os.path.exists(trigger):
            try:
                os.remove(trigger)
            except OSError:
                pass
            self._action_queue.append("dance")
        trigger = os.path.join(APP_DIR, "run_tantrum.flag")
        if os.path.exists(trigger):
            try:
                os.remove(trigger)
            except OSError:
                pass
            self._action_queue.append("tantrum")
        trigger = os.path.join(APP_DIR, "run_walk.flag")
        if os.path.exists(trigger):
            try:
                os.remove(trigger)
            except OSError:
                pass
            if self.mode == "bottom":
                _left, _top = self._bottom_home()
                _geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
                self.target = (_geo.left() + 20 + self.width() / 2,
                               _top + self.height() / 2)
                self._bottom_away = True

    def _drain_queues(self):
        if self._say_queue:
            for text in self._say_queue:
                self.say(text)
            self._say_queue.clear()
        if self._action_queue:
            for action in self._action_queue:
                self._perform_action(action)
            self._action_queue.clear()
        if self._chat_queue:
            for text in self._chat_queue:
                self.chat_dialog.append_message("assistant", text)
                self.say(text if len(text) <= 24 else text[:22] + "…")
                self.speak(text)
                if not text.startswith(("API错误", "请求失败", "请求超时", "连接失败")):
                    self.pet_state["affection"] = min(
                        100, int(self.pet_state.get("affection", 0)) + 1)
                    self.add_exp(3)
            self._chat_queue.clear()
            self._save_chat_history()
        if self._chat_quiet_queue:
            for text, bubble in self._chat_quiet_queue:
                self.chat_dialog.append_message("assistant", text)
                self.say(bubble if len(bubble) <= 24 else bubble[:22] + "…")
            self._chat_quiet_queue.clear()
        if self._dsh_success_pending:
            self._dsh_success_pending = False
            self._bump_counter("dsh")
        if self.t > 0 and self.t % 3000 == 0:
            self._bump_daily("minutes")
        if self.t > 0 and self.t % 60000 == 0:
            st = self.pet_state
            st["hunger"] = max(0, int(st.get("hunger", 70)) - 1)
            self._update_status_label()
            self._save_pet_state()
            if st["hunger"] == 20:
                line = "我饿了……该投喂了。"
                self.say(line)
                self.speak(line)
        if (self.cfg.get("proactive_enabled", True)
                and self.isVisible()
                and not self.ds_busy
                and not self.chat_paused
                and not self.dragging
                and not self.sleeping
                and self.game is None
                and time.time() >= self._next_proactive):
            self._next_proactive = time.time() + self._proactive_delay()
            self._proactive()

    def _tick_modes(self):
        if self.chat_paused:
            self.update()
            return

        if self.dragging:
            self.update()
            return
        if self._throwing:
            self._apply_throw_physics()
            self.update()
            return
        now_ms = self.t * TICK

        if self.mode == "follow":
            cursor = self.cursor().pos()
            screen = QApplication.screenAt(cursor) or self.screen() or QApplication.primaryScreen()
            geo = screen.availableGeometry()
            near = (self.x() - 100 <= cursor.x() <= self.x() + self.width() + 100 and
                    self.y() - 100 <= cursor.y() <= self.y() + self.height() + 100)
            if near:
                self.target = None
            else:
                tx = max(geo.left(), min(geo.right() - self.width(), cursor.x() - self.width() / 2))
                ty = max(geo.top(), min(geo.bottom() - self.height(), cursor.y() - 90))
                self.target = (tx, ty)
        elif self.mode == "relaxed":
            if self.target is None:
                if now_ms < self.rest_until:
                    self._maybe_idle_action()
                    self.update()
                    return
                # 大部分时候真的走动，剩下才继续歇着
                if random.random() < RELAX_MOVE_CHANCE:
                    geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
                    hx = getattr(self, "home_x", self.x())
                    hy = getattr(self, "home_y", self.y())
                    # 跑远了就先回家，否则只在“家”附近溜达
                    if abs(self.x() - hx) > RELAX_RADIUS_X + 60 or abs(self.y() - hy) > RELAX_RADIUS_Y + 50:
                        tx, ty = hx, hy
                    else:
                        tx = hx + random.randint(-RELAX_RADIUS_X, RELAX_RADIUS_X)
                        ty = hy + random.randint(-RELAX_RADIUS_Y, RELAX_RADIUS_Y)
                    tx = max(geo.left() + 20, min(geo.right() - self.width() - 20, tx))
                    ty = max(geo.top() + 20, min(geo.bottom() - self.height() - 20, ty))
                    self.target = (tx, ty)
                else:
                    self.rest_until = self.t * TICK + random.randint(*RELAX_DECISION_REST_MS)
                    self._maybe_idle_action()
                    self.update()
                    return
        elif self.mode == "bottom":
            home_left, home_top = self._bottom_home()
            home_cx = home_left + self.width() / 2
            home_cy = home_top + self.height() / 2
            geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
            # 任务栏显示/隐藏会改变工作区，随时重新贴底
            if self.target is not None:
                self.target = (self.target[0], home_cy)
            elif not self.action and abs(self.y() - home_top) > 2:
                self.move(self.x(), home_top)
            if self.target is None:
                if now_ms < self.rest_until:
                    self._maybe_idle_action()
                    self.update()
                    return
                if self._bottom_away:
                    self.target = (home_cx, home_cy)        # 游走完一定自己回去
                elif abs(self.x() - home_left) > BOTTOM_WANDER_PX + 80:
                    self.target = (home_cx, home_cy)        # 跑远了先回家
                elif random.random() < BOTTOM_WANDER_CHANCE:
                    # 整条屏幕底边都可以走，偶尔一直溜达到左边
                    tx = random.randint(int(geo.left() + 20 + self.width() / 2),
                                        int(geo.right() - 20 - self.width() / 2))
                    self.target = (tx, home_cy)
                    self._bottom_away = True
                elif abs(self.x() - home_left) > 30:
                    self.target = (home_cx, home_cy)
                else:
                    self.rest_until = self.t * TICK + random.randint(*RELAX_DECISION_REST_MS)
                    self._maybe_idle_action()
                    self.update()
                    return
        elif self.mode == "wander":
            if self.target is None:
                if now_ms < self.rest_until:
                    self._maybe_idle_action()
                    self.update()
                    return
                geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
                self.target = (random.randint(geo.left() + 40, geo.right() - self.width() - 40),
                               random.randint(geo.top() + 40, geo.bottom() - self.height() - 40))
        else:
            self._maybe_idle_action()
            self.update()
            return

        if self.target is not None:
            cx, cy = self.x() + self.width() / 2, self.y() + self.height() / 2
            dx, dy = self.target[0] - cx, self.target[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < 12:
                self.target = None
                if self.mode == "bottom":
                    hx, _ = self._bottom_home()
                    if abs(self.x() - hx) <= 30:
                        self._bottom_away = False
                        self.rest_until = self.t * TICK + random.randint(*RELAX_ARRIVAL_REST_MS)
                    else:
                        self.rest_until = self.t * TICK + random.randint(2000, 5000)
                elif self.mode == "relaxed":
                    self.rest_until = self.t * TICK + random.randint(*RELAX_ARRIVAL_REST_MS)
                else:
                    self.rest_until = self.t * TICK + random.randint(8000, 18000)
                self._set_dir("down")
            else:
                step = self.cur_speed * TICK / 1000.0
                cycle_px = max(46.0, WALK_CYCLE_FACTOR * self.cur_h)
                self._walk_phase = (getattr(self, "_walk_phase", 0.0) + step / cycle_px) % 1.0
                nx, ny = cx + dx / dist * step, cy + dy / dist * step
                self.move(int(nx - self.width() / 2), int(ny - self.height() / 2))
                if abs(dx) > abs(dy) * 1.15:
                    self._set_dir("left" if dx < 0 else "right", 1 if dx < 0 else -1)
                else:
                    self._set_dir("up" if dy < 0 else "down")
            jump_chance = 0.004 if self.mode == "bottom" else 0.002
            if random.random() < jump_chance and self.jump_t == 0:
                self.jump_t = 0.5
        base_speed = (RELAX_SPEED if self.mode == "relaxed"
                      else WALK_SPEED_BOTTOM if self.mode == "bottom" else SPEED)
        target_speed = base_speed if self.target is not None else 0.0
        self.cur_speed += (target_speed - self.cur_speed) * 0.3
        self.update()

    # ---------- 3D 朝向 / 眨眼 / 看鼠标 / 摸头 / 午睡 ----------
    def _update_3d_state(self):
        now = time.time()
        dt = TICK / 1000.0
        self._idle_clock += dt
        self._squash = self._squash * 0.86 if self._squash > 0.002 else 0.0
        # 被拎起来时像钟摆一样晃，松手后慢慢停
        target = 0.0
        if self.dragging and len(self._drag_samples) >= 2:
            (t0, x0, _), (t1, x1, _) = self._drag_samples[0], self._drag_samples[-1]
            vx = (x1 - x0) / max(0.02, t1 - t0)
            target = max(-28.0, min(28.0, -vx * 0.03))
        self._dangle_v = (self._dangle_v + (target - self._dangle) * 0.18) * 0.82
        self._dangle += self._dangle_v
        if not self.dragging and abs(self._dangle) < 0.05 and abs(self._dangle_v) < 0.05:
            self._dangle = self._dangle_v = 0.0
        # 起步时身子往前倾、停下时往后仰一下（惯性），只在左右走时
        accel = (self.cur_speed - self._prev_speed) / dt
        self._prev_speed = self.cur_speed
        fwd = -1.0 if self.dir == "left" else 1.0 if self.dir == "right" else 0.0
        lean_target = fwd * max(-1.0, min(1.0, accel / 400.0)) * 5.0
        self._lean += (lean_target - self._lean) * 0.2
        if abs(self._lean) < 0.02:
            self._lean = 0.0
        if self._hearts:
            self._hearts = [h for h in self._hearts if now - h[0] < 1.5]
        cur = QCursor.pos()
        if self._cursor_last is None or (cur - self._cursor_last).manhattanLength() > 2:
            self._cursor_moved_at = now
            self._cursor_last = cur
        self._check_stroke(now, cur)
        self._check_nap(now)
        # 眨眼：2~6 秒一次，偶尔连眨两下
        if now >= self._next_blink and not self.sleeping:
            self._blink_until = now + 0.13
            self._next_blink = now + (0.30 if random.random() < 0.2 else random.uniform(2.2, 6.0))
        # 朝向：被扔出去时在空中转圈，平时平滑转向目标；躺下 / 爬起过程中保持侧身
        if self._flop is not None:
            return
        if (self.game is not None and getattr(self.game, "direct_yaw", None) is not None
                and not self.dragging and not self._throwing):
            self.yaw = self.yaw_target = self._wrap_yaw(float(self.game.direct_yaw))   # 舞台秀直接给角度
            return
        if self._throwing:
            self.yaw = self._wrap_yaw(self.yaw + self._spin_dir * 900.0 * dt)
            self.yaw_target = self.yaw
            return
        self.yaw_target = self._desired_yaw(now, cur)
        d = self._yaw_diff(self.yaw_target, self.yaw)
        step = TURN_SPEED * dt
        self.yaw = self.yaw_target if abs(d) <= step else self._wrap_yaw(self.yaw + (step if d > 0 else -step))

    def _desired_yaw(self, now, cur):
        if self.game is not None:
            y = self.game.desired_yaw()
            if y is not None:
                return y
        if self.dragging:
            return 90.0 if self.dir == "left" else -90.0 if self.dir == "right" else self.yaw_target
        if self.action == "tantrum":
            return 90.0 if getattr(self, "_tantrum_dir", 1) > 0 else -90.0
        if self.action == "dance":
            return 40.0 * math.sin((1.0 - self.action_t) * math.pi * 4)
        if now < self._look_back_until:
            return 150.0 * self._look_back_side           # 被摸尾巴：转过身去看尾巴
        if self.target is not None:
            return {"left": 90.0, "right": -90.0, "up": 180.0, "down": 0.0}.get(self.dir, 0.0)
        if self.chat_paused or now < self._happy_until:
            return 0.0                                  # 聊天 / 被摸的时候看着你
        if now < self._glance_until:
            return float(LOOK_YAW * self._glance_side)
        if self.cfg.get("look_at_cursor", True) and now - self._cursor_moved_at < LOOK_BORED_S:
            g = self.frameGeometry()
            mid = g.center()
            dx = cur.x() - mid.x()
            if g.contains(cur):
                return 0.0
            if abs(dx) < LOOK_RANGE and abs(cur.y() - mid.y()) < 700:
                if dx < -40:
                    self._look_side = 1
                elif dx > 40:
                    self._look_side = -1
                elif self._look_side == 0:
                    self._look_side = 1 if dx < 0 else -1
                return float(LOOK_YAW * self._look_side)
        self._look_side = 0
        if random.random() < 0.0015:                    # 偶尔自己左右张望一下
            self._glance_side = random.choice((-1, 1))
            self._glance_until = now + random.uniform(1.2, 2.4)
        return 0.0

    def _check_stroke(self, now, cur):
        """鼠标不按键、在她头上来回划几下 = 摸摸头。"""
        if self.dragging or self._mouse_down or self.sleeping or self.game is not None:
            self._stroke.clear()
            return
        g = self.frameGeometry()
        top = g.top() + BUBBLE_H + MARGIN
        inside = (g.left() + self.win_mx * 0.5 <= cur.x() <= g.right() - self.win_mx * 0.5
                  and top - 10 <= cur.y() <= top + self.cur_h * 0.45)
        if not inside:
            if self._stroke:
                self._stroke.clear()
            return
        if not self._stroke or abs(cur.x() - self._stroke[-1][1]) >= 2:
            self._stroke.append((now, cur.x()))
        self._stroke = [s for s in self._stroke if now - s[0] < 1.6]
        rev, direction, anchor = 0, 0, None
        for _, x in self._stroke:
            if anchor is None:
                anchor = x
                continue
            if abs(x - anchor) >= 6:
                d = 1 if x > anchor else -1
                if direction and d != direction:
                    rev += 1
                direction, anchor = d, x
        if rev >= STROKE_REVERSALS:
            self._stroke.clear()
            self._on_stroked(now)

    def _on_stroked(self, now):
        self._happy_until = now + 1.8
        for _ in range(2):
            self._hearts.append((now + random.uniform(0.0, 0.35), random.uniform(-0.12, 0.12),
                                 random.uniform(-14, 14)))
        if now - self._stroke_reward_at > 3.0:
            self._stroke_reward_at = now
            st = self.pet_state
            st["affection"] = min(100, int(st.get("affection", 0)) + 1)
            self.add_exp(1)
            self._bump_daily("pet")
            self._bump_counter("pet")
            if random.random() < 0.45:
                line = random.choice(["呼噜呼噜……", "嘿嘿，舒服～", "再摸摸～",
                                      "头发要被你摸顺了", "本鱼批准你继续摸"])
                self.say(line)
                self.speak(line)

    def _check_fullscreen(self):
        """前台是全屏程序（游戏 / 全屏视频 / F11 网页）且和她在同一块屏幕上：先躲起来，
        既不挡画面，也把 CPU 让给游戏；退出全屏后自动回来。"""
        try:
            on = self.cfg.get("fullscreen_hide", True) and self._foreground_fullscreen()
        except Exception:
            on = False
        if (on and self.isVisible() and self.game is None and not self.dragging
                and time.time() >= getattr(self, "_fs_ignore_until", 0.0)):
            self._fs_hidden = True
            self.chat_dialog.hide()
            self.food_panel.hide()
            self.hide()
        elif not on and getattr(self, "_fs_hidden", False):
            self._fs_hidden = False
            self.show()
            self.raise_()

    def _foreground_fullscreen(self):
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        own = {int(self.winId()), int(self.chat_dialog.winId())}
        if hwnd in own:
            return False
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", ctypes.wintypes.RECT),
                        ("rcWork", ctypes.wintypes.RECT), ("dwFlags", ctypes.c_ulong)]

        mon = user32.MonitorFromWindow(hwnd, 2)
        pet_mon = user32.MonitorFromWindow(int(self.winId()), 2)
        if mon != pet_mon:
            return False
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return False
        r = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        m = mi.rcMonitor
        return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom

    @staticmethod
    def _user_idle_seconds():
        """主人多久没碰鼠标键盘了（秒）。"""
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(lii)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
                return ((now - lii.dwTime) & 0xFFFFFFFF) / 1000.0
        except Exception:
            pass
        return 0.0

    def _check_nap(self, now):
        if now - self._last_input_check < 2.0:
            return
        self._last_input_check = now
        idle = self._user_idle_seconds()
        if not self.sleeping:
            # 主人离开 5 分钟以上又回来：蹦一下打招呼
            if idle >= 300:
                self._was_away = True
            elif self._was_away and idle < 3.0:
                self._was_away = False
                self._welcome_back()
        if self.sleeping:
            if self._sleep_until and now >= self._sleep_until:
                self._wake_up("嗯……睡饱了！")
            elif idle < 3.0 and now - self._sleep_since > 5:
                # 主人回来了：再赖一会儿床才醒
                if not self._sleep_input_back:
                    self._sleep_input_back = now + random.uniform(15, 35)
                elif now >= self._sleep_input_back:
                    self._wake_up("睡醒啦～你回来啦？")
            return
        if not self.cfg.get("auto_nap", True) or not self._use_3d() or now < self._nap_block_until:
            return
        if (self.dragging or self._throwing or self.chat_paused or self.game is not None
                or not self.isVisible() or self.action is not None or self.ds_busy):
            return
        hour = time.localtime().tm_hour
        limit = NAP_IDLE_MINUTES * 60 * (0.5 if (hour >= 23 or hour < 6) else 1.0)
        if idle >= limit:
            self.start_nap()

    def _welcome_back(self):
        if self.game is not None or self.chat_paused or self.dragging or not self.isVisible():
            return
        now = time.time()
        self.jump_t = 1.0
        self._happy_until = now + 1.6
        for i in range(2):
            self._hearts.append((now + i * 0.2, random.uniform(-0.1, 0.1), random.uniform(-12, 12)))
        line = random.choice(["你回来啦！", "终于理我了～", "刚刚去哪了？想你了", "欢迎回来，主人！"])
        self.say(line)
        self.speak(line)

    def start_nap(self, minutes=None):
        if self.sleeping:
            return
        if not self._use_3d():
            self.say("困了……可惜 2D 立绘躺不下", inner=True)
            return
        if self.game is not None:
            self.end_game()
        self.sleeping = True
        self._sleep_since = time.time()
        self._sleep_mirror = random.random() < 0.5
        self._flop = (time.time(), "down", self._sleep_mirror)     # 啪叽倒下
        self._sleep_until = time.time() + minutes * 60 if minutes else 0.0
        self._sleep_input_back = 0.0
        self.target = None
        self.action = None
        self.action_t = 0.0
        self.jump_t = 0.0
        self._bump_counter("nap")
        self.say(random.choice(["呼……就睡一小会儿", "肚皮朝天，充电中……", "zzz……别吵"]), inner=True)

    def _wake_up(self, line=None):
        if not self.sleeping:
            return
        self.sleeping = False
        self._sleep_until = 0.0
        self._sleep_input_back = 0.0
        self._nap_block_until = time.time() + 600      # 刚睡醒，十分钟内不会再自动睡
        self._flop = (time.time(), "up", self._sleep_mirror)       # 爬起来
        self.yaw = -90.0 if self._sleep_mirror else 90.0          # 侧身起来，再转过来看你
        self.rest_until = self.t * TICK + 4000
        self._perform_action("stretch")
        self._happy_until = time.time() + 1.2
        if line:
            self.say(line)
            self.speak(line)

    # ---------- 小游戏 / 玩具（games.py） ----------
    def start_game(self, kind):
        if self.sleeping:
            self._wake_up("唔……要玩游戏？好！")
        if self.game is not None:
            self.end_game()
        self.chat_dialog.hide()
        self.chat_paused = False
        cls = {"catch": games.CatchFishGame, "hide": games.HideSeekGame,
               "fetch": games.FetchGame, "dance": games.DanceShow}.get(kind)
        if cls is None:
            return
        self.target = None
        self.game = cls(self)
        self.game.start()

    def end_game(self):
        g, self.game = self.game, None
        if g is not None:
            g.stop()
        self.target = None
        self.rest_until = self.t * TICK + 3000
        if self.mode == "bottom":
            self._bottom_away = True                 # 玩完自己走回右下角的家
        else:
            self.home_x, self.home_y = self.x(), self.y()

    def throw_ball(self):
        self.start_game("fetch")

    def blow_bubbles(self):
        if self.sleeping:
            return
        self._perform_action("jump")
        self.toys.append(games.BubbleBurst(self))

    def sprite_geometry(self):
        """精灵在屏幕上的位置：(中心 x, 头顶 y, 脚底 y)。"""
        top = self.y() + BUBBLE_H + MARGIN
        return self.x() + self.width() / 2.0, float(top), float(top + self.cur_h)

    def _perform_action(self, kind):
        if kind == "jump":
            self.jump_t = 1.0
        elif kind == "sway":
            self.action, self.action_t = "sway", 1.0
        elif kind == "stretch":
            self.action, self.action_t = "stretch", 1.0
        elif kind == "flip":
            self._flip_dir = random.choice((-1, 1))
            self.action, self.action_t = "flip", 1.0
        elif kind == "jog":
            self.action, self.action_t = "jog", 1.0
        elif kind == "dance":
            if self._use_3d() and self.game is None and not self.sleeping and not self.dragging:
                self.start_game("dance")             # 3D 形象：完整的性感舞蹈秀（可以打拍子）
                return
            self.prev_key = self._sprite_key()
            self.cross_t = 1.0
            self.target = None
            if self.look != "cute":
                self._look_before_dance = self.look
                self.look = "cute"                   # 跳舞用可爱形象
            self.action, self.action_t = "dance", 1.0
        elif kind == "tantrum":
            self.prev_key = self._sprite_key()
            self.cross_t = 1.0
            self.target = None
            self._tantrum_dir = random.choice((-1, 1))
            self.action, self.action_t = "tantrum", 1.0
        elif kind == "eat":
            self.action, self.action_t = "eat", 1.0
        elif kind == "come":
            self._move_near_chat()
        elif kind == "back":
            self._move_home()
        elif kind == "stop":
            self.target = None
            self.jump_t = 0.0
            self.action = None
            self.action_t = 0.0
            self.rest_until = self.t * TICK + 120000
        elif kind == "cute":
            self.set_look("cute")
        elif kind == "sexy":
            self.set_look("sexy")

    def _maybe_idle_action(self):
        if random.random() < IDLE_ACTION_CHANCE:
            pick = random.random()
            if pick < 0.35:
                self._perform_action("jump")
            elif pick < 0.6:
                self._perform_action("sway")
            elif pick < 0.8:
                self._perform_action("stretch")
            elif pick < 0.9:
                if self.t - self.last_speak_tick >= 1500:
                    self.last_speak_tick = self.t
                    if pick < 0.82:
                        self.say(random.choice(INNER_LINES), inner=True)
                    else:
                        self.say(random.choice(LINES))
            elif pick < 0.9 + FLIP_CHANCE:
                self._perform_action("flip")
            elif pick < 0.9 + FLIP_CHANCE + JOG_CHANCE:
                self._perform_action("jog")
            elif (self._use_3d() and self.cfg.get("idle_bubbles", True)
                  and time.time() - getattr(self, "_last_idle_bubbles", 0.0) > 900):
                # 偶尔自己吹一串泡泡（15 分钟最多一次），戳破有奖励
                self._last_idle_bubbles = time.time()
                self.blow_bubbles()

    def _animate_to(self, x, y, duration=650):
        self._move_anim = QPropertyAnimation(self, b"pos", self)
        self._move_anim.setDuration(duration)
        self._move_anim.setStartValue(self.pos())
        self._move_anim.setEndValue(QPoint(int(x), int(y)))
        self._move_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._move_anim.start()

    def _move_near_chat(self):
        chat = self.chat_dialog
        screen = QApplication.screenAt(chat.frameGeometry().center()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = max(geo.left() + 10, min(geo.right() - self.width() - 10,
                                      chat.x() - self.width() + 30))
        y = max(geo.top() + 10, min(geo.bottom() - self.height() - 10,
                                     chat.y() + chat.height() - self.height()))
        self._animate_to(x, y)

    def _bottom_home(self):
        geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        return (geo.right() - self.width() - BOTTOM_HOME_MARGIN,
                geo.bottom() - self.height())

    def _move_home(self):
        if self.mode == "bottom":
            self._animate_to(*self._bottom_home())
            return
        self._animate_to(getattr(self, "home_x", self.x()),
                         getattr(self, "home_y", self.y()))

    def _on_chat_text_changed(self, _text):
        if self._text_eat_busy:
            return
        self._chat_text_changed_at = time.time()
        self._text_eat_rolled = False

    def _maybe_text_eat(self):
        """Low-probability gag: eat the unsent text in the pet's own chat box."""
        if not self.cfg.get("text_eat_enabled", True):
            return
        if self._text_eat_busy or time.time() < self._text_eat_cooldown_until:
            return
        if not self.chat_dialog.isVisible():
            return
        text = self.chat_dialog.input.text()
        if not text.strip() or not self.chat_dialog.input.hasFocus():
            return
        if self._chat_text_changed_at <= 0 or time.time() - self._chat_text_changed_at < 2.5:
            return
        if self._text_eat_rolled:
            return
        self._text_eat_rolled = True
        if random.random() < float(self.cfg.get("text_eat_chance", 0.12)):
            self._start_text_eat(text)

    def _start_text_eat(self, text=None):
        if self._text_eat_busy:
            return
        if text is None and not self.chat_dialog.isVisible():
            self._show_chat_dialog()
            self.say("先打一句，再让我吃～")
            return
        if text is None:
            text = self.chat_dialog.input.text()
        if not text.strip():
            self.say("先在聊天框里打一句～")
            return
        self._text_eat_busy = True
        self._text_eat_saved = text
        self._text_eat_origin = self.pos()
        lo = float(self.cfg.get("text_eat_cooldown_min", 5))
        hi = max(lo, float(self.cfg.get("text_eat_cooldown_max", 10)))
        self._text_eat_cooldown_until = time.time() + random.uniform(lo, hi) * 60
        self.chat_dialog.input.clear()

        chat = self.chat_dialog
        screen = QApplication.screenAt(chat.frameGeometry().center()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        tx = max(geo.left() + 10, min(geo.right() - self.width() - 10,
                                       chat.x() - self.width() + 30))
        ty = max(geo.top() + 10, min(geo.bottom() - self.height() - 10,
                                     chat.y() + chat.height() - self.height()))
        self._text_eat_anim = QPropertyAnimation(self, b"pos", self)
        self._text_eat_anim.setDuration(650)
        self._text_eat_anim.setStartValue(self.pos())
        self._text_eat_anim.setEndValue(QPoint(int(tx), int(ty)))
        self._text_eat_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._text_eat_anim.finished.connect(self._text_eat_chomp)
        self._text_eat_anim.start()

    def set_text_eat_enabled(self, on):
        self.cfg["text_eat_enabled"] = bool(on)
        self._save_config()
        self.say("文字恶作剧开啦～" if on else "好吧，不抢你的字了")

    def _text_eat_chomp(self):
        self.action, self.action_t = "eat", 1.0
        shown = self._text_eat_saved.replace("\n", " ")
        if len(shown) > 24:
            shown = shown[:24] + "…"
        self.say(f"嗷呜——「{shown}」")
        QTimer.singleShot(1200, self._text_eat_spit)

    def _text_eat_spit(self):
        box = self.chat_dialog.input
        if not box.text():
            box.setText(self._text_eat_saved)
        else:
            self.say("你自己又打了一句，那就留给你吧～")
        box.setFocus()
        self._text_eat_busy = False
        self._text_eat_rolled = True
        self._text_eat_anim = QPropertyAnimation(self, b"pos", self)
        self._text_eat_anim.setDuration(600)
        self._text_eat_anim.setStartValue(self.pos())
        self._text_eat_anim.setEndValue(self._text_eat_origin)
        self._text_eat_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._text_eat_anim.start()

    def _queue_say(self, text):
        """后台线程调用：只入队，由主线程 tick 统一弹出显示（线程安全）"""
        self._say_queue.append(text)

    def _queue_chat(self, text):
        """后台线程调用：把回复排进聊天窗队列，由主线程更新界面"""
        self._chat_queue.append(text)

    def say(self, text, inner=False):
        if text == self.last_line and not text.startswith("天气"):
            return
        self.last_line = text
        self.bubble_inner = inner
        self.bubble_text = f"（{text}）" if inner else text
        duration = 12.0 if self.chat_paused else 2.8
        self.bubble_until = self.t * TICK / 1000.0 + duration
        self.update()

    def check_system_status(self):
            now = self.t * TICK

            if now - getattr(self, "last_system_check", 0) < 10000:
                return

            self.last_system_check = now

            cpu = psutil.cpu_percent()

            if cpu >= 90:
                self.say("CPU跑满了，再这样下去我就卡死了")
                return

            ram = psutil.virtual_memory().percent

            if ram >= 95:
                self.say("内存爆了，快关掉几个没用的东西吧，注意，别把我关了")
                return

            if GPU_AVAILABLE:
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(0)

                    temp = pynvml.nvmlDeviceGetTemperature(
                        handle,
                        pynvml.NVML_TEMPERATURE_GPU
                    )

                    if temp > 80:
                        self.say("我感觉我的鱼鳍快熟了")

                except Exception as e:
                    print("GPU读取失败:", e)

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.sleeping:
                self._ignore_release = True
                self._wake_up(random.choice(["唔……谁戳我", "让我再睡五分钟……", "干嘛啦，正做梦呢"]))
                return
            if self.game is not None and self.game.on_pet_pressed():
                self._ignore_release = True
                return
            self._ignore_release = False
            self.last_press_pos = e.globalPosition().toPoint()
            self.dragging = False
            self.drag_start_pos = e.globalPosition().toPoint()
            self.function_panel.hide()
            self.chat_dialog.hide()
            self.chat_paused = True
            pos = e.position().toPoint()
            rel_y = pos.y() - BUBBLE_H
            if rel_y < self.cur_h * 0.42:
                self._click_part = "head"
            elif rel_y > self.cur_h * 0.72:
                self._click_part = "tail"
            else:
                self._click_part = "body"
            self._mouse_down = True
            self._long_pressed = False
            self._press_timer.stop()
            self._pet_timer.stop()
            self._throwing = False
            self._vel_x = 0.0
            self._vel_y = 0.0
            self._drag_samples = []
            if self._click_part == "head":
                self._press_timer.start(500)

    def mouseMoveEvent(self, e):
        if getattr(self, "_ignore_release", False):
            return
        if e.buttons() & Qt.MouseButton.LeftButton and self.drag_start_pos is not None:
            delta = e.globalPosition().toPoint() - self.drag_start_pos
            if not self.dragging and delta.manhattanLength() > 6:
                self.dragging = True
                self.drag_offset = e.globalPosition().toPoint() - QPoint(self.x(), self.y())
            if self.dragging and self.drag_offset is not None:
                pos = e.globalPosition().toPoint() - self.drag_offset
                self.move(pos)
                now = time.time()
                self._drag_samples.append(
                    (now, e.globalPosition().x(), e.globalPosition().y()))
                self._drag_samples = [s for s in self._drag_samples if now - s[0] < 0.12]
                if abs(delta.x()) > 10:
                    self._set_dir("left" if delta.x() < 0 else "right", 1 if delta.x() < 0 else -1)
                self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and getattr(self, "_ignore_release", False):
            self._ignore_release = False
            self._mouse_down = False
            self.drag_start_pos = None
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._mouse_down = False
            self._press_timer.stop()
            self._pet_timer.stop()
            if self.dragging:
                self.dragging = False
                self.drag_offset = None
                self.drag_start_pos = None
                self._set_dir("down", 1)
                self.target = None
                self.rest_until = self.t * TICK + random.randint(6000, 14000)
                if len(self._drag_samples) >= 2:
                    t0, x0, y0 = self._drag_samples[0]
                    t1, x1, y1 = self._drag_samples[-1]
                    dt = max(0.02, t1 - t0)
                    vx = (x1 - x0) / dt
                    vy = (y1 - y0) / dt
                    if (vx * vx + vy * vy) ** 0.5 > 180:
                        self._vel_x, self._vel_y = vx, vy
                        self._throwing = True
                        self._spin_dir = 1 if vx < 0 else -1      # 在空中朝飞行方向转圈
                        self._bump_counter("throw")
                self._drag_samples = []
                if random.random() < 0.5 and not self._throwing:
                    self.say(random.choice(DRAG_LINES))
                if not self._throwing:
                    self.home_x, self.home_y = self.x(), self.y()
                self.chat_paused = False
            elif self._long_pressed:
                self._long_pressed = False
                self.chat_paused = False
            else:
                self._click_timer.start(280)  # 等双击判定；单击则回嘴+弹聊天面板
            self.last_press_pos = None
            self.drag_start_pos = None

    def mouseDoubleClickEvent(self, e):
        if self.sleeping or self.game is not None:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self.food_panel.popup_at(self.x() + self.width() / 2, self.y() + BUBBLE_H)

    def _on_single_click(self):
        """单击：蹦跳回嘴 + 直接弹出小聊天输入条"""
        now = time.time()
        if self._click_part == "tail":
            self._set_dir("left" if self.facing >= 0 else "right",
                          -1 if self.facing >= 0 else 1)
            # 3D：被碰到尾巴会转过身去看一眼
            self._look_back_until = now + 1.2
            self._look_back_side = random.choice((-1, 1))
        elif self._click_part == "head":
            self._happy_until = now + 1.0
        else:
            self._blink_until = now + 0.16
        if self._click_part == "body":
            now = time.time()
            self._poke_times = [t for t in self._poke_times if now - t < 2.0]
            self._poke_times.append(now)
            if len(self._poke_times) >= 3:
                self._poke_times.clear()
                self._angry_until = now + 20
                line = random.choice(["别戳了！再戳我生气了！", "你戳上瘾了是吧！", "我生气了，哄不好的那种！"])
                self.say(line)
                self.speak(line)
                self.pet_state["affection"] = max(
                    0, int(self.pet_state.get("affection", 0)) - 1)
                self._show_chat_dialog()
                return
        if random.random() < 0.7:
            self.jump_t = 1.0
        if random.random() < 0.7:
            mood = self._mood()
            if mood == "angry":
                pool = ["哼，不理你了。", "别碰我！", "除非给我三条小鱼干，否则不原谅你。"]
            elif mood == "hungry":
                pool = ["饿饿，饭饭！", "再不给吃的我就啃桌角了！", "肚子在唱空城计……"]
            elif mood == "clingy":
                pool = ["你终于来啦～", "抱抱！今天也要陪我。", "别走嘛，再待一会儿。"]
            elif self._click_part == "head":
                pool = HEAD_LINES
            elif self._click_part == "tail":
                pool = TAIL_LINES
            else:
                pool = BODY_LINES + PLAYFUL_LINES
            line = random.choice(pool)
            self.say(line)
            self.speak(line)
        self._show_chat_dialog()

    def _on_long_press(self):
        if not self._mouse_down or self.dragging or self._click_part != "head":
            return
        self._long_pressed = True
        self._pet_count = 0
        self._bump_daily("pet")
        self._on_pet_tick()
        self._pet_timer.start()

    def _on_pet_tick(self):
        if not self._mouse_down or self.dragging:
            self._pet_timer.stop()
            return
        self._pet_count += 1
        now = time.time()
        self._happy_until = now + 1.3
        self._hearts.append((now, random.uniform(-0.1, 0.1), random.uniform(-12, 12)))
        line = random.choice(["呼噜呼噜……", "再摸一会儿……", "舒服～", "头发要乱了啦。"])
        self.say(line)
        self.speak(line)
        self.pet_state["affection"] = min(
            100, int(self.pet_state.get("affection", 0)) + 1)
        self.add_exp(1)
        self._bump_counter("pet")
        if self._pet_count >= 3:
            self._pet_timer.stop()

    def _apply_throw_physics(self):
        dt = TICK / 1000.0
        geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self._vel_y += 2400.0 * dt
        x = self.x() + self._vel_x * dt
        y = self.y() + self._vel_y * dt
        w, h = self.width(), self.height()
        if x < geo.left():
            x = geo.left()
            self._vel_x = -self._vel_x * 0.55
        elif x + w > geo.right():
            x = geo.right() - w
            self._vel_x = -self._vel_x * 0.55
        if y < geo.top():
            y = geo.top()
            self._vel_y = -self._vel_y * 0.55
        if y + h > geo.bottom():
            y = geo.bottom() - h
            impact = abs(self._vel_y)
            self._vel_y = -self._vel_y * 0.5
            self._vel_x *= 0.75
            self._squash = max(self._squash, min(1.0, impact / 900.0))   # 落地压扁再弹回
            if impact > 650:
                line = random.choice(["晕鱼了……", "摔死我了！", "我的鱼生啊……"])
                self.say(line)
                self.speak(line)
                self.jump_t = 0.5
                self._dizzy_until = time.time() + 2.4
            if abs(self._vel_y) < 90:
                self._vel_y = 0.0
                self._throwing = False
                self.home_x, self.home_y = self.x(), self.y()
                self.rest_until = self.t * TICK + 6000
        self.move(int(x), int(y))
        if abs(self._vel_x) < 15 and abs(self._vel_y) < 15:
            self._throwing = False
            self.home_x, self.home_y = self.x(), self.y()

    def on_food(self, food):
        self.food_panel.hide()
        costs = {"🐟": 0, "🍰": 1, "🍭": 1, "🍡": 2, "🍚": 2, "💎": 5}
        cost = costs.get(food, 0)
        coins = int(self.pet_state.get("fish_coins", 10))
        if cost > coins:
            line = f"小鱼干不够啦（{food} 要 {cost} 条），做每日任务赚一点吧。"
            self.say(line)
            self.speak(line)
            return
        if cost:
            self.pet_state["fish_coins"] = coins - cost
        if self.sleeping:
            self._wake_up()
        self.eat_t = 1.0
        self.jump_t = 0.6
        self.action, self.action_t = "eat", 1.0
        now = time.time()
        self._happy_until = now + 1.6
        self._hearts.append((now + 0.2, random.uniform(-0.1, 0.1), random.uniform(-12, 12)))
        lines = FOOD_LINES.get(food, ["好吃！"])
        line = random.choice(lines)
        self.say(line)
        self.speak(line)
        st = self.pet_state
        gains = {"🍚": 30}   # 一大碗米饭更管饱
        st["hunger"] = min(100, int(st.get("hunger", 70)) + gains.get(food, 15))
        st["affection"] = min(100, int(st.get("affection", 0)) + 2)
        self.add_exp(10)
        self._bump_daily("feed")
        self._bump_counter("feed")

    def _show_chat_dialog(self):
        key = self.cfg.get("ds_api_key", "")
        if not key:
            self.say("请先在右键菜单里设置 DeepSeek Key！")
            self.chat_paused = False
            return
        self.chat_paused = True
        self.chat_dialog.popup_at(
            self.x() + self.width() / 2,
            self.y()
        )

    """def _get_city_by_ip(self):
        try:
            r = requests.get("http://ip-api.com/json/?fields=city&lang=zh-CN", timeout=5)
            if r.status_code == 200:
                city = r.json().get("city", "")
                if city:
                    return city
        except:
            pass
        return "汕头" """

    def _get_weather(self):
        # 网络请求放到后台线程：以前在主线程里同步请求，网络慢时整只桌宠会卡住最多 10 秒
        if getattr(self, "_weather_busy", False):
            return
        self._weather_busy = True
        self.say("我去窗外看一眼……")
        threading.Thread(target=self._weather_worker, args=(self.cfg.get("city", "汕头"),),
                         daemon=True).start()

    def _weather_worker(self, city):
        try:
            w = fetch_weather(city)
            self._weather_cache = (time.time(), city, weather_brief(w))   # 接着在聊天里问也有数据
            today = w["days"][0] if w["days"] else None
            extra = f"，今天{today['min']}~{today['max']}°" if today else ""
            self._queue_say(f"天气：{city}现在{w['temp']}°，{w['desc']}{extra}")
        except Exception as e:
            print("天气错误:", repr(e))
            self._queue_say("天气获取失败，网络好像不太通")
        finally:
            self._weather_busy = False
    

    def _build_menu(self):
        def check(menu, label, on, slot):
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(bool(on))
            a.triggered.connect(slot)
            return a

        m = QMenu(self)
        m.addAction("打开聊天", self._show_chat_dialog)
        play = m.addMenu("小游戏 / 一起玩")
        play.addAction("🐟 接小鱼干（鼠标左右移动接）", lambda: self.start_game("catch"))
        play.addAction("⚽ 丢球给她捡", self.throw_ball)
        play.addAction("🙈 捉迷藏", lambda: self.start_game("hide"))
        play.addAction("🫧 吹泡泡（点泡泡）", self.blow_bubbles)
        if self.game is not None:
            play.addSeparator()
            play.addAction("结束当前游戏", self.end_game)
        act = m.addMenu("互动")
        act.addAction("摸摸头", self.pet_head)
        act.addAction("逗她一下", self.tease_pet)
        act.addAction("💃 性感舞蹈秀（在节拍上点她）", lambda: self._perform_action("dance"))
        act.addAction("撒泼打滚", lambda: self._perform_action("tantrum"))
        act.addAction("吃掉这句话", lambda: self._start_text_eat())
        if self.sleeping:
            act.addAction("叫醒她", lambda: self._wake_up("唔……醒了醒了"))
        else:
            act.addAction("哄她睡一觉", lambda: self.start_nap(minutes=3))
        grow = m.addMenu("养成")
        grow.addAction("查看养成状态", self.show_status)
        grow.addAction("成就", self._show_achievements)
        m.addSeparator()
        mode_menu = m.addMenu("模式")
        for label, key in [("悠闲（推荐）", "relaxed"), ("底部游走", "bottom"),
                           ("自由散步", "wander"), ("跟随鼠标", "follow"), ("原地待着", "still")]:
            a = mode_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.mode == key)
            a.triggered.connect(lambda _, k=key: self.set_mode(k))
        size_menu = m.addMenu("大小")
        for label, mult in SIZE_LEVELS.items():
            a = size_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(self.cur_h - 340 * mult) < 2)
            a.triggered.connect(lambda _, v=mult: self.set_size(v))
        look_menu = m.addMenu("形象")
        for label, key in (("可爱", "cute"), ("性感", "sexy")):
            a = look_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.look == key)
            a.triggered.connect(lambda _, k=key: self.set_look(k))
        look_menu.addSeparator()
        a3 = check(look_menu, "3D 形象（会转身）", self._use_3d(), lambda on: self.set_render3d(on))
        a3.setEnabled(bool(self.r3d.ok))
        check(look_menu, "看向鼠标", self.cfg.get("look_at_cursor", True),
              lambda on: self._set_cfg_flag("look_at_cursor", on))
        check(look_menu, "没人理我就睡午觉", self.cfg.get("auto_nap", True),
              lambda on: self._set_cfg_flag("auto_nap", on))
        check(look_menu, "待机时偶尔吹泡泡", self.cfg.get("idle_bubbles", True),
              lambda on: self._set_cfg_flag("idle_bubbles", on))
        check(look_menu, "全屏游戏 / 看视频时自动躲起来", self.cfg.get("fullscreen_hide", True),
              lambda on: self._set_cfg_flag("fullscreen_hide", on))

        st = m.addMenu("设置")
        check(st, "语音", self.cfg.get("voice_enabled", True), self.set_voice_enabled)
        check(st, "聊天时深度思考（更准，但回得慢）", self.cfg.get("deep_think", False), self.set_deep_think)
        op_menu = st.addMenu("聊天框透明度")
        current_op = float(self.cfg.get("chat_opacity", 0.75))
        for label, value in [("20%", 0.2), ("40%", 0.4), ("60%", 0.6),
                             ("75%", 0.75), ("90%", 0.9), ("全透明", 0.0)]:
            check(op_menu, label, abs(current_op - value) < 0.01,
                  lambda _, v=value: self.set_chat_opacity(v))
        check(st, "文字恶作剧", self.cfg.get("text_eat_enabled", True),
              lambda on: self.set_text_eat_enabled(on))
        st.addSeparator()
        st.addAction("设置 DeepSeek Key…", self._set_key_dialog)
        st.addAction(f"设置城市（现在：{self.cfg.get('city', '汕头')}）…", self._set_city_dialog)
        st.addSeparator()
        check(st, "鼠标穿透（点不到它）", self.cfg["passthrough"], lambda on: self.set_passthrough(on))
        check(st, "窗口置顶", self.cfg["topmost"], lambda on: self.set_topmost(on))
        check(st, "开机自启", self.cfg["autostart"], lambda on: self.set_autostart(on))
        tools = m.addMenu("工具")
        tools.addAction("让 DSH 干活…", self._on_dsh_menu)
        tools.addAction("查看天气", self._get_weather)
        m.addSeparator()
        m.addAction("显示/隐藏", self.toggle_visible)
        m.addAction("回到屏幕内", self.snap_into_screen)
        m.addAction("退出", self.quit_app)
        return m

    def _set_cfg_flag(self, key, on):
        self.cfg[key] = bool(on)
        self._save_config()

    def set_deep_think(self, on):
        self._set_cfg_flag("deep_think", on)
        self.say("深度思考开啦：先想清楚再回答，要多等一会儿～" if on else "深度思考关了，回得快一点～")

    def _set_key_dialog(self):
        key, ok = QInputDialog.getText(
            self, 
            "设置 DeepSeek Key", 
            "输入你的 API Key（从 platform.deepseek.com 获取）:",
            QLineEdit.EchoMode.Normal,
            self.cfg.get("ds_api_key", "")
        )
        if ok and key.strip():
            self.cfg["ds_api_key"] = key.strip()
            self._save_config()
            self.say("Key 设置成功！")
        elif ok and not key.strip():
            self.say("Key 不能为空")

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Context:
            self.tray.setContextMenu(self._build_menu())
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def contextMenuEvent(self, e):
        self._build_menu().exec(e.globalPos())

    # ---------- 功能 ----------
    def set_mode(self, mode):
        if mode not in ("relaxed", "bottom", "wander", "follow", "still"):
            return
        self.mode = mode
        self.target = None
        self._bottom_away = False
        self.cfg["mode"] = mode
        if mode == "relaxed":
            self.home_x, self.home_y = self.x(), self.y()
        elif mode == "bottom":
            hx, hy = self._bottom_home()
            self.move(hx, hy)
            self.home_x, self.home_y = hx, hy
            self.snap_into_screen()
            self.rest_until = self.t * TICK + random.randint(*RELAX_ARRIVAL_REST_MS)
        self._save_config()

    def set_size(self, mult):
        self.cur_h = int(340 * mult)
        self.cfg["size"] = mult
        self.cross_t = 0.0
        self.prev_key = None
        self.sprites = self._load_sprites(self.cur_h)
        self.r3d.load(self.cur_h)
        self._side_parts_cache = {}
        self._apply_window_size()
        self.snap_into_screen()
        self._save_config()

    def snap_into_screen(self):
        geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        x = max(geo.left(), min(geo.right() - self.width(), self.x()))
        y = max(geo.top(), min(geo.bottom() - self.height(), self.y()))
        self.move(x, y)

    def _apply_passthrough(self, on):
        hwnd = int(self.winId())
        GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
        style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        style = style | WS_EX_LAYERED
        if on:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)

    def set_passthrough(self, on):
        self.cfg["passthrough"] = bool(on)
        self._apply_passthrough(bool(on))
        self._save_config()
        if on:
            self.say("我隐身了！右键托盘图标解除～")

    def set_topmost(self, on):
        self.cfg["topmost"] = bool(on)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        self.show()
        self._save_config()

    def set_look(self, look):
        if look not in ("cute", "sexy"):
            return
        self.look = look
        self._look_before_dance = None
        self.cfg["look"] = look
        self.say("换好啦，可爱模式～" if look == "cute" else "换好啦，性感模式～")
        self.update()
        self._save_config()

    def set_render3d(self, on):
        if on and not self.r3d.ok:
            self.cfg["render3d"] = False
            self.say("3D 帧还没装好，先用 2D 立绘～（运行 tools/build_3d.py 生成）")
            return
        if not on and self.sleeping:
            self._wake_up()
        self.cfg["render3d"] = bool(on)
        self.prev_key = None
        self.cross_t = 0.0
        bottom = self.y() + self.height()
        self._apply_window_size()
        self.move(self.x(), bottom - self.height())
        self.snap_into_screen()
        self.say("换成 3D 形象啦～" if on else "换回 2D 立绘～")
        self.update()
        self._save_config()

    def set_autostart(self, on):
        self.cfg["autostart"] = bool(on)
        lnk = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                           "Start Menu", "Programs", "Startup", "肚皮朝天.lnk")
        try:
            if on:
                ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{}');"
                      "$s.TargetPath='{}';$s.Arguments='\"{}\"';$s.WorkingDirectory='{}';$s.Save()"
                      .format(lnk, PYTHONW,
                              "" if getattr(sys, "frozen", False) else os.path.join(APP_DIR, "桌宠.py"),
                              APP_DIR))
                subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
                self.say("已开机自启，明天见～")
            else:
                if os.path.exists(lnk):
                    os.remove(lnk)
                self.say("已取消开机自启")
        except Exception as ex:
            QMessageBox.warning(self, "开机自启", f"设置失败：{ex}")
        self._save_config()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            # 手动叫出来时，5 分钟内不因为全屏程序再自动躲起来
            self._fs_hidden = False
            self._fs_ignore_until = time.time() + 300
            self.show()
            self.raise_()

    def quit_app(self):
        if self.game is not None:
            self.end_game()
        for toy in list(self.toys):
            toy.close_toy()
        self._save_all()
        self._stop_hotkeys()
        if getattr(self, "_mouse_listener", None):
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if getattr(self, "_hotkeys", None):
            try:
                self._hotkeys.stop()
            except Exception:
                pass
        self.tray.hide()
        QApplication.quit()


def _setup_logging():
    """pythonw 没有控制台，出错就悄无声息：把报错写进 pet.log（超过 512KB 自动换新）。"""
    if sys.stderr is not None and getattr(sys.stderr, "isatty", lambda: False)():
        return
    path = os.path.join(APP_DIR, "pet.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            os.replace(path, path + ".1")
        f = open(path, "a", encoding="utf-8", buffering=1)
        f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 启动 =====\n")
        sys.stderr = f
        sys.stdout = f
    except Exception:
        pass


_INSTANCE_MUTEX = None


def _claim_single_instance():
    """开机自启 + 手动双击会跑出两只鱼、互相覆盖存档：用命名互斥体只留一只。"""
    global _INSTANCE_MUTEX
    try:
        _INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\dafeiyu_pet_single_instance")
        return ctypes.windll.kernel32.GetLastError() != 183          # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def main():
    if not _claim_single_instance():
        # 已经有一只在跑：让它出来打个招呼，这边直接退出
        try:
            open(os.path.join(APP_DIR, "show_pet.flag"), "w").close()
        except OSError:
            pass
        return
    _setup_logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    w = PetWindow()
    # 关机 / 注销 / 意外退出前把配置、养成、聊天都存好
    app.aboutToQuit.connect(w._save_all)
    app.commitDataRequest.connect(lambda *_: w._save_all())
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "肚皮朝天出错", str(ex))
        except Exception:
            pass
        raise