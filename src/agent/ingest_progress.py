from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from src.config.settings import Settings

ProgressPhase = Literal["start", "done", "error"]
ProgressCallback = Callable[[str, ProgressPhase, str | None], None]

STEP_CHECK = "check"
STEP_DETECT_PDF = "detect_pdf"
STEP_MINERU = "mineru"
STEP_OCR_POSTPROCESS = "ocr_postprocess"
STEP_STRUCTURE = "structure"
STEP_QUALITY = "quality"
STEP_PERSIST = "persist"
STEP_QUESTIONS = "questions"
STEP_EMBED = "embed"
STEP_FAISS = "faiss"
STEP_BM25 = "bm25"


@dataclass(frozen=True)
class IngestStep:
    id: str
    label: str
    hint: str


def noop_progress(_step_id: str, _phase: ProgressPhase, _detail: str | None = None) -> None:
    pass


def report_progress(
    callback: ProgressCallback | None,
    step_id: str,
    phase: ProgressPhase,
    detail: str | None = None,
) -> None:
    if callback is not None:
        callback(step_id, phase, detail)


def build_ingest_plan(settings: Settings) -> list[IngestStep]:
    """按当前配置生成入库流程步骤（供 UI 展示与进度对齐）。"""
    steps: list[IngestStep] = [
        IngestStep(
            STEP_CHECK,
            "环境与 MinerU CLI",
            "检查 magic-pdf 是否可用",
        ),
        IngestStep(
            STEP_DETECT_PDF,
            "PDF 类型检测",
            "确认页数与扫描件策略",
        ),
        IngestStep(
            STEP_MINERU,
            "MinerU 解析（magic-pdf）",
            "单通道 OCR + 版面分析（耗时最长）",
        ),
    ]
    if settings.ocr_postprocess_enabled:
        steps.append(
            IngestStep(
                STEP_OCR_POSTPROCESS,
                "OCR 规则后处理",
                "条款号归一、缺口标记等",
            )
        )
    steps.extend(
        [
            IngestStep(
                STEP_STRUCTURE,
                "结构化分块与表补全",
                "条款/表格块、content_list 补表",
            ),
            IngestStep(
                STEP_QUALITY,
                "质量闸门",
                "覆盖率与最小文本量校验",
            ),
            IngestStep(
                STEP_PERSIST,
                "写入 doc.json",
                "持久化解析清单",
            ),
        ]
    )
    if settings.index_hypothetical_questions:
        steps.append(
            IngestStep(
                STEP_QUESTIONS,
                "预设问句（ARK）",
                f"每 chunk 生成 {settings.index_questions_per_chunk} 条问句",
            )
        )
    steps.extend(
        [
            IngestStep(
                STEP_EMBED,
                "向量嵌入（DashScope）",
                "正文"
                + (" + 问句" if settings.index_hypothetical_questions else "")
                + " 分批 embedding",
            ),
            IngestStep(
                STEP_FAISS,
                "FAISS 索引",
                "双稠密（正文 + 问句）" if settings.index_hypothetical_questions else "稠密向量",
            ),
            IngestStep(
                STEP_BM25,
                "BM25 索引",
                "仅索引正文，供混合检索",
            ),
        ]
    )
    return steps
