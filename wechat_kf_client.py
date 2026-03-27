"""
企业微信客服 API 客户端模块

封装企业微信客服相关 API 调用，包括获取 access_token、
拉取消息（sync_msg）、发送消息（send_msg）。
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class WeComKfClient:
    """企业微信客服 API 客户端。

    负责与企业微信服务器交互，管理 access_token 缓存，
    提供消息拉取和发送功能。
    """

    # 企业微信 API 基础地址
    BASE_URL = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(self, corp_id: str, kf_secret: str, open_kfid: str):
        """初始化客服 API 客户端。

        Args:
            corp_id: 企业 ID。
            kf_secret: 微信客服应用的 Secret。
            open_kfid: 客服账号 ID。
        """
        self.corp_id = corp_id
        self.kf_secret = kf_secret
        self.open_kfid = open_kfid
        self._access_token = None
        self._token_expires_at = 0

    def get_access_token(self) -> str:
        """获取 access_token，带缓存机制。

        access_token 有效期为 7200 秒，本方法会在过期前
        自动刷新。

        Returns:
            有效的 access_token 字符串。

        Raises:
            RuntimeError: 获取 access_token 失败时抛出。
        """
        # 提前 5 分钟刷新，避免临界过期
        if (
            self._access_token
            and time.time() < self._token_expires_at - 300
        ):
            return self._access_token

        url = f"{self.BASE_URL}/gettoken"
        params = {
            "corpid": self.corp_id,
            "corpsecret": self.kf_secret,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            if data.get("errcode", 0) != 0:
                error_msg = (
                    f"获取 access_token 失败: "
                    f"errcode={data.get('errcode')}, "
                    f"errmsg={data.get('errmsg')}"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get(
                "expires_in", 7200
            )
            logger.info("access_token 已刷新")
            return self._access_token

        except requests.RequestException as e:
            logger.error("请求企业微信 API 失败: %s", str(e))
            raise RuntimeError(f"请求企业微信 API 失败: {str(e)}") from e

    def sync_msg(
        self,
        cursor: str = "",
        token: str = "",
        open_kfid: str = "",
        limit: int = 1000,
    ) -> dict:
        """拉取客服消息。

        收到回调通知后调用此接口拉取具体消息内容。

        Args:
            cursor: 上一次拉取返回的 next_cursor，首次可不填。
            token: 回调事件返回的 token，10 分钟内有效。
            open_kfid: 客服账号 ID，不填则使用默认值。
            limit: 期望拉取的消息数量，最大 1000。

        Returns:
            API 返回的完整 JSON 数据，包含 msg_list 等字段。

        Raises:
            RuntimeError: API 调用失败时抛出。
        """
        access_token = self.get_access_token()
        url = f"{self.BASE_URL}/kf/sync_msg"
        params = {"access_token": access_token}

        body = {"limit": limit}
        if cursor:
            body["cursor"] = cursor
        if token:
            body["token"] = token
        if open_kfid:
            body["open_kfid"] = open_kfid
        else:
            body["open_kfid"] = self.open_kfid

        try:
            resp = requests.post(
                url, params=params, json=body, timeout=10
            )
            data = resp.json()

            if data.get("errcode", 0) != 0:
                error_msg = (
                    f"拉取消息失败: "
                    f"errcode={data.get('errcode')}, "
                    f"errmsg={data.get('errmsg')}"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            msg_count = len(data.get("msg_list", []))
            logger.info("成功拉取 %d 条消息", msg_count)
            return data

        except requests.RequestException as e:
            logger.error("拉取消息请求失败: %s", str(e))
            raise RuntimeError(f"拉取消息请求失败: {str(e)}") from e

    def send_text_msg(
        self, touser: str, content: str, open_kfid: str = ""
    ) -> dict:
        """向客户发送文本消息。

        客户主动发送消息后 48 小时内，最多可发送 5 条消息。

        Args:
            touser: 接收消息的客户 UserID（external_userid）。
            content: 文本消息内容。
            open_kfid: 客服账号 ID，不填则使用默认值。

        Returns:
            API 返回的完整 JSON 数据。

        Raises:
            RuntimeError: API 调用失败时抛出。
        """
        access_token = self.get_access_token()
        url = f"{self.BASE_URL}/kf/send_msg"
        params = {"access_token": access_token}

        body = {
            "touser": touser,
            "open_kfid": open_kfid or self.open_kfid,
            "msgtype": "text",
            "text": {"content": content},
        }

        try:
            resp = requests.post(
                url, params=params, json=body, timeout=10
            )
            data = resp.json()

            if data.get("errcode", 0) != 0:
                error_msg = (
                    f"发送消息失败: "
                    f"errcode={data.get('errcode')}, "
                    f"errmsg={data.get('errmsg')}"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info("消息已发送给用户: %s", touser)
            return data

        except requests.RequestException as e:
            logger.error("发送消息请求失败: %s", str(e))
            raise RuntimeError(f"发送消息请求失败: {str(e)}") from e
