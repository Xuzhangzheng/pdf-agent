# 火山方舟 ARK 配置

Chat（生成 / reflect / revise / rewrite_query / llm_judge）使用 OpenAI 兼容 API。

## 环境变量

```bash
ARK_API_KEY=your_key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_CHAT_MODEL=doubao-1-5-lite-32k-250115
ARK_TEMPERATURE=0.1
# 部分模型不支持 response_format=json_object（如 doubao-seed-2-0-lite）；不设也会自动回退
# ARK_CHAT_JSON_MODE=false
```

## 模型与 JSON 模式

反思、假设问句生成等会通过 `ArkClient` 请求 `response_format: json_object`。若控制台模型**不支持**该参数（报错 `json_object is not supported`）：

1. **推荐**：保持默认，SDK 会自动去掉 `response_format` 再请求，并从文本解析 JSON（`src/llm/ark_client.py`）。
2. 或显式设置 `ARK_CHAT_JSON_MODE=false`，始终不用 JSON mode。

换用 `doubao-seed-*` 等模型时，只需保证 `.env` 中 `ARK_CHAT_MODEL` 与方舟控制台 **推理接入点 ID** 一致；**不影响** MinerU PDF 解析（解析不走 ARK Chat）。

## API Key 与 IP

若报错 `IP access denied by API-Key restriction`，在火山方舟控制台为该 Key 添加当前公网 IP 或关闭 IP 白名单。Chat（`ARK_API_KEY`）与 Embedding（`DASHSCOPE_API_KEY`）可能是不同 Key，需分别检查。

## 调用示例

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["ARK_API_KEY"],
    base_url=os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
)
resp = client.chat.completions.create(
    model=os.environ.get("ARK_CHAT_MODEL", "doubao-1-5-lite-32k-250115"),
    messages=[{"role": "user", "content": "hello"}],
    temperature=0.1,
)
print(resp.choices[0].message.content)
```

Embedding 与 Rerank 使用 DashScope，见 [EMBEDDING.md](./EMBEDDING.md) 与 [rerank-spec.md](./rerank-spec.md)。
