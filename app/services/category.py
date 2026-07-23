"""应用分类与默认时段/限额策略。"""
from __future__ import annotations

from datetime import time
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import App, TimeWindow

# category codes
CAT_ENTERTAINMENT = "entertainment"  # 游戏娱乐
CAT_STUDY = "study"  # 学习
CAT_WORK = "work"  # 办公
CAT_OTHER = "other"  # 其他

CATEGORY_LABELS: Dict[str, str] = {
    CAT_ENTERTAINMENT: "游戏娱乐",
    CAT_STUDY: "学习",
    CAT_WORK: "办公",
    CAT_OTHER: "其他",
}

VALID_CATEGORIES = set(CATEGORY_LABELS.keys())

# 游戏娱乐：周末 06:00–22:20，日限 2 小时
# 其他分类：每天 05:00–22:20，不限时长
_ENT_START = time(6, 0)
_ENT_END = time(22, 20)
_OTHER_START = time(5, 0)
_OTHER_END = time(22, 20)


def normalize_category(value: Optional[str]) -> str:
    v = (value or CAT_OTHER).strip().lower()
    aliases = {
        "游戏": CAT_ENTERTAINMENT,
        "娱乐": CAT_ENTERTAINMENT,
        "游戏娱乐": CAT_ENTERTAINMENT,
        "game": CAT_ENTERTAINMENT,
        "fun": CAT_ENTERTAINMENT,
        "学习": CAT_STUDY,
        "study": CAT_STUDY,
        "learn": CAT_STUDY,
        "办公": CAT_WORK,
        "工作": CAT_WORK,
        "work": CAT_WORK,
        "office": CAT_WORK,
        "其他": CAT_OTHER,
        "other": CAT_OTHER,
    }
    if v in aliases:
        return aliases[v]
    if v in VALID_CATEGORIES:
        return v
    return CAT_OTHER


def category_label(code: Optional[str]) -> str:
    return CATEGORY_LABELS.get(normalize_category(code), "其他")


def default_policy(category: Optional[str]) -> Dict:
    """返回该分类的默认限额与时段描述。"""
    cat = normalize_category(category)
    if cat == CAT_ENTERTAINMENT:
        return {
            "category": cat,
            "daily_limit_minutes": 120,
            "session_limit_minutes": None,
            "weekdays": [5, 6],  # 周六、周日
            "start_time": _ENT_START,
            "end_time": _ENT_END,
            "summary": "周末 06:00–22:20，日限 2 小时",
        }
    return {
        "category": cat,
        "daily_limit_minutes": None,
        "session_limit_minutes": None,
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "start_time": _OTHER_START,
        "end_time": _OTHER_END,
        "summary": "每天 05:00–22:20，不限时长",
    }


def apply_category_defaults(db: Session, app: App, *, set_limits: bool = True) -> App:
    """
    按分类写入默认时段（替换已有时段），并按策略设置日限。
    """
    policy = default_policy(app.category)
    app.category = policy["category"]
    if set_limits:
        app.daily_limit_minutes = policy["daily_limit_minutes"]
        app.session_limit_minutes = policy["session_limit_minutes"]

    db.query(TimeWindow).filter(TimeWindow.app_id == app.id).delete()
    for wd in policy["weekdays"]:
        db.add(
            TimeWindow(
                app_id=app.id,
                weekday=wd,
                start_time=policy["start_time"],
                end_time=policy["end_time"],
            )
        )
    return app


_ENTERTAINMENT_KEYWORDS = (
    "steam",
    "epic",
    "game",
    "games",
    "play",
    "bilibili",
    "哔哩",
    "douyin",
    "抖音",
    "tiktok",
    "youtube",
    "netflix",
    "iqiyi",
    "爱奇艺",
    "youku",
    "优酷",
    "tencentvideo",
    "腾讯视频",
    "qqmusic",
    "网易云",
    "cloudmusic",
    "spotify",
    "wechat",
    "微信",
    "weixin",
    "qq.exe",
    "discord",
    "telegram",
    "origin",
    "battle.net",
    "blizzard",
    "riot",
    "league",
    "英雄联盟",
    "valorant",
    "minecraft",
    "roblox",
    "genshin",
    "原神",
    "hoyoverse",
    "mihoyo",
    "launcher",  # 常见游戏启动器路径片段，需结合其他词；单独时偏弱
    "娱乐",
    "游戏",
)

_STUDY_KEYWORDS = (
    "study",
    "learn",
    "edu",
    "course",
    "课堂",
    "学习",
    "作业",
    "exam",
    "anki",
    "notion",
    "obsidian",
    "typora",
    "word",
    "excel",
    "powerpoint",
    "wps",
    "pdf",
    "zotero",
    "endnote",
    "matlab",
    "jupyter",
    "vscode",
    "cursor",
    "pycharm",
    "idea64",
    "visual studio",
)

_WORK_KEYWORDS = (
    "outlook",
    "teams",
    "zoom",
    "dingtalk",
    "钉钉",
    "feishu",
    "飞书",
    "lark",
    "slack",
    "office",
    "sap",
    "erp",
    "企业微信",
    "wxwork",
)


def suggest_category(name: str = "", exe_path: str = "", process_name: str = "") -> str:
    """根据名称/路径做启发式分类建议（可被用户覆盖）。"""
    blob = f"{name} {exe_path} {process_name}".lower()
    # 学习/办公优先于泛娱乐关键词（如 vscode 路径）
    if any(k in blob for k in _STUDY_KEYWORDS):
        return CAT_STUDY
    if any(k in blob for k in _WORK_KEYWORDS):
        return CAT_WORK
    # launcher 单独出现不算娱乐；与 game/steam 等组合才算
    ent_hits = [k for k in _ENTERTAINMENT_KEYWORDS if k != "launcher" and k in blob]
    if ent_hits:
        return CAT_ENTERTAINMENT
    if "launcher" in blob and any(
        k in blob for k in ("game", "steam", "epic", "riot", "mihoyo", "hoyoverse")
    ):
        return CAT_ENTERTAINMENT
    return CAT_OTHER
