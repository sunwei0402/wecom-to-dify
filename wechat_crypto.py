"""
企业微信消息加解密模块

实现企业微信回调消息的签名验证、AES 加解密功能。
兼容 Python 3，基于企业微信官方加解密方案实现。
"""

import base64
import hashlib
import socket
import struct
import time
import xml.etree.ElementTree as ET

from Crypto.Cipher import AES


class WXBizMsgCryptError:
    """企业微信加解密错误码定义。"""

    OK = 0
    VALIDATE_SIGNATURE_ERROR = -40001
    PARSE_XML_ERROR = -40002
    COMPUTE_SIGNATURE_ERROR = -40003
    ILLEGAL_AES_KEY = -40004
    VALIDATE_CORPID_ERROR = -40005
    ENCRYPT_AES_ERROR = -40006
    DECRYPT_AES_ERROR = -40007
    ILLEGAL_BUFFER = -40008
    ENCODE_BASE64_ERROR = -40009
    DECODE_BASE64_ERROR = -40010
    GEN_RETURN_XML_ERROR = -40011


class PKCS7Encoder:
    """PKCS7 填充/去填充工具类。"""

    BLOCK_SIZE = 32

    @staticmethod
    def encode(text: bytes) -> bytes:
        """对明文进行 PKCS7 填充。

        Args:
            text: 需要填充的明文字节串。

        Returns:
            填充后的字节串。
        """
        amount = PKCS7Encoder.BLOCK_SIZE - (
            len(text) % PKCS7Encoder.BLOCK_SIZE
        )
        pad = bytes([amount]) * amount
        return text + pad

    @staticmethod
    def decode(decrypted: bytes) -> bytes:
        """去除 PKCS7 填充。

        Args:
            decrypted: 解密后带填充的字节串。

        Returns:
            去除填充后的明文字节串。
        """
        pad = decrypted[-1]
        if pad < 1 or pad > PKCS7Encoder.BLOCK_SIZE:
            pad = 0
        return decrypted[:-pad]


class Prpcrypt:
    """AES 加解密工具类，使用 CBC 模式。"""

    def __init__(self, key: bytes):
        """初始化加解密工具。

        Args:
            key: AES 密钥（32 字节）。
        """
        self.key = key
        self.mode = AES.MODE_CBC

    def encrypt(self, text: str, corpid: str) -> tuple:
        """对明文进行 AES 加密。

        按照企业微信格式：随机16字节 + 消息长度(4字节) + 明文 + CorpID

        Args:
            text: 待加密的明文字符串。
            corpid: 企业 ID。

        Returns:
            (错误码, Base64 编码的密文)。
        """
        try:
            # 16 字节随机字符串
            random_str = self._get_random_str()
            text_bytes = text.encode("utf-8")
            corpid_bytes = corpid.encode("utf-8")

            # 拼接：随机字符串 + 消息长度 + 消息 + CorpID
            content = (
                random_str
                + struct.pack("!I", len(text_bytes))
                + text_bytes
                + corpid_bytes
            )
            content = PKCS7Encoder.encode(content)

            cipher = AES.new(self.key, self.mode, self.key[:16])
            encrypted = cipher.encrypt(content)

            return (
                WXBizMsgCryptError.OK,
                base64.b64encode(encrypted).decode("utf-8"),
            )
        except Exception:
            return (WXBizMsgCryptError.ENCRYPT_AES_ERROR, None)

    def decrypt(self, encrypted: str, corpid: str) -> tuple:
        """对密文进行 AES 解密。

        Args:
            encrypted: Base64 编码的密文。
            corpid: 企业 ID，用于验证解密结果。

        Returns:
            (错误码, 解密后的明文字符串)。
        """
        try:
            cipher = AES.new(self.key, self.mode, self.key[:16])
            decrypted = cipher.decrypt(base64.b64decode(encrypted))
            decrypted = PKCS7Encoder.decode(decrypted)

            # 去除16字节随机字符串，读取4字节消息长度
            msg_len = struct.unpack("!I", decrypted[16:20])[0]
            content = decrypted[20: 20 + msg_len].decode("utf-8")
            from_corpid = decrypted[20 + msg_len:].decode("utf-8")

            if from_corpid != corpid:
                return (WXBizMsgCryptError.VALIDATE_CORPID_ERROR, None)

            return (WXBizMsgCryptError.OK, content)
        except Exception:
            return (WXBizMsgCryptError.DECRYPT_AES_ERROR, None)

    @staticmethod
    def _get_random_str() -> bytes:
        """生成 16 字节随机字符串。"""
        import random
        import string

        chars = string.ascii_letters + string.digits
        return "".join(random.choice(chars) for _ in range(16)).encode(
            "utf-8"
        )


