"""
Dify API 客户端模块

封装 Dify Chat Messages API 调用，支持 blocking 模式对话。
"""

import logging

import requests

logger = logging.getLogger(__name__)


class DifyClient:
    """Dify Chat Messages API 客户端。

    负责将用户消息转发到 Dify 应用并获取 AI 回复。
    使用 blocking 模式，等待完整回复后返回。
    """

    def __init__(self, api_base_url: str, api_key: str):
        """初始化 Dify 客户端。

        Args:
            api_base_url: Dify API 基础地址
                          （如 https://api.dify.ai/v1）。
            api_key: Dify 应用的 API Key
                     （如 app-xxxxxxxx）。
        """
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key

    def chat(
        self,
        query: str,
        user: str,
        conversation_id: str = "",
        inputs: dict = None,
    ) -> dict:
        """发送对话消息到 Dify 并获取 AI 回复。

        Args:
            query: 用户的问题或消息内容。
            user: 用户唯一标识符。
            conversation_id: 对话 ID，用于延续之前的对话。
                           首次对话留空，后续使用返回的 ID。
            inputs: 可选的输入变量字典。

        Returns:
            包含以下键的字典：
            - answer: AI 的回复文本。
            - conversation_id: 对话 ID（用于后续对话）。
            - message_id: 消息 ID。

        Raises:
            RuntimeError: API 调用失败时抛出。
        """
        url = f"{self.api_base_url}/chat-messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "blocking",
            "user": user,
        }

        # 仅在有对话 ID 时传入，避免传空字符串
        if conversation_id:
            body["conversation_id"] = conversation_id

        try:
            logger.info(
                "向 Dify 发送消息: user=%s, query=%s",
                user,
                query[:50],
            )
            resp = requests.post(
                url, headers=headers, json=body, timeout=120
            )

            if resp.status_code != 200:
                error_msg = (
                    f"Dify API 调用失败: "
                    f"status={resp.status_code}, "
                    f"body={resp.text[:200]}"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            data = resp.json()
            answer = data.get("answer", "")
            conv_id = data.get("conversation_id", "")
            msg_id = data.get("message_id", "")

            logger.info(
                "Dify 回复: conversation_id=%s, answer=%s",
                conv_id,
                answer[:50],
            )

            return {
                "answer": answer,
                "conversation_id": conv_id,
                "message_id": msg_id,
            }

        except requests.RequestException as e:
            logger.error("请求 Dify API 失败: %s", str(e))
            raise RuntimeError(f"请求 Dify API 失败: {str(e)}") from e
