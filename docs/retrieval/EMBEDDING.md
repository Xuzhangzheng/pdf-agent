# Embedding 配置（DashScope text-embedding-v4）

本项目检索向量化**定稿**为阿里云百炼 **text-embedding-v4**（在线 API）。生成与 Self-Reflection 仍使用火山方舟 ARK。

## 环境变量

项目根目录已提供 `**.env`**（自行填写 Key）与 `**.env.example`**（模板）。`.env` 已加入 `.gitignore`。

必填项：


| 变量                  | 说明                      |
| ------------------- | ----------------------- |
| `DASHSCOPE_API_KEY` | 百炼 API Key（Embedding）   |
| `ARK_API_KEY`       | 火山方舟 API Key（Chat / 反思） |


其余项见 `.env.example` 注释；Embedding 相关默认值：

```bash
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

## 调用示例

```python
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["DASHSCOPE_API_KEY"],
    base_url=os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
)

resp = client.embeddings.create(
    model=os.environ.get("EMBEDDING_MODEL", "text-embedding-v4"),
    input=["chunk text 1", "chunk text 2"],  # 每批最多 10 条
    dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1024")),
)
vectors = [d.embedding for d in resp.data]
```

## 与检索栈的关系


| 组件    | 技术                            |
| ----- | ----------------------------- |
| 稠密向量  | text-embedding-v4 → Chroma（**正文 + 预设问句** 双写，见下） |
| 关键词   | rank_bm25（**仅正文**，弥补 v4 无稀疏向量） |
| 融合    | RRF（稠密命中按 `chunk_id` 归并） |
| Top-K | 默认 12（`RETRIEVAL_TOP_K`） |

### 双稠密索引（默认开启）

每个 chunk 除 `embed(chunk.text)` 外，ingest 时用 ARK 生成 `INDEX_QUESTIONS_PER_CHUNK` 条预设问句并 `embed(问句)`，一同写入同一 Chroma collection；`metadata.index_role` 为 `content` 或 `question`。在线检索扩大稠密池后归并到 chunk，**生成证据仍用正文**。

详见 [indexing-and-retrieval.md](./indexing-and-retrieval.md)、[architecture.md](../overview/architecture.md)。


## 限制（实现 ingest 时注意）

- 单次请求最多 **10** 条文本
- 单行最多 **8192** tokens
- 国标分块目标 600–800 token/块，一般无需截断

## 备选（仅对照实验，非默认）

- 本地 `BAAI/bge-m3`
- DashScope `text-embedding-v3`
- 火山 `doubao-embedding-large-text-`*

详见 [archive/requirements-discussion-log.md](../archive/requirements-discussion-log.md) §4、§10（历史）；现行见 [architecture.md](../overview/architecture.md)。