class WXBizMsgCrypt:
    """企业微信消息加解密类。

    提供 URL 验证、消息解密、消息加密三个核心方法。
    """

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        """初始化加解密实例。

        Args:
            token: 回调配置的 Token。
            encoding_aes_key: 回调配置的 EncodingAESKey（43 字符）。
            corp_id: 企业 ID。
        """
        self.token = token
        self.corp_id = corp_id

        try:
            self.key = base64.b64decode(encoding_aes_key + "=")
            assert len(self.key) == 32
        except Exception:
            raise ValueError(
                f"EncodingAESKey 无效，长度应为 43 个字符，"
                f"当前: {len(encoding_aes_key)}"
            )

        self.prpcrypt = Prpcrypt(self.key)

    def verify_url(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        echostr: str,
    ) -> tuple:
        """验证回调 URL 有效性。

        企业微信在配置回调 URL 时会发送 GET 请求进行验证。

        Args:
            msg_signature: 签名串。
            timestamp: 时间戳。
            nonce: 随机数。
            echostr: 加密的随机字符串。

        Returns:
            (错误码, 解密后的 echostr)。
        """
        signature = self._compute_signature(
            self.token, timestamp, nonce, echostr
        )
        if signature != msg_signature:
            return (WXBizMsgCryptError.VALIDATE_SIGNATURE_ERROR, None)

        ret, reply_echostr = self.prpcrypt.decrypt(echostr, self.corp_id)
        return (ret, reply_echostr)

    def decrypt_msg(
        self,
        post_data: str,
        msg_signature: str,
        timestamp: str,
        nonce: str,
    ) -> tuple:
        """解密企业微信推送的回调消息。

        Args:
            post_data: POST 请求体（XML 格式）。
            msg_signature: 签名串。
            timestamp: 时间戳。
            nonce: 随机数。

        Returns:
            (错误码, 解密后的 XML 明文)。
        """
        try:
            xml_tree = ET.fromstring(post_data)
            encrypt = xml_tree.find("Encrypt").text
        except Exception:
            return (WXBizMsgCryptError.PARSE_XML_ERROR, None)

        signature = self._compute_signature(
            self.token, timestamp, nonce, encrypt
        )
        if signature != msg_signature:
            return (WXBizMsgCryptError.VALIDATE_SIGNATURE_ERROR, None)

        ret, xml_content = self.prpcrypt.decrypt(encrypt, self.corp_id)
        return (ret, xml_content)

    def encrypt_msg(
        self, reply_msg: str, nonce: str, timestamp: str = None
    ) -> tuple:
        """加密回复消息。

        Args:
            reply_msg: 回复的明文消息。
            nonce: 随机数。
            timestamp: 时间戳，默认使用当前时间。

        Returns:
            (错误码, 加密后的 XML 字符串)。
        """
        if timestamp is None:
            timestamp = str(int(time.time()))

        ret, encrypt = self.prpcrypt.encrypt(reply_msg, self.corp_id)
        if ret != WXBizMsgCryptError.OK:
            return (ret, None)

        signature = self._compute_signature(
            self.token, timestamp, nonce, encrypt
        )

        resp_xml = (
            "<xml>"
            f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
            f"<TimeStamp>{timestamp}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            "</xml>"
        )
        return (WXBizMsgCryptError.OK, resp_xml)

    @staticmethod
    def _compute_signature(token: str, timestamp: str, nonce: str,
                           encrypt: str) -> str:
        """计算消息签名。

        Args:
            token: 回调 Token。
            timestamp: 时间戳。
            nonce: 随机数。
            encrypt: 加密内容。

        Returns:
            SHA1 签名字符串。
        """
        sort_list = sorted([token, timestamp, nonce, encrypt])
        sha1 = hashlib.sha1("".join(sort_list).encode("utf-8"))
        return sha1.hexdigest()
