from __future__ import annotations

from pydantic import BaseModel

from src.llm.ark_client import ArkClient


class JudgeVerdict(BaseModel):
    pass_: bool
    reason: str


class LlmJudge:
    def __init__(self, ark: ArkClient | None = None):
        self.ark = ark or ArkClient()

    def judge(
        self,
        question: str,
        final_answer: str,
        evidence_summary: str,
        rubric: str,
        *,
        question_id: str | None = None,
        session_id: str | None = None,
    ) -> JudgeVerdict:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是评测裁判。仅根据证据与回答判断金标要点是否覆盖。"
                    "金标为要点覆盖而非逐字穷举；与证据一致、未编造、已覆盖 rubric "
                    "核心要求时应判 pass。"
                    '输出 JSON: {"pass": true/false, "reason": "..."}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"问题：{question}\n金标要求：{rubric}\n"
                    f"证据摘要：\n{evidence_summary}\n\n回答：\n{final_answer}"
                ),
            },
        ]
        raw = self.ark.chat(
            messages,
            json_mode=True,
            temperature=0.0,
            stage="llm_judge",
            question_id=question_id,
            session_id=session_id,
        )
        data = self.ark.parse_json(raw)
        return JudgeVerdict(
            pass_=bool(data.get("pass", False)),
            reason=str(data.get("reason", "")),
        )
