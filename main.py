"""
企业微信客服 → Dify AI 中间件

主入口文件。加载配置，启动 Webhook 服务器，
将企业微信客服消息转发到 Dify 应用实现 AI 自动回复。
"""

import logging
import os
import sys

import yaml

from webhook_server import create_app


def _setup_logging() -> None:
    """配置日志格式和级别。"""
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s [%(levelname)s] "
            "%(name)s - %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def _load_config(config_path: str) -> dict:
    """加载 YAML 配置文件。

    Args:
        config_path: 配置文件路径。

    Returns:
        配置字典。

    Raises:
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: 配置文件格式错误。
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            f"请复制 config.yaml.example 为 config.yaml 并填入实际值"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 验证必要配置项
    required_keys = [
        ("wecom", "corp_id"),
        ("wecom", "kf_secret"),
        ("wecom", "open_kfid"),
        ("callback", "token"),
        ("callback", "encoding_aes_key"),
        ("dify", "api_base_url"),
        ("dify", "api_key"),
    ]

    for section, key in required_keys:
        value = config.get(section, {}).get(key, "")
        if not value or value.startswith("your_"):
            raise ValueError(
                f"配置项 {section}.{key} 未设置，"
                f"请在 config.yaml 中填入实际值"
            )

    return config


def example_start_server() -> None:
    """启动企业微信客服 → Dify 中间件服务。

    加载配置并启动 Flask Webhook 服务器，
    开始监听企业微信客服的回调消息。
    """
    _setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 50)
    logger.info("企业微信客服 → Dify AI 中间件")
    logger.info("=" * 50)

    # 加载配置
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    try:
        config = _load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error("配置错误: %s", str(e))
        sys.exit(1)

    logger.info("配置加载成功")
    logger.info(
        "企业 ID: %s", config["wecom"]["corp_id"][:6] + "***"
    )
    logger.info("客服账号: %s", config["wecom"]["open_kfid"])
    logger.info("Dify API: %s", config["dify"]["api_base_url"])

    # 创建 Flask 应用
    app = create_app(config)

    # 获取服务器配置
    server_config = config.get("server", {})
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8080)
    debug = server_config.get("debug", False)

    logger.info("服务器启动: http://%s:%d", host, port)
    logger.info("回调地址: http://<your-domain>:%d/callback", port)
    logger.info("健康检查: http://%s:%d/health", host, port)

    # 启动服务器
    app.run(host=host, port=port, debug=debug)


def main():
    """主入口函数。"""
    example_start_server()


if __name__ == "__main__":
    main()
