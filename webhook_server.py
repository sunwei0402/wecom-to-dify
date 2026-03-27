"""
Webhook 服务器模块

基于 Flask 实现的 HTTP 服务器，接收企业微信客服回调，
处理消息并通过 Dify AI 生成回复。
"""

import logging
import threading
import xml.etree.ElementTree as ET

from flask import Flask, request

from dify_client import DifyClient
from session_manager import SessionManager
from wechat_crypto import WXBizMsgCrypt
from wechat_kf_client import WeComKfClient

logger = logging.getLogger(__name__)

# 用于消息去重的全局缓存
processed_msgids = set()
processed_msgids_list = []
msgids_lock = threading.Lock()

def _is_msg_processed(msgid: str) -> bool:
    if not msgid:
        return False
    with msgids_lock:
        if msgid in processed_msgids:
            return True
        processed_msgids.add(msgid)
        processed_msgids_list.append(msgid)
        if len(processed_msgids_list) > 1000:
            oldest = processed_msgids_list.pop(0)
            processed_msgids.discard(oldest)
        return False


def create_app(config: dict) -> Flask:
    """创建并配置 Flask 应用。

    Args:
        config: 应用配置字典，包含 wecom、callback、dify、
               session 等配置项。

    Returns:
        配置完成的 Flask 应用实例。
    """
    app = Flask(__name__)

    # ---- 初始化各模块 ----

    # 企业微信消息加解密
    crypto = WXBizMsgCrypt(
        token=config["callback"]["token"],
        encoding_aes_key=config["callback"]["encoding_aes_key"],
        corp_id=config["wecom"]["corp_id"],
    )

    # 企业微信客服 API 客户端
    kf_client = WeComKfClient(
        corp_id=config["wecom"]["corp_id"],
        kf_secret=config["wecom"]["kf_secret"],
        open_kfid=config["wecom"]["open_kfid"],
    )

    # Dify API 客户端
    dify_client = DifyClient(
        api_base_url=config["dify"]["api_base_url"],
        api_key=config["dify"]["api_key"],
    )

    # 会话管理器
    session_timeout = config.get("session", {}).get("timeout", 3600)
    session_mgr = SessionManager(timeout=session_timeout)

    # ---- 路由定义 ----

    @app.route("/callback", methods=["GET"])
    def verify_callback():
        """处理企业微信回调 URL 验证（GET 请求）。

        企业微信在配置回调 URL 时会发送 GET 请求，
        需要解密 echostr 并原样返回明文。
        """
        msg_signature = request.args.get("msg_signature", "")
        timestamp = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")
        echostr = request.args.get("echostr", "")

        logger.info("收到 URL 验证请求")

        ret, reply_echostr = crypto.verify_url(
            msg_signature, timestamp, nonce, echostr
        )

        if ret != 0:
            logger.error("URL 验证失败, 错误码: %d", ret)
            return "验证失败", 403

        logger.info("URL 验证成功")
        return reply_echostr

    @app.route("/callback", methods=["POST"])
    def handle_callback():
        """处理企业微信回调消息推送（POST 请求）。

        收到回调后：
        1. 解密回调消息，获取事件信息
        2. 调用 sync_msg 拉取具体消息
        3. 将用户文本消息转发给 Dify
        4. 将 Dify 回复通过 send_msg 发送给用户
        """
        msg_signature = request.args.get("msg_signature", "")
        timestamp = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")
        post_data = request.data.decode("utf-8")

        logger.info("收到回调消息推送")

        # 1. 解密回调消息
        ret, decrypted_xml = crypto.decrypt_msg(
            post_data, msg_signature, timestamp, nonce
        )

        if ret != 0:
            logger.error("回调消息解密失败, 错误码: %d", ret)
            return "解密失败", 403

        # 2. 解析回调 XML，提取事件信息
        callback_token, open_kfid = _parse_callback_xml(
            decrypted_xml
        )

        if not callback_token:
            logger.warning("回调消息中未找到 Token 字段")
            return "success"

        # 3. 异步拉取消息并处理，避免超时导致企业微信重试
        def async_process():
            try:
                sync_result = kf_client.sync_msg(
                    token=callback_token, open_kfid=open_kfid
                )
                msg_list = sync_result.get("msg_list", [])
                for msg in msg_list:
                    _process_message(
                        msg, kf_client, dify_client, session_mgr
                    )
            except RuntimeError as e:
                logger.error("拉取消息失败: %s", str(e))
            except Exception as e:
                logger.error("后台处理消息异常: %s", str(e))

        threading.Thread(target=async_process, daemon=True).start()

        return "success"

    @app.route("/health", methods=["GET"])
    def health_check():
        """健康检查端点。"""
        return {
            "status": "ok",
            "active_sessions": session_mgr.active_count,
        }

    return app


