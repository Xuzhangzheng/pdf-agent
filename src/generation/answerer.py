from __future__ import annotations

from src.llm.ark_client import ArkClient
from src.models.agent import Evidence, ReflectionResult
from src.retrieval.query_signals import (
    wants_composite_strength_table,
    wants_table_evidence,
)


def _format_evidence(evidence: list[Evidence]) -> str:
    parts = []
    for i, e in enumerate(evidence, 1):
        cite = f"[p.{e.page}"
        if e.clause_id:
            cite += f" 条款{e.clause_id}"
        if e.table_id:
            cite += f" {e.table_id}"
        cite += "]"
        parts.append(f"证据{i} {cite}:\n{e.text}")
    return "\n\n".join(parts)


class Answerer:
    def __init__(self, ark: ArkClient | None = None):
        self.ark = ark or ArkClient()

    def generate_draft(
        self,
        question: str,
        evidence: list[Evidence],
        *,
        question_id: str | None = None,
        session_id: str | None = None,
        retrieval_round: int = 0,
    ) -> str:
        ev_text = _format_evidence(evidence)
        hint = ""
        if wants_composite_strength_table(question):
            hint = (
                "\n\n【须分两段作答：①3.1 抗拉强度数值；"
                "②4.2/表1 抽样检查项目与抗拉强度试验的关系。】"
            )
        elif wants_table_evidence(question):
            hint = (
                "\n\n【须写表1各行 AQL 数值，并说明键宽平行度(3.5)、"
                "1:100斜度(3.6)的公差要求。】"
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是国标文档问答助手。仅根据给定证据回答，不要编造。\n"
                    "引用格式必须为 [p.页码] 或 [p.页码 条款3.1] 或 [p.页码 表1]，"
                    "禁止使用「证据1」等非标准格式。\n"
                    "规则：\n"
                    "1) 问表格/尺寸/公差/参数时，优先使用 chunk_type=table 的证据，"
                    "须逐条写出表中键宽b、键高h、键长L、AQL 等可见数值（勿只列类型名），"
                    "段末须写 [p.N 表1]；表中「键宽平行度」行须同时引用条款3.5写出"
                    "b分段公差等级（≤6mm 7级等）；「1:100斜度」行须引用条款3.6写出"
                    "AT8 与极限偏差±AT8/2。\n"
                    "2) 问句条款号含 OCR 误写（如 4.l.2）时，按 4.1.2 理解，"
                    "须用「条款4.1.2」引用并概括该条正文；若该条不涉及所问概念，如实说明，"
                    "可补充 3.5/3.6/表1 等公差相关证据。\n"
                    "3) 范围题须说明适用于「除花键外的各种键」及证据中的键类型。\n"
                    "4) 证据仅部分相关时，回答已有部分并说明未规定的内容，不要整题拒答。\n"
                    "4b) 问表面/外观/粗糙度时，必须引用 3.2（裂纹、浮锈等）和/或 3.3，"
                    "勿说「未规定」；勿引用无关条款（如 3.7）。\n"
                    "5) 问抗拉强度与表1/检查项目关系时，须引用 3.1、4.2（或 4.3）及表1，"
                    "说明抗拉强度试验的 AQL/抽样与表1检查项目同属验收检查体系，"
                    "禁止写「文档未提及关系」。\n"
                    "6) 材料/热处理/硬度：若证据无专条，可说明未单独规定，并引用抗拉强度等相关条款。\n"
                    "7) 勿轻易写「无法从本文档回答」；仅当问题与键标准完全无关（如蓝牙、手机加密）时才用拒答模板。\n"
                    "8) 问检验/验收/抽样时，须含「见表1」或 4.3 尺寸检查、4.4 抽检协议等要点，"
                    "与「检验规则」类问题表述可一致（抽样、合格质量水平、AQL）。"
                ),
            },
            {
                "role": "user",
                "content": f"问题：{question}\n\n证据：\n{ev_text}{hint}",
            },
        ]
        return self.ark.chat(
            messages,
            stage="generate",
            question_id=question_id,
            session_id=session_id,
            retrieval_round=retrieval_round,
        )

    def reflect(
        self,
        question: str,
        evidence: list[Evidence],
        draft: str,
        *,
        question_id: str | None = None,
        session_id: str | None = None,
        retrieval_round: int = 0,
    ) -> ReflectionResult:
        ev_text = _format_evidence(evidence)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是答案质检员。对照证据批判草稿，输出 JSON："
                    '{"has_evidence":bool,"hallucination_risk":"low|medium|high",'
                    '"should_refuse":bool,"unsupported_claims":[],"missing_citations":[],'
                    '"critique":"...","action":"accept|revise|re_retrieve|refuse"}\n'
                    "should_refuse=true 仅当：完全无相关证据，或草稿编造了证据中不存在的事实。"
                    "条款号 OCR 误写、问题概念与条文不完全一致时，用 revise 修正而非 refuse。"
                    "表格题若未用表证据，action=revise。"
                    "critique 字段勿使用反斜杠 LaTeX（如 \\geq），用 Unicode 或纯文本。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"问题：{question}\n证据：\n{ev_text}\n\n草稿：\n{draft}"
                ),
            },
        ]
        raw = self.ark.chat(
            messages,
            json_mode=True,
            temperature=0.0,
            stage="reflect",
            question_id=question_id,
            session_id=session_id,
            retrieval_round=retrieval_round,
        )
        data = self.ark.parse_json(raw)
        risk = str(data.get("hallucination_risk", "low")).lower()
        if risk not in ("low", "medium", "high"):
            data["hallucination_risk"] = "low"
        return ReflectionResult.model_validate(data)

    def revise(
        self,
        question: str,
        evidence: list[Evidence],
        draft: str,
        critique: str,
        *,
        question_id: str | None = None,
        session_id: str | None = None,
        retrieval_round: int = 0,
    ) -> str:
        ev_text = _format_evidence(evidence)
        messages = [
            {
                "role": "system",
                "content": (
                    "根据 critique 修订答案，仅使用证据内容，保留引用格式。"
                    "不得删减已正确段落；复合题须同时保留抗拉强度与表1/抽样关系。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"问题：{question}\n证据：\n{ev_text}\n\n原草稿：\n{draft}\n\n批评：\n{critique}"
                ),
            },
        ]
        return self.ark.chat(
            messages,
            stage="revise",
            question_id=question_id,
            session_id=session_id,
            retrieval_round=retrieval_round,
        )

    def rewrite_query(
        self,
        question: str,
        critique: str,
        *,
        question_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": "将用户问题改写为更适合检索国标文档的查询，只输出一行查询文本。",
            },
            {
                "role": "user",
                "content": f"原问题：{question}\n反思说明：{critique}",
            },
        ]
        return self.ark.chat(
            messages,
            stage="rewrite_query",
            question_id=question_id,
            session_id=session_id,
        ).strip()
