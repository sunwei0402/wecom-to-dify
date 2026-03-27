"""
会话管理模块

管理微信用户与 Dify 对话 ID 的映射关系，
支持会话超时自动清理。
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class SessionManager:
    """用户会话管理器。

    维护 external_userid → Dify conversation_id 的映射。
    基于内存字典实现，支持会话超时自动清理。

    Attributes:
        timeout: 会话超时时间（秒）。
    """

    def __init__(self, timeout: int = 3600):
        """初始化会话管理器。

        Args:
            timeout: 会话超时时间（秒），默认 1 小时。
                    超时后用户的下一条消息将开启新的 Dify 对话。
        """
        self.timeout = timeout
        self._sessions = {}
        self._lock = threading.Lock()

    def get_conversation_id(self, user_id: str) -> str:
        """获取用户对应的 Dify 对话 ID。

        如果会话已超时或不存在，返回空字符串。

        Args:
            user_id: 微信用户的 external_userid。

        Returns:
            Dify 对话 ID，如果不存在或已超时则返回空字符串。
        """
        with self._lock:
            session = self._sessions.get(user_id)
            if session is None:
                return ""

            # 检查是否超时
            if time.time() - session["last_active"] > self.timeout:
                logger.info(
                    "用户 %s 的会话已超时，将开始新对话", user_id
                )
                del self._sessions[user_id]
                return ""

            return session.get("conversation_id", "")

    def update_session(
        self, user_id: str, conversation_id: str
    ) -> None:
        """更新用户的会话信息。

        Args:
            user_id: 微信用户的 external_userid。
            conversation_id: Dify 返回的对话 ID。
        """
        with self._lock:
            self._sessions[user_id] = {
                "conversation_id": conversation_id,
                "last_active": time.time(),
            }
            logger.debug(
                "用户 %s 的会话已更新: conversation_id=%s",
                user_id,
                conversation_id,
            )

    def clear_session(self, user_id: str) -> None:
        """清除指定用户的会话。

        Args:
            user_id: 微信用户的 external_userid。
        """
        with self._lock:
            if user_id in self._sessions:
                del self._sessions[user_id]
                logger.info("用户 %s 的会话已清除", user_id)

    def cleanup_expired(self) -> int:
        """清理所有过期的会话。

        Returns:
            被清理的会话数量。
        """
        now = time.time()
        cleaned = 0

        with self._lock:
            expired_users = [
                uid
                for uid, session in self._sessions.items()
                if now - session["last_active"] > self.timeout
            ]
            for uid in expired_users:
                del self._sessions[uid]
                cleaned += 1

        if cleaned > 0:
            logger.info("已清理 %d 个过期会话", cleaned)

        return cleaned

    @property
    def active_count(self) -> int:
        """当前活跃会话数量。"""
        with self._lock:
            return len(self._sessions)
