# 火山方舟 ARK 配置

Chat（生成 / reflect / revise / rewrite_query / llm_judge）使用 OpenAI 兼容 API。

## 环境变量

```bash
ARK_API_KEY=your_key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_CHAT_MODEL=doubao-1-5-lite-32k-250115
ARK_TEMPERATURE=0.1
```

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
