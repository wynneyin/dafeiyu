import traceback

import anthropic

from utils.history import total_chars as history_chars
from utils.my_log import logger


class Claude:
    """Anthropic Claude（Messages API）。

    api_key / auth_token / base_url 留空时由 SDK 自己读环境变量：
    ANTHROPIC_API_KEY、ANTHROPIC_AUTH_TOKEN、ANTHROPIC_BASE_URL。
    这样 Key 不用写进 config.json，和 Claude Code 共用同一套配置。
    api_key 走 x-api-key 头，auth_token 走 Authorization: Bearer 头，中转站认哪个填哪个。
    """

    def __init__(self, data):
        self.config_data = data
        self.history = []

        client_kwargs = {"timeout": float(data.get("timeout") or 60)}
        if data.get("api_key"):
            client_kwargs["api_key"] = data["api_key"]
        if data.get("auth_token"):
            client_kwargs["auth_token"] = data["auth_token"]
        if data.get("base_url"):
            client_kwargs["base_url"] = data["base_url"]
        self.client = anthropic.Anthropic(**client_kwargs)

    def create_message(self, messages):
        request = {
            "model": self.config_data["model"],
            "max_tokens": int(self.config_data.get("max_tokens") or 16000),
            "system": self.config_data["preset"],
            "messages": messages,
        }
        # 直播聊天不需要深度推理，effort 调低换响应速度；Opus 5.5 不能关 thinking，只能靠它控制
        if self.config_data.get("effort"):
            request["output_config"] = {"effort": self.config_data["effort"]}

        # 安全分类器拒答时由服务端自动换模型重答，中转站不支持时在配置里关掉
        if self.config_data.get("fallback_enable"):
            return self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **request,
            )
        return self.client.messages.create(**request)

    def get_resp(self, prompt):
        """请求对应接口，获取返回值

        Args:
            prompt (str): 你的提问

        Returns:
            str: 返回的文本回答
        """
        try:
            # 历史只存纯文本问答，不存 thinking 块，从头部丢弃旧轮次不会让后续请求失效
            messages = list(self.history) + [{"role": "user", "content": prompt}]

            response = self.create_message(messages)

            if response.stop_reason == "refusal":
                category = response.stop_details.category if response.stop_details else None
                logger.warning(f"Claude 拒绝回答，category={category}")
                return None

            resp_content = "".join(block.text for block in response.content if block.type == "text").strip()
            if not resp_content:
                logger.warning(f"Claude 返回内容为空，stop_reason={response.stop_reason}")
                return None

            # 启用历史就给我记住！
            if self.config_data["history_enable"]:
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": resp_content})
                # 超长就成对丢弃最早的问答
                while len(self.history) > 2 and history_chars(self.history) > int(self.config_data["history_max_len"]):
                    self.history.pop(0)
                    self.history.pop(0)

            return resp_content
        except anthropic.APIStatusError as e:
            logger.error(f"Claude 接口报错 status={e.status_code}：{e.message}")
            return None
        except anthropic.APIConnectionError as e:
            logger.error(f"Claude 连接失败，请检查 base_url / 网络：{e}")
            return None
        except Exception:
            logger.error(traceback.format_exc())
            return None
