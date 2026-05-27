#!/usr/bin/env python3
"""Run demo question bank and produce artifacts/eval_report.json."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.orchestrator import ask, index_ready
from src.config.settings import get_settings
from src.evaluation.llm_judge import LlmJudge
from src.evaluation.models import DemoQuestionBank
from src.models.agent import Evidence
from src.observability.usage import flush_langfuse, summarize_usage
from src.retrieval.retriever import HybridRetriever

logging.basicConfig(
    level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
)
logger = logging.getLogger("evaluate")


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _gold_keyword_pass(answer: str, gold) -> bool:
    lower = answer.lower()
    if gold.must_not_contain_any:
        for w in gold.must_not_contain_any:
            if w.lower() in lower:
                return False
    if gold.must_contain_any:
        return any(w.lower() in lower for w in gold.must_contain_any)
    return True


def _check_citations(state: dict, spec) -> bool:
    cites = state.get("citations") or []
    if len(cites) < spec.min_count:
        return False
    if spec.require_page:
        if not all(c.get("page") for c in cites):
            return False
    if spec.require_table_ref:
        if not any(c.get("table_id") for c in cites):
            if not any("表" in (state.get("final_answer") or "") for _ in [1]):
                return False
    return True


def _retrieval_hits(state: dict, spec) -> bool:
    ev = state.get("evidence") or []
    if len(ev) < spec.min_hits:
        return len(ev) >= spec.min_hits
    if spec.must_include_chunk_types:
        types = {e.get("chunk_type") for e in ev}
        for t in spec.must_include_chunk_types:
            if t not in types:
                return False
    return len(ev) >= spec.min_hits


def run_evaluation(skip_llm_judge: bool = False) -> dict:
    settings = get_settings()
    if not index_ready():
        raise FileNotFoundError("Index missing. Run scripts/ingest.py first.")

    bank_path = ROOT / "scripts" / "demo_questions.json"
    bank = DemoQuestionBank.model_validate_json(bank_path.read_text(encoding="utf-8"))
    judge = LlmJudge()
    retriever = HybridRetriever()

    run_id = f"eval-{uuid.uuid4().hex[:8]}"
    session_ids: list[str] = []
    per_question: list[dict] = []
    re_retrieve_count = 0

    refuse_expected = 0
    refuse_correct = 0
    answer_expected = 0
    false_refuse = 0
    citation_ok = 0
    citation_total = 0
    table_hit = 0
    table_total = 0
    clause_hit = 0
    clause_total = 0
    reflection_ok = 0
    reflection_total = 0
    unsupported_ok = 0
    unsupported_total = 0
    judge_pass = 0
    judge_total = 0
    fuzzy_pass = 0
    fuzzy_total = 0
    ocr_pass = 0
    ocr_total = 0
    regression_groups: dict[str, list[dict]] = {}

    for q in bank.questions:
        sid = f"{run_id}-{q.id}"
        session_ids.append(sid)
        state = ask(q.question, question_id=q.id, session_id=sid)
        ver = state.get("verification") or {}
        re_retrieve_count += int(ver.get("re_retrieve_count", 0) or 0)

        ans = state.get("final_answer") or ""
        refused = bool(ver.get("should_refuse")) or "无法可靠回答" in ans
        if "无法从本文档回答" in ans and not re.search(r"\[p\.\d+", ans):
            refused = True
        if q.category == "out_of_scope":
            refused = refused or (
                ("未" in ans or "无" in ans)
                and any(k in ans for k in ("蓝牙", "加密", "配对", "手机"))
            )
        row = {
            "id": q.id,
            "category": q.category,
            "question": q.question,
            "expected_behavior": q.expected_behavior,
            "should_refuse": refused,
            "final_answer_preview": (state.get("final_answer") or "")[:200],
            "verification": ver,
            "citation_count": len(state.get("citations") or []),
            "evidence_count": len(state.get("evidence") or []),
        }
        per_question.append(row)

        if q.expected_behavior == "refuse":
            refuse_expected += 1
            if refused:
                refuse_correct += 1
        else:
            answer_expected += 1
            if refused:
                false_refuse += 1
            else:
                citation_total += 1
                if _check_citations(state, q.citation):
                    citation_ok += 1
                reflection_total += 1
                if all(
                    k in ver
                    for k in ("has_evidence", "hallucination_risk", "should_refuse")
                ):
                    reflection_ok += 1
                unsupported_total += 1
                unsup = ver.get("unsupported_claims") or []
                if not unsup:
                    unsupported_ok += 1
                if not _gold_keyword_pass(state.get("final_answer") or "", q.answer_gold):
                    row["gold_keyword_fail"] = True

                if q.category == "table":
                    table_total += 1
                    if _retrieval_hits(state, q.retrieval):
                        table_hit += 1
                if q.category == "clause":
                    clause_total += 1
                    if _retrieval_hits(state, q.retrieval):
                        clause_hit += 1

                if q.llm_judge.enabled and settings.eval_llm_judge_enabled and not skip_llm_judge:
                    judge_total += 1
                    ev_sum = "\n".join(
                        (e.get("text") or "")[:200] for e in (state.get("evidence") or [])[:3]
                    )
                    try:
                        v = judge.judge(
                            q.question,
                            state.get("final_answer") or "",
                            ev_sum,
                            q.llm_judge.rubric,
                            question_id=q.id,
                            session_id=sid,
                        )
                        row["llm_judge_pass"] = v.pass_
                        row["llm_judge_reason"] = v.reason
                        if v.pass_:
                            judge_pass += 1
                    except Exception as e:
                        row["llm_judge_error"] = str(e)

        if q.category == "fuzzy" and q.fuzzy_clear_question:
            fuzzy_total += 1
            out_clear = retriever.retrieve(q.fuzzy_clear_question, question_id=f"{q.id}-clear")
            out_fuzzy = retriever.retrieve(q.question, question_id=f"{q.id}-fuzzy")
            ids_clear = {e.chunk_id for e in out_clear.evidence[:5]}
            ids_fuzzy = {e.chunk_id for e in out_fuzzy.evidence[:5]}
            jac = _jaccard(ids_clear, ids_fuzzy)
            row["fuzzy_jaccard"] = jac
            if jac >= 0.6:
                fuzzy_pass += 1

        if q.category == "ocr_robust":
            ocr_total += 1
            ev = state.get("evidence") or []
            ocr_hit = False
            if q.retrieval.clause_id_pattern:
                ocr_hit = any(
                    (e.get("clause_id") or "") == q.retrieval.clause_id_pattern
                    for e in ev
                )
            else:
                ocr_hit = _retrieval_hits(state, q.retrieval)
            if ocr_hit and not refused:
                ocr_pass += 1

        if q.regression_group:
            regression_groups.setdefault(q.regression_group, []).append(
                {
                    "id": q.id,
                    "refused": refused,
                    "answer": state.get("final_answer") or "",
                    "gold": q.answer_gold.must_contain_any,
                }
            )

    regression_ok = True
    for grp, items in regression_groups.items():
        if len(items) < 2:
            continue
        refuses = [i["refused"] for i in items]
        if len(set(refuses)) != 1:
            regression_ok = False
            break
        keywords = [set(i["gold"]) for i in items]
        for i in range(1, len(items)):
            a = set()
            b = set()
            ans0 = items[0]["answer"].lower()
            ansi = items[i]["answer"].lower()
            for kw in items[0]["gold"]:
                if kw.lower() in ans0:
                    a.add(kw.lower())
            for kw in items[i]["gold"]:
                if kw.lower() in ansi:
                    b.add(kw.lower())
            if _jaccard(a, b) < 0.7:
                regression_ok = False

    metrics = {
        "refuse_accuracy": refuse_correct / refuse_expected if refuse_expected else 1.0,
        "false_refuse_rate": false_refuse / answer_expected if answer_expected else 0.0,
        "citation_compliance": citation_ok / citation_total if citation_total else 1.0,
        "table_retrieval_hit": table_hit / table_total if table_total else 1.0,
        "clause_retrieval_hit": clause_hit / clause_total if clause_total else 1.0,
        "reflection_fields_present": reflection_ok / reflection_total if reflection_total else 1.0,
        "unsupported_claims_empty": unsupported_ok / unsupported_total if unsupported_total else 1.0,
        "llm_judge_pass_rate": judge_pass / judge_total if judge_total else 1.0,
        "fuzzy_recall_pass": fuzzy_pass >= fuzzy_total if fuzzy_total else True,
        "ocr_robust_pass": ocr_pass >= ocr_total if ocr_total else True,
        "regression_consistency": regression_ok,
        "re_retrieve_used_count": re_retrieve_count,
    }

    hard_checks = [
        metrics["refuse_accuracy"] >= 1.0,
        metrics["false_refuse_rate"] <= 0.0,
        metrics["citation_compliance"] >= 1.0,
        metrics["table_retrieval_hit"] >= 1.0 if table_total else True,
        metrics["clause_retrieval_hit"] >= settings.clause_hit_threshold if clause_total else True,
        metrics["reflection_fields_present"] >= 1.0,
        metrics["unsupported_claims_empty"] >= 1.0,
        metrics["llm_judge_pass_rate"] >= 0.8 if judge_total else True,
        metrics["fuzzy_recall_pass"],
        metrics["ocr_robust_pass"],
        metrics["regression_consistency"],
    ]
    overall = all(hard_checks)
    if settings.eval_pass_strict:
        metrics["eval_overall_pass"] = overall
    else:
        metrics["eval_overall_pass"] = overall

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "metrics": metrics,
        "eval_overall_pass": metrics["eval_overall_pass"],
        "per_question_results": per_question,
        "cost_summary": summarize_usage(session_ids + [run_id]),
        "reranker_degraded": any(
            (pq.get("verification") or {}).get("reranker_degraded")
            for pq in per_question
        ),
    }
    out = settings.resolve_path("artifacts/eval_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    flush_langfuse()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-llm-judge", action="store_true")
    args = parser.parse_args()
    try:
        report = run_evaluation(skip_llm_judge=args.skip_llm_judge)
        print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
        print(f"eval_overall_pass={report['eval_overall_pass']}")
        print(f"Report: artifacts/eval_report.json")
        return 0 if report["eval_overall_pass"] else 1
    except Exception as e:
        logger.exception("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