def _parse_callback_xml(xml_content: str) -> tuple:
    """解析回调 XML 消息，提取 Token 和 OpenKfId。

    Args:
        xml_content: 解密后的 XML 字符串。

    Returns:
        (token, open_kfid) 元组。解析失败时返回 ("", "")。
    """
    try:
        root = ET.fromstring(xml_content)
        token = root.find("Token")
        open_kfid = root.find("OpenKfId")

        token_text = token.text if token is not None else ""
        kfid_text = open_kfid.text if open_kfid is not None else ""

        logger.debug(
            "回调解析: Token=%s, OpenKfId=%s",
            token_text[:10] + "..." if token_text else "",
            kfid_text,
        )
        return (token_text, kfid_text)
    except ET.ParseError as e:
        logger.error("解析回调 XML 失败: %s", str(e))
        return ("", "")


def _process_message(
    msg: dict,
    kf_client: WeComKfClient,
    dify_client: DifyClient,
    session_mgr: SessionManager,
) -> None:
    """处理单条消息。

    仅处理来自客户的文本消息，忽略其他类型。

    Args:
        msg: 消息字典，包含 msgtype、origin、external_userid 等。
        kf_client: 企业微信客服 API 客户端。
        dify_client: Dify API 客户端。
        session_mgr: 会话管理器。
    """
    # 仅处理来源为客户的消息（origin=3 表示客户发送）
    origin = msg.get("origin", 0)
    if origin != 3:
        logger.debug("跳过非客户消息, origin=%d", origin)
        return

    msgtype = msg.get("msgtype", "")
    external_userid = msg.get("external_userid", "")
    open_kfid = msg.get("open_kfid", "")
    msgid = msg.get("msgid", "")

    if not external_userid:
        logger.warning("消息中缺少 external_userid")
        return

    # 检查是否已处理过
    if _is_msg_processed(msgid):
        logger.debug("消息 %s 已处理过，跳过", msgid)
        return

    # 目前仅支持文本消息
    if msgtype == "text":
        text_content = msg.get("text", {}).get("content", "")
        if not text_content:
            return

        logger.info(
            "收到用户 %s 的文本消息: %s",
            external_userid,
            text_content[:50],
        )

        # 获取用户的 Dify 对话 ID
        conversation_id = session_mgr.get_conversation_id(
            external_userid
        )

        # 转发到 Dify
        try:
            dify_result = dify_client.chat(
                query=text_content,
                user=external_userid,
                conversation_id=conversation_id,
            )

            # 更新会话映射
            new_conv_id = dify_result.get("conversation_id", "")
            if new_conv_id:
                session_mgr.update_session(
                    external_userid, new_conv_id
                )

            # 发送 AI 回复给用户
            answer = dify_result.get("answer", "")
            if answer:
                kf_client.send_text_msg(
                    touser=external_userid,
                    content=answer,
                    open_kfid=open_kfid,
                )
            else:
                logger.warning("Dify 返回了空回复")

        except RuntimeError as e:
            logger.error(
                "处理消息失败 (user=%s): %s",
                external_userid,
                str(e),
            )
            # 向用户发送错误提示
            try:
                kf_client.send_text_msg(
                    touser=external_userid,
                    content="抱歉，AI 助手暂时无法回复，请稍后再试。",
                    open_kfid=open_kfid,
                )
            except RuntimeError:
                logger.error("发送错误提示消息也失败了")

    elif msgtype == "image":
        logger.info("收到图片消息，暂不支持处理")
        try:
            kf_client.send_text_msg(
                touser=external_userid,
                content="暂时只支持文字消息哦，请发送文字内容~",
                open_kfid=open_kfid,
            )
        except RuntimeError:
            pass

    elif msgtype == "event":
        event_type = msg.get("event", {}).get("event_type", "")
        logger.info(
            "收到事件消息: type=%s, user=%s",
            event_type,
            external_userid,
        )
    else:
        logger.info("收到不支持的消息类型: %s", msgtype)
