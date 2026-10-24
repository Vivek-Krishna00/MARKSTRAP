"""OASIS agent profiles. Copied from MiroFish backend/app/services/oasis_profile_generator.py (AGPL-3.0, commit 7657031).

Kept: _coerce_to_str, _coerce_to_str_list, OasisAgentProfile, _save_twitter_csv (now a function).
Removed: OasisProfileGenerator (Zep graph search + LLM-written persona), the `mbti` field and its archetype rules,
the Reddit writer (OASIS's Reddit system prompt hard-codes "MBTI personality type of ..."; Twitter uses only user_char).
Personality now comes from MarkStrap's engine/personality.py and arrives here as behaviour text in `persona`.
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def _coerce_to_str(value: Any) -> str:
    """Coerce a value to a plain string.

    Handles dict, list, and other non-string types that may be returned
    by LLM JSON parsing.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ('text', 'value', 'description', 'content', 'summary', 'name'):
            if key in value:
                candidate = _coerce_to_str(value[key])
                if candidate:
                    return candidate
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        str_items = [_coerce_to_str(item) for item in value]
        str_items = [item for item in str_items if item]
        return ', '.join(str_items)
    return str(value)


def _coerce_to_str_list(value: Any) -> List[str]:
    """Coerce a value to a list of strings.

    Handles nested structures that may be returned by LLM JSON parsing.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        result: List[str] = []
        for item in value:
            if isinstance(item, (list, tuple)):
                result.extend(_coerce_to_str_list(item))
            else:
                text = _coerce_to_str(item)
                if text:
                    result.append(text)
        return result
    text = _coerce_to_str(value)
    return [text] if text else []


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile数据结构"""
    # 通用字段
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str

    # 可选字段 - Reddit风格
    karma: int = 1000

    # 可选字段 - Twitter风格
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500

    # 额外人设信息
    age: Optional[int] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)

    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def __post_init__(self):
        """Normalize structured LLM fields once at the profile boundary."""
        self.bio = _coerce_to_str(self.bio) or self.name
        self.persona = _coerce_to_str(self.persona) or (
            f"{self.name} is a participant in social discussions."
        )
        self.country = _coerce_to_str(self.country) or None
        self.profession = _coerce_to_str(self.profession) or None
        self.gender = _coerce_to_str(self.gender) or None
        self.interested_topics = _coerce_to_str_list(self.interested_topics)


def save_twitter_csv(profiles: List[OasisAgentProfile], file_path: str):
    """
    保存Twitter Profile为CSV格式（符合OASIS官方要求）

    OASIS Twitter要求的CSV字段：
    - user_id: 用户ID（根据CSV顺序从0开始）
    - name: 用户真实姓名
    - username: 系统中的用户名
    - user_char: 详细人设描述（注入到LLM系统提示中，指导Agent行为）
    - description: 简短的公开简介（显示在用户资料页面）
    """
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'name', 'username', 'user_char', 'description'])
        for idx, profile in enumerate(profiles):
            # user_char: 完整人设（bio + persona），用于LLM系统提示
            user_char = profile.bio
            if profile.persona and profile.persona != profile.bio:
                user_char = f"{profile.bio} {profile.persona}"
            user_char = user_char.replace('\n', ' ').replace('\r', ' ')
            description = profile.bio.replace('\n', ' ').replace('\r', ' ')
            writer.writerow([idx, profile.name, profile.user_name, user_char, description])
