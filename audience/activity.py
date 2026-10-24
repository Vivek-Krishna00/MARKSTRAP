"""Feed actions -> memory episodes. Ported from MiroFish backend/app/services/zep_graph_memory_updater.py
(AGPL-3.0, commit 7657031): AgentActivity.to_episode_text and _build_episode_payloads, descriptions translated to
English. Zep's client, worker thread and retry/barrier logic are dropped; the engine writes the episodes to Graphiti.
"""
from dataclasses import dataclass
from typing import Any, Dict, List

MAX_EPISODE_CHARS = 9_500  # as in MiroFish
SKIP = {"DO_NOTHING", "REFRESH", "SIGN_UP", "TREND", "INTERVIEW"}


@dataclass
class AgentActivity:
    platform: str
    agent_id: int
    agent_name: str
    action_type: str
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str

    def to_episode_text(self) -> str:
        """Natural language, no simulation jargon, so the graph extracts entities and relations from it."""
        describe = {
            "CREATE_POST": self._create_post, "LIKE_POST": self._like_post, "DISLIKE_POST": self._dislike_post,
            "REPOST": self._repost, "QUOTE_POST": self._quote_post, "FOLLOW": self._follow,
            "CREATE_COMMENT": self._create_comment, "LIKE_COMMENT": self._like_comment,
            "DISLIKE_COMMENT": self._dislike_comment, "SEARCH_POSTS": self._search,
            "SEARCH_USER": self._search_user, "MUTE": self._mute,
        }.get(self.action_type, self._generic)
        # Keep the event time in the text as well, so a multi-action batch keeps its order.
        text = describe().replace("\r", " ").replace("\n", " / ")  # one action per line
        return f"[{self.timestamp}] [{self.platform} round {self.round_num}] {self.agent_name}: {text}"

    def _post(self, verb: str, content_key="post_content", author_key="post_author_name") -> str:
        content, author = self.action_args.get(content_key, ""), self.action_args.get(author_key, "")
        if content and author:
            return f"{verb} {author}'s post: «{content}»"
        if content:
            return f"{verb} a post: «{content}»"
        if author:
            return f"{verb} a post by {author}"
        return f"{verb} a post"

    def _create_post(self):
        content = self.action_args.get("content", "")
        return f"posted: «{content}»" if content else "posted"

    def _like_post(self):
        return self._post("liked")

    def _dislike_post(self):
        return self._post("disliked")

    def _repost(self):
        return self._post("reposted", "original_content", "original_author_name")

    def _quote_post(self):
        base = self._post("quoted", "original_content", "original_author_name")
        quote = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        return f"{base}, adding: «{quote}»" if quote else base

    def _follow(self):
        target = self.action_args.get("target_user_name", "")
        return f"followed «{target}»" if target else "followed a user"

    def _create_comment(self):
        content = self.action_args.get("content", "")
        if not content:
            return "commented"
        return self._post("commented on", "post_content", "post_author_name") + f": «{content}»"

    def _like_comment(self):
        return self._post("liked a comment on", "comment_content", "comment_author_name")

    def _dislike_comment(self):
        return self._post("disliked a comment on", "comment_content", "comment_author_name")

    def _search(self):
        q = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"searched for «{q}»" if q else "searched"

    def _search_user(self):
        q = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"searched for the user «{q}»" if q else "searched for a user"

    def _mute(self):
        target = self.action_args.get("target_user_name", "")
        return f"muted «{target}»" if target else "muted a user"

    def _generic(self):
        return f"did {self.action_type}"


def episodes(activities: List[AgentActivity]) -> List[dict]:
    """MiroFish's _build_episode_payloads: pack activity lines into episodes of at most MAX_EPISODE_CHARS."""
    out, lines, people, length = [], [], [], 0
    for a in activities:
        text = a.to_episode_text()
        if len(text) > MAX_EPISODE_CHARS:
            marker = "... [truncated]"
            text = text[: MAX_EPISODE_CHARS - len(marker)] + marker
        if lines and length + 1 + len(text) > MAX_EPISODE_CHARS:
            out.append({"people": sorted(set(people)), "text": "\n".join(lines)})
            lines, people, length = [], [], 0
        lines.append(text)
        people.append(a.agent_name)
        length += (1 if len(lines) > 1 else 0) + len(text)
    if lines:
        out.append({"people": sorted(set(people)), "text": "\n".join(lines)})
    return out
