"""
wechat_crypto 模块单元测试

验证消息加解密和签名功能的正确性。
"""

import unittest

from wechat_crypto import (
    PKCS7Encoder,
    Prpcrypt,
    WXBizMsgCrypt,
    WXBizMsgCryptError,
)


class TestPKCS7Encoder(unittest.TestCase):
    """PKCS7 填充/去填充测试。"""

    def test_encode_adds_padding(self):
        """测试编码后长度为 BLOCK_SIZE 的倍数。"""
        data = b"hello"
        result = PKCS7Encoder.encode(data)
        self.assertEqual(len(result) % 32, 0)

    def test_encode_decode_roundtrip(self):
        """测试编码后解码能还原。"""
        data = b"test message content"
        encoded = PKCS7Encoder.encode(data)
        decoded = PKCS7Encoder.decode(encoded)
        self.assertEqual(decoded, data)

    def test_encode_full_block(self):
        """测试恰好一个块大小的数据。"""
        data = b"a" * 32
        encoded = PKCS7Encoder.encode(data)
        # 应多出一个完整的填充块
        self.assertEqual(len(encoded), 64)


class TestPrpcrypt(unittest.TestCase):
    """AES 加解密测试。"""

    def setUp(self):
        """设置测试密钥（32 字节）。"""
        import base64

        # 使用一个有效的 43 字符 EncodingAESKey 生成 32 字节密钥
        self.encoding_aes_key = (
            "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
        )
        self.key = base64.b64decode(self.encoding_aes_key + "=")
        self.prpcrypt = Prpcrypt(self.key)
        self.corp_id = "test_corp_id"

    def test_encrypt_decrypt_roundtrip(self):
        """测试加密后解密能还原明文。"""
        plaintext = "Hello, World! 你好世界！"
        ret_enc, encrypted = self.prpcrypt.encrypt(
            plaintext, self.corp_id
        )
        self.assertEqual(ret_enc, WXBizMsgCryptError.OK)
        self.assertIsNotNone(encrypted)

        ret_dec, decrypted = self.prpcrypt.decrypt(
            encrypted, self.corp_id
        )
        self.assertEqual(ret_dec, WXBizMsgCryptError.OK)
        self.assertEqual(decrypted, plaintext)

    def test_decrypt_wrong_corpid(self):
        """测试使用错误 CorpID 解密应失败。"""
        plaintext = "secret message"
        _, encrypted = self.prpcrypt.encrypt(
            plaintext, self.corp_id
        )

        ret, _ = self.prpcrypt.decrypt(encrypted, "wrong_corp_id")
        self.assertEqual(
            ret, WXBizMsgCryptError.VALIDATE_CORPID_ERROR
        )


class TestWXBizMsgCrypt(unittest.TestCase):
    """WXBizMsgCrypt 综合测试。"""

    def setUp(self):
        """设置测试实例。"""
        self.token = "test_token_123"
        self.encoding_aes_key = (
            "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
        )
        self.corp_id = "test_corp_id"
        self.crypt = WXBizMsgCrypt(
            self.token, self.encoding_aes_key, self.corp_id
        )

    def test_encrypt_decrypt_msg_roundtrip(self):
        """测试消息加密后能正确解密。"""
        # 模拟明文 XML 消息
        plain_xml = (
            "<xml>"
            "<ToUserName><![CDATA[test]]></ToUserName>"
            "<Content><![CDATA[你好]]></Content>"
            "</xml>"
        )
        nonce = "test_nonce"
        timestamp = "1234567890"

        # 加密
        ret_enc, encrypted_xml = self.crypt.encrypt_msg(
            plain_xml, nonce, timestamp
        )
        self.assertEqual(ret_enc, WXBizMsgCryptError.OK)
        self.assertIn("<Encrypt>", encrypted_xml)
        self.assertIn("<MsgSignature>", encrypted_xml)

        # 从加密 XML 中提取签名
        import xml.etree.ElementTree as ET

        root = ET.fromstring(encrypted_xml)
        msg_signature = root.find("MsgSignature").text

        # 解密
        ret_dec, decrypted = self.crypt.decrypt_msg(
            encrypted_xml, msg_signature, timestamp, nonce
        )
        self.assertEqual(ret_dec, WXBizMsgCryptError.OK)
        self.assertEqual(decrypted, plain_xml)

    def test_invalid_encoding_aes_key(self):
        """测试无效的 EncodingAESKey 应抛出异常。"""
        with self.assertRaises(ValueError):
            WXBizMsgCrypt(
                self.token, "short_key", self.corp_id
            )

    def test_signature_verification_failure(self):
        """测试签名验证失败。"""
        ret, _ = self.crypt.verify_url(
            msg_signature="wrong_signature",
            timestamp="123",
            nonce="456",
            echostr="dummy",
        )
        self.assertEqual(
            ret, WXBizMsgCryptError.VALIDATE_SIGNATURE_ERROR
        )


if __name__ == "__main__":
    unittest.main()
