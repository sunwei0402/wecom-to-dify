# 企业微信客服 → Dify AI 中间件

将企业微信客服接入 Dify AI 应用，实现客户消息的 AI 自动回复。

## 架构

```
微信用户 → 企业微信服务器 → 本中间件(Webhook) → Dify API → AI 回复 → 企业微信客服 → 用户
```

### 消息处理流程

1. 企业微信服务器向中间件发送回调通知（POST `/callback`）
2. 中间件解密回调消息，调用 `kf/sync_msg` 拉取具体消息内容
3. 提取用户文本消息，连同对话上下文转发到 Dify Chat API
4. 将 Dify 返回的 AI 回复通过 `kf/send_msg` 发送给用户

## 项目结构

```
webcomdify/
├── main.py               # 主入口
├── webhook_server.py     # Flask Webhook 服务器
├── wechat_crypto.py      # 消息加解密
├── wechat_kf_client.py   # 企业微信客服 API 客户端
├── dify_client.py        # Dify API 客户端
├── session_manager.py    # 会话管理（用户 ↔ Dify 对话）
├── config.yaml.example   # 配置模板
├── requirements.txt      # Python 依赖
└── tests/                # 单元测试
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

复制配置模板并填入实际值：

```bash
cp config.yaml.example config.yaml
```

需要配置的关键信息：

| 配置项 | 说明 | 获取位置 |
|--------|------|----------|
| `wecom.corp_id` | 企业 ID | 企业微信管理后台 → 我的企业 |
| `wecom.kf_secret` | 客服应用 Secret | 应用管理 → 微信客服 |
| `wecom.open_kfid` | 客服账号 ID | 微信客服 → 账号管理 |
| `callback.token` | 回调 Token | 微信客服 → API 设置 |
| `callback.encoding_aes_key` | 回调加密密钥 | 微信客服 → API 设置 |
| `dify.api_base_url` | Dify API 地址 | Dify 控制台 |
| `dify.api_key` | Dify 应用 API Key | Dify 应用 → API 访问 |

### 3. 启动服务

```bash
python main.py
```

服务默认监听 `0.0.0.0:8080`。

### 4. 配置企业微信回调

在企业微信管理后台 → 微信客服 → API：

1. 将回调 URL 设置为 `http://<your-domain>:8080/callback`
2. 填入与 `config.yaml` 一致的 Token 和 EncodingAESKey
3. 点击保存完成验证

### 5. 验证

- 健康检查：`GET http://localhost:8080/health`
- 通过微信客服向客服账号发送消息，应收到 AI 回复

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CONFIG_PATH` | 配置文件路径 | `config.yaml` |

## 注意事项

- 企业微信客服发送消息有 **48 小时 / 5 条** 限制
- 回调 token（sync_msg 参数）**10 分钟**内有效
- 会话默认 **1 小时**超时，可在配置中调整
- 生产环境建议使用 Gunicorn 等 WSGI 服务器替代 Flask 内置服务器
