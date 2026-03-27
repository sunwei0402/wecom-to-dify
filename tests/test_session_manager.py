"""
session_manager 模块单元测试

验证会话管理逻辑，包括创建、更新、超时和清理。
"""

import time
import unittest

from session_manager import SessionManager


class TestSessionManager(unittest.TestCase):
    """会话管理器测试。"""

    def test_new_user_returns_empty(self):
        """新用户应返回空对话 ID。"""
        mgr = SessionManager(timeout=3600)
        result = mgr.get_conversation_id("user_001")
        self.assertEqual(result, "")

    def test_update_and_get(self):
        """更新会话后应能获取对话 ID。"""
        mgr = SessionManager(timeout=3600)
        mgr.update_session("user_001", "conv_abc123")
        result = mgr.get_conversation_id("user_001")
        self.assertEqual(result, "conv_abc123")

    def test_session_timeout(self):
        """超时后应返回空对话 ID。"""
        # 使用 1 秒超时以便快速测试
        mgr = SessionManager(timeout=1)
        mgr.update_session("user_001", "conv_abc123")

        # 等待超时
        time.sleep(1.1)

        result = mgr.get_conversation_id("user_001")
        self.assertEqual(result, "")

    def test_clear_session(self):
        """清除会话后应返回空对话 ID。"""
        mgr = SessionManager(timeout=3600)
        mgr.update_session("user_001", "conv_abc123")
        mgr.clear_session("user_001")
        result = mgr.get_conversation_id("user_001")
        self.assertEqual(result, "")

    def test_clear_nonexistent_session(self):
        """清除不存在的会话不应报错。"""
        mgr = SessionManager(timeout=3600)
        mgr.clear_session("nonexistent_user")

    def test_active_count(self):
        """活跃会话计数应正确。"""
        mgr = SessionManager(timeout=3600)
        self.assertEqual(mgr.active_count, 0)

        mgr.update_session("user_001", "conv_1")
        mgr.update_session("user_002", "conv_2")
        self.assertEqual(mgr.active_count, 2)

        mgr.clear_session("user_001")
        self.assertEqual(mgr.active_count, 1)

    def test_cleanup_expired(self):
        """清理过期会话应正确移除。"""
        mgr = SessionManager(timeout=1)
        mgr.update_session("user_old", "conv_old")

        time.sleep(1.1)

        # 添加新会话
        mgr.update_session("user_new", "conv_new")

        cleaned = mgr.cleanup_expired()
        self.assertEqual(cleaned, 1)
        self.assertEqual(mgr.active_count, 1)
        self.assertEqual(
            mgr.get_conversation_id("user_new"), "conv_new"
        )

    def test_update_existing_session(self):
        """更新已存在的会话应覆盖旧值。"""
        mgr = SessionManager(timeout=3600)
        mgr.update_session("user_001", "conv_old")
        mgr.update_session("user_001", "conv_new")
        result = mgr.get_conversation_id("user_001")
        self.assertEqual(result, "conv_new")

    def test_multiple_users_independent(self):
        """不同用户的会话应互相独立。"""
        mgr = SessionManager(timeout=3600)
        mgr.update_session("user_001", "conv_1")
        mgr.update_session("user_002", "conv_2")

        self.assertEqual(
            mgr.get_conversation_id("user_001"), "conv_1"
        )
        self.assertEqual(
            mgr.get_conversation_id("user_002"), "conv_2"
        )


if __name__ == "__main__":
    unittest.main()
