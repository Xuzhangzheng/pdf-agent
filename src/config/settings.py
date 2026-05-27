from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dashscope_api_key: str = ""
    # OpenAI 兼容：Embedding / Chat 等
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # 文本排序（Rerank）专用，与 compatible-mode 不同
    dashscope_rerank_base_url: str = (
        "https://dashscope.aliyuncs.com/compatible-api/v1"
    )
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 10

    reranker_backend: str = "dashscope"
    reranker_model: str = "qwen3-rerank"
    rerank_top_n: int = 5
    reranker_instruct: str = (
        "Given a web search query, retrieve relevant passages that answer the query."
    )
    reranker_local_model: str = "BAAI/bge-reranker-v2-m3"

    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_chat_model: str = "doubao-1-5-lite-32k-250115"
    # 部分豆包模型不支持 response_format=json_object，可设 false 或依赖 ArkClient 自动回退
    ark_chat_json_mode: bool = True
    ark_temperature: float = 0.1

    pdf_input_path: str = "pdf/GBT 1568-2008 键 技术条件.pdf"
    parsed_output_dir: str = "artifacts/parsed"
    faiss_index_dir: str = Field(
        default="artifacts/faiss",
        validation_alias=AliasChoices("FAISS_INDEX_DIR", "CHROMA_PERSIST_DIR"),
    )
    bm25_index_path: str = "artifacts/bm25_index.pkl"
    mineru_output_dir: str = "artifacts/mineru"
    mineru_bin: str = ""
    mineru_model_mode: str = "full"
    mineru_force_reparse: bool = False
    ocr_postprocess_enabled: bool = True
    # 扫描件解析：仅 MinerU（magic-pdf + PaddleOCR）
    pdf_parser_backend: str = "mineru"
    # 可选：对 MinerU 缺口/低置信页做 VL 校对（非臆造补全）
    ocr_vl_correction_enabled: bool = False
    ark_vl_model: str = "doubao-seed-2-0-pro-260215"
    ocr_vl_render_scale: float = 2.0

    mvp_force_scanned: bool = True
    chunk_target_tokens: int = 700
    chunk_overlap_tokens: int = 140

    # 双稠密：正文 + LLM 预设问句各一条向量；BM25 仍仅索引正文
    index_hypothetical_questions: bool = True
    index_questions_per_chunk: int = 2
    index_questions_force_regenerate: bool = False

    retrieval_top_k: int = 12
    # 稠密召回池：FAISS 行数含问句向量，需扩大再按 chunk_id 归并
    retrieval_dense_pool_factor: int = 3
    # 问句含条款号/表意图时，对 metadata 匹配的 chunk 提高 RRF 分
    retrieval_metadata_boost: float = 0.12
    retrieval_min_score: float = 0.35
    bm25_min_score: float = 0.0
    rrf_k: int = 60

    max_reflection: int = 2
    max_re_retrieve: int = 1
    reflection_temperature: float = 0.0

    min_total_text_chars: int = 1500
    min_table_blocks: int = 1
    min_clause_blocks: int = 3
    min_parse_coverage: float = 0.95

    eval_llm_judge_enabled: bool = True
    eval_pass_strict: bool = True
    clause_hit_threshold: float = 0.8

    # Langfuse 自托管观测（替代 artifacts/usage/*.jsonl）
    langfuse_enabled: bool = True
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_log_io: bool = True
    langfuse_io_max_chars: int = 4000

    # 已弃用：仅保留字段兼容旧 .env，不再写入 JSONL
    usage_log_dir: str = "artifacts/usage"
    log_token_usage: bool = True
    log_level: str = "INFO"
    streamlit_server_port: int = 8501

    # Chat API + MongoDB
    api_base_url: str = "http://127.0.0.1:8000"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "pdf_agent"
    chat_history_turns: int = 5

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def resolve_path(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else self.project_root / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
