import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from semantic_catalog.runtime import build_semantic_context

DEFAULT_DB_PATH = "database/local_data_rebuilt.db"
RULES_PATH = "semantic_catalog/business_rules.json"
REGRESSION_REPORT_PATH = "evaluation/deterministic_sql_regression_report.json"
OUT_JSON = "evaluation/semantic_manual_review_report.json"
OUT_MD = "evaluation/semantic_manual_review_report.md"

RULE_LINE_RE = re.compile(r"^\s*-\s+(br_[^\s|]+)\s*\|")


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_questions(cli_questions: List[str], questions_file: str) -> List[str]:
    if cli_questions:
        return [q.strip() for q in cli_questions if q and q.strip()]

    if questions_file and Path(questions_file).exists():
        payload = _read_json(questions_file)
        if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
            return [str(q).strip() for q in payload.get("questions", []) if str(q).strip()]

    if Path(REGRESSION_REPORT_PATH).exists():
        payload = _read_json(REGRESSION_REPORT_PATH)
        results = payload.get("results") or []
        out: List[str] = []
        for row in results:
            q = str((row or {}).get("question") or "").strip()
            if q:
                out.append(q)
        if out:
            return out

    return []


def _extract_rule_ids_from_context(context_text: str) -> List[str]:
    hit: List[str] = []
    for line in (context_text or "").splitlines():
        m = RULE_LINE_RE.match(line)
        if m:
            hit.append(m.group(1))
    return hit


def _validate_rules(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    required_keys = ["id", "name", "description", "rules", "trigger_terms", "sql_guardrails"]
    duplicate_counter = Counter(str(r.get("id") or "").strip() for r in rules)
    duplicate_ids = [rid for rid, c in duplicate_counter.items() if rid and c > 1]

    invalid_items: List[Dict[str, Any]] = []
    for idx, rule in enumerate(rules, start=1):
        rid = str(rule.get("id") or "").strip()
        missing = [k for k in required_keys if k not in rule]
        wrong_types = []
        for list_key in ["rules", "trigger_terms", "sql_guardrails"]:
            if list_key in rule and not isinstance(rule[list_key], list):
                wrong_types.append(f"{list_key}:expected_list")
        if not rid:
            missing.append("id(empty)")
        if missing or wrong_types:
            invalid_items.append(
                {
                    "index": idx,
                    "id": rid,
                    "missing": missing,
                    "wrong_types": wrong_types,
                }
            )

    return {
        "rule_count": len(rules),
        "duplicate_ids": duplicate_ids,
        "invalid_items": invalid_items,
    }


def run_review(db_path: str, questions: List[str], max_each: int) -> Dict[str, Any]:
    rules_payload = _read_json(RULES_PATH)
    rules = rules_payload.get("business_rules") or []
    known_rule_ids = {str(r.get("id") or "").strip() for r in rules if str(r.get("id") or "").strip()}

    validation = _validate_rules(rules)

    question_results: List[Dict[str, Any]] = []
    hit_counter: Counter = Counter()

    for q in questions:
        context_text = build_semantic_context(question=q, db_path=db_path, max_each=max_each)
        hit_rule_ids = _extract_rule_ids_from_context(context_text)
        for rid in hit_rule_ids:
            hit_counter[rid] += 1

        unknown_rule_ids = [rid for rid in hit_rule_ids if rid not in known_rule_ids]
        question_results.append(
            {
                "question": q,
                "hit_rule_ids": hit_rule_ids,
                "hit_rule_count": len(hit_rule_ids),
                "unknown_rule_ids": unknown_rule_ids,
            }
        )

    never_hit_rules = [rid for rid in sorted(known_rule_ids) if hit_counter.get(rid, 0) == 0]

    return {
        "generated_at": datetime.now().isoformat(),
        "db_path": db_path,
        "rules_path": RULES_PATH,
        "question_count": len(questions),
        "validation": validation,
        "rule_hit_frequency": dict(sorted(hit_counter.items(), key=lambda kv: (-kv[1], kv[0]))),
        "never_hit_rules": never_hit_rules,
        "questions": question_results,
    }


def _to_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Semantic Manual Review Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- db_path: {report.get('db_path')}")
    lines.append(f"- rules_path: {report.get('rules_path')}")
    lines.append(f"- question_count: {report.get('question_count')}")

    validation = report.get("validation") or {}
    lines.append("")
    lines.append("## Rule Health")
    lines.append(f"- total_rules: {validation.get('rule_count', 0)}")
    lines.append(f"- duplicate_ids: {len(validation.get('duplicate_ids') or [])}")
    lines.append(f"- invalid_items: {len(validation.get('invalid_items') or [])}")

    if validation.get("duplicate_ids"):
        lines.append("- duplicate_id_list:")
        for rid in validation.get("duplicate_ids"):
            lines.append(f"  - {rid}")

    if validation.get("invalid_items"):
        lines.append("- invalid_rule_items:")
        for item in validation.get("invalid_items"):
            lines.append(
                f"  - index={item.get('index')} id={item.get('id')} missing={item.get('missing')} wrong_types={item.get('wrong_types')}"
            )

    lines.append("")
    lines.append("## Rule Hit Frequency")
    freq = report.get("rule_hit_frequency") or {}
    if not freq:
        lines.append("- no rule hit in current questions")
    else:
        for rid, c in freq.items():
            lines.append(f"- {rid}: {c}")

    never_hit = report.get("never_hit_rules") or []
    lines.append("")
    lines.append("## Never Hit Rules")
    if not never_hit:
        lines.append("- none")
    else:
        for rid in never_hit:
            lines.append(f"- {rid}")

    lines.append("")
    lines.append("## Per Question Rule Hits")
    for item in report.get("questions") or []:
        lines.append("")
        lines.append(f"### {item.get('question')}")
        lines.append(f"- hit_rule_count: {item.get('hit_rule_count')}")
        for rid in item.get("hit_rule_ids") or []:
            lines.append(f"- {rid}")
        unknown_ids = item.get("unknown_rule_ids") or []
        if unknown_ids:
            lines.append(f"- unknown_rule_ids: {', '.join(unknown_ids)}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate semantic manual review report.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite DB path")
    parser.add_argument("--question", action="append", default=[], help="Question text (repeatable)")
    parser.add_argument("--questions-file", default="", help="JSON file with {\"questions\": [...]} ")
    parser.add_argument("--max-each", type=int, default=6, help="Max semantic items per block")
    parser.add_argument("--out-json", default=OUT_JSON, help="Output JSON report path")
    parser.add_argument("--out-md", default=OUT_MD, help="Output Markdown report path")
    args = parser.parse_args()

    questions = _load_questions(args.question, args.questions_file)
    if not questions:
        raise SystemExit("No questions available. Provide --question or --questions-file.")

    report = run_review(db_path=args.db, questions=questions, max_each=max(1, int(args.max_each)))

    out_json_path = Path(args.out_json)
    out_md_path = Path(args.out_md)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_md_path.parent.mkdir(parents=True, exist_ok=True)

    out_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md_path.write_text(_to_markdown(report), encoding="utf-8")

    print(str(out_json_path))
    print(str(out_md_path))


if __name__ == "__main__":
    main()
