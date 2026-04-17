#!/usr/bin/env python3
"""Generate a single defect QGate title guidance CSV."""

from __future__ import annotations

import argparse
import math
import random
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "report" / "ad_hoc"
VALID_PROJECT_VALUES = {"IDC", "IDCEVO", "MGU", "App", "RSU", "ENTRYEVO"}
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "onto", "while", "when", "where",
    "after", "before", "during", "then", "than", "there", "here", "have", "has", "had", "been",
    "being", "was", "were", "are", "is", "am", "will", "would", "should", "could", "can", "cannot",
    "cant", "not", "does", "doesnt", "did", "didnt", "without", "within", "over", "under", "above",
    "below", "between", "because", "about", "issue", "problem", "error", "abnormal", "abnormally",
    "incorrect", "failed", "failure", "working", "work", "unable", "normal", "properly", "proper",
    "occur", "occurs", "occurred", "happen", "happens", "happened", "display", "shown", "show",
    "shows", "screen", "system", "function", "using", "used", "use", "user", "vehicle", "afterwards",
    "again", "still", "only", "some", "same", "very", "much", "more", "less", "please", "test",
    "testing", "new", "old", "open", "close", "closing", "opening", "set", "get", "gets", "getting",
    "mode", "status", "feature", "case", "ticket", "defect", "canot", "doesn", "didn", "won",
    "wouldn", "shouldn",
}
TOKEN_RE = re.compile(r"[a-z0-9_+-]+|[\u4e00-\u9fff]+", re.IGNORECASE)


def default_db_path() -> Path:
    rebuilt = REPO_ROOT / "database" / "local_data_rebuilt.db"
    if rebuilt.exists():
        return rebuilt
    return REPO_ROOT / "database" / "local_data.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a single title -> top_aida -> function -> project -> owner guidance CSV."
    )
    parser.add_argument("--db-path", default=str(default_db_path()), help="SQLite database path")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT.relative_to(REPO_ROOT)),
        help="Output directory for the generated CSV",
    )
    parser.add_argument("--output", default="", help="Optional explicit output CSV path")
    parser.add_argument("--top-function-count", type=int, default=3, help="Top function candidates kept per AIDA")
    parser.add_argument("--top-project-count", type=int, default=3, help="Top project candidates kept per AIDA/function")
    parser.add_argument("--top-owner-count", type=int, default=3, help="Top owner candidates kept per AIDA/function/project")
    parser.add_argument("--min-token-df", type=int, default=4, help="Minimum token document frequency used in evaluation")
    parser.add_argument("--min-feature-total", type=int, default=20, help="Minimum keyword sample count for title-to-AIDA rules")
    parser.add_argument("--min-match-count", type=int, default=10, help="Minimum label match count for title-to-AIDA rules")
    parser.add_argument("--min-precision", type=float, default=0.45, help="Minimum keyword precision for title-to-AIDA rules")
    parser.add_argument("--min-lift", type=float, default=2.0, help="Minimum keyword lift for title-to-AIDA rules")
    return parser.parse_args()


def _as_repo_path(path_str: str) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def normalize_owner(text: str) -> str:
    value = str(text or "").strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1].strip()
    return value


def normalize_project(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    upper = value.upper()
    if upper == "APP":
        return "App"
    if upper in {"IDCEVO", "ENTRYEVO"}:
        return upper
    return upper


def tokenize(text: str) -> list[str]:
    normalized = str(text or "").lower().replace("/", " ").replace("\\", " ")
    raw_tokens = TOKEN_RE.findall(normalized)
    tokens: list[str] = []
    for token in raw_tokens:
        token = token.strip("_-+ ")
        if not token or token.isdigit():
            continue
        if len(token) < 2 and not re.search(r"[\u4e00-\u9fff]", token):
            continue
        if token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def make_features(text: str) -> list[str]:
    tokens = tokenize(text)
    features = set(tokens)
    for left, right in zip(tokens, tokens[1:]):
        features.add(f"{left} {right}")
    return sorted(features)


def make_model_tokens(text: str) -> list[str]:
    tokens = tokenize(text)
    model_tokens = list(tokens)
    model_tokens.extend(f"{left}_{right}" for left, right in zip(tokens, tokens[1:]))
    return model_tokens


def evaluate_nb(texts: list[str], labels: list[str], min_token_df: int = 4, seed: int = 42) -> dict[str, float | int]:
    indices = list(range(len(texts)))
    rng = random.Random(seed)
    rng.shuffle(indices)
    split = max(1, int(len(indices) * 0.8))
    train_idx = indices[:split]
    test_idx = indices[split:] if split < len(indices) else indices[-max(1, len(indices) // 5):]
    if not test_idx:
        test_idx = train_idx[-1:]
        train_idx = train_idx[:-1]

    train_docs = [make_model_tokens(texts[i]) for i in train_idx]
    test_docs = [make_model_tokens(texts[i]) for i in test_idx]
    train_labels = [labels[i] for i in train_idx]
    test_labels = [labels[i] for i in test_idx]

    token_df: Counter[str] = Counter()
    for doc in train_docs:
        for token in set(doc):
            token_df[token] += 1
    vocab = {token for token, df in token_df.items() if df >= min_token_df}
    if not vocab:
        vocab = set(token_df)
    vocab_size = max(1, len(vocab))

    class_doc_count = Counter(train_labels)
    class_token_count: Counter[str] = Counter()
    feature_count: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for doc, label in zip(train_docs, train_labels):
        filtered = [token for token in doc if token in vocab]
        for token in filtered:
            feature_count[label][token] += 1
            class_token_count[label] += 1

    classes = list(class_doc_count)
    total_docs = len(train_labels)
    alpha = 1.0

    def predict_topk(doc: list[str], k: int = 3) -> list[str]:
        filtered = [token for token in doc if token in vocab]
        doc_counter = Counter(filtered)
        scores: list[tuple[str, float]] = []
        for label in classes:
            prior = math.log(class_doc_count[label] / total_docs)
            denom = class_token_count[label] + alpha * vocab_size
            score = prior
            label_features = feature_count[label]
            for token, count in doc_counter.items():
                score += count * math.log((label_features.get(token, 0) + alpha) / denom)
            scores.append((label, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return [label for label, _ in scores[:k]]

    top1 = 0
    top3 = 0
    for doc, actual in zip(test_docs, test_labels):
        predictions = predict_topk(doc, 3)
        if predictions and predictions[0] == actual:
            top1 += 1
        if actual in predictions:
            top3 += 1

    baseline = class_doc_count.most_common(1)[0][1] / total_docs if total_docs else 0.0
    return {
        "train_size": len(train_idx),
        "test_size": len(test_idx),
        "class_count": len(classes),
        "baseline_top1": baseline,
        "top1": top1 / len(test_idx) if test_idx else 0.0,
        "top3": top3 / len(test_idx) if test_idx else 0.0,
    }


def load_defects(db_path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            """
            SELECT defect_id, name, top_aida, first_use_sop_of_function AS found_in_function,
                   project, owner, team, creation_time
            FROM octane_defects
            ORDER BY creation_time DESC, defect_id DESC
            """,
            conn,
        )
    finally:
        conn.close()

    for col in ["name", "top_aida", "found_in_function", "project", "owner", "team"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["owner"] = df["owner"].apply(normalize_owner)
    df["project"] = df["project"].apply(normalize_project)
    df["features"] = df["name"].apply(make_features)
    return df


def build_title_to_label_rules(
    df: pd.DataFrame,
    label_col: str,
    *,
    min_feature_total: int,
    min_match_count: int,
    min_precision: float,
    min_lift: float,
) -> pd.DataFrame:
    feature_rows: list[tuple[str, str, str]] = []
    for row in df[["defect_id", "features", label_col]].itertuples(index=False):
        if not row.features:
            continue
        for feature in row.features:
            feature_rows.append((row.defect_id, feature, getattr(row, label_col)))

    feature_df = pd.DataFrame(feature_rows, columns=["defect_id", "feature", label_col])
    if feature_df.empty:
        return feature_df

    feature_total = feature_df.groupby("feature").size().rename("feature_total")
    label_total = df.groupby(label_col).size().rename("label_total")

    counts = feature_df.groupby(["feature", label_col]).size().reset_index(name="match_count")
    counts = counts.merge(feature_total, on="feature", how="left")
    counts["label_total"] = counts[label_col].map(label_total)
    counts["precision"] = counts["match_count"] / counts["feature_total"]
    counts["base_rate"] = counts["label_total"] / len(df)
    counts["lift"] = counts["precision"] / counts["base_rate"]
    counts["score"] = counts["precision"] * counts["lift"] * counts["match_count"].apply(lambda value: math.log1p(value))

    counts = counts.sort_values(["feature", "match_count", "precision", "lift"], ascending=[True, False, False, False])
    counts = counts.groupby("feature").head(1).copy()
    counts = counts[
        (counts["feature_total"] >= min_feature_total)
        & (counts["match_count"] >= min_match_count)
        & (counts["precision"] >= min_precision)
        & (counts["lift"] >= min_lift)
    ].copy()
    return counts.sort_values(["score", "match_count"], ascending=[False, False])


def top_n_group_counts(
    df: pd.DataFrame,
    group_cols: list[str],
    share_base_cols: list[str],
    share_name: str,
    rank_name: str,
    top_n: int,
) -> pd.DataFrame:
    counts = df.groupby(group_cols).size().reset_index(name="ticket_count")
    totals = df.groupby(share_base_cols).size().rename("group_total")
    counts["group_total"] = counts.set_index(share_base_cols).index.map(totals)
    counts[share_name] = counts["ticket_count"] / counts["group_total"]
    counts = counts.sort_values(group_cols[:-1] + ["ticket_count", group_cols[-1]], ascending=[True] * (len(group_cols) - 1) + [False, True])
    counts[rank_name] = counts.groupby(share_base_cols).cumcount() + 1
    return counts[counts[rank_name] <= top_n].copy()


def build_guidance_dataframe(
    df: pd.DataFrame,
    *,
    min_feature_total: int,
    min_match_count: int,
    min_precision: float,
    min_lift: float,
    top_function_count: int,
    top_project_count: int,
    top_owner_count: int,
) -> pd.DataFrame:
    valid_project_df = df[df["project"].isin(VALID_PROJECT_VALUES)].copy()
    full_chain_df = valid_project_df[
        (valid_project_df["top_aida"] != "")
        & (valid_project_df["found_in_function"] != "")
        & (valid_project_df["owner"] != "")
    ].copy()
    aida_df = df[df["top_aida"] != ""].copy()
    function_df = df[(df["top_aida"] != "") & (df["found_in_function"] != "")].copy()

    aida_rules = build_title_to_label_rules(
        aida_df,
        "top_aida",
        min_feature_total=min_feature_total,
        min_match_count=min_match_count,
        min_precision=min_precision,
        min_lift=min_lift,
    )
    if aida_rules.empty:
        return pd.DataFrame(columns=[
            "title_keyword", "keyword_ticket_count", "suggested_top_aida", "top_aida_match_count",
            "top_aida_precision", "top_aida_lift", "candidate_found_in_function", "function_rank",
            "function_share_in_top_aida", "candidate_project", "project_rank", "project_share_within_aida_function",
            "candidate_owner", "owner_rank", "owner_share_within_aida_function_project",
        ])

    function_top = top_n_group_counts(
        function_df,
        ["top_aida", "found_in_function"],
        ["top_aida"],
        "function_share_in_top_aida",
        "function_rank",
        top_function_count,
    )
    project_top = top_n_group_counts(
        full_chain_df,
        ["top_aida", "found_in_function", "project"],
        ["top_aida", "found_in_function"],
        "project_share_within_aida_function",
        "project_rank",
        top_project_count,
    ).rename(columns={"project": "candidate_project"})
    owner_top = top_n_group_counts(
        full_chain_df,
        ["top_aida", "found_in_function", "project", "owner"],
        ["top_aida", "found_in_function", "project"],
        "owner_share_within_aida_function_project",
        "owner_rank",
        top_owner_count,
    ).rename(columns={"project": "candidate_project", "owner": "candidate_owner"})

    guidance = aida_rules[["feature", "feature_total", "top_aida", "match_count", "precision", "lift"]].copy()
    guidance = guidance.rename(columns={
        "feature": "title_keyword",
        "feature_total": "keyword_ticket_count",
        "top_aida": "suggested_top_aida",
        "match_count": "top_aida_match_count",
        "precision": "top_aida_precision",
        "lift": "top_aida_lift",
    })
    guidance = guidance.merge(
        function_top[["top_aida", "found_in_function", "function_rank", "function_share_in_top_aida"]].rename(
            columns={"top_aida": "suggested_top_aida", "found_in_function": "candidate_found_in_function"}
        ),
        on="suggested_top_aida",
        how="left",
    )
    guidance = guidance.merge(
        project_top[["top_aida", "found_in_function", "candidate_project", "project_rank", "project_share_within_aida_function"]].rename(
            columns={"top_aida": "suggested_top_aida", "found_in_function": "candidate_found_in_function"}
        ),
        on=["suggested_top_aida", "candidate_found_in_function"],
        how="left",
    )
    guidance = guidance.merge(
        owner_top[[
            "top_aida", "found_in_function", "candidate_project", "candidate_owner", "owner_rank",
            "owner_share_within_aida_function_project",
        ]].rename(columns={"top_aida": "suggested_top_aida", "found_in_function": "candidate_found_in_function"}),
        on=["suggested_top_aida", "candidate_found_in_function", "candidate_project"],
        how="left",
    )
    guidance = guidance.sort_values(
        ["top_aida_precision", "function_rank", "project_rank", "owner_rank"],
        ascending=[False, True, True, True],
    )
    return guidance.reset_index(drop=True)


def choose_output_path(args: argparse.Namespace, output_root: Path) -> Path:
    if args.output:
        return _as_repo_path(args.output)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_root / f"defect_qgate_title_top_aida_function_project_owner_guidance_{timestamp}.csv"


def generate_guidance(
    *,
    db_path: Path,
    output_root: Path,
    output_path: Path | None = None,
    min_feature_total: int = 20,
    min_match_count: int = 10,
    min_precision: float = 0.45,
    min_lift: float = 2.0,
    top_function_count: int = 3,
    top_project_count: int = 3,
    top_owner_count: int = 3,
) -> tuple[Path, pd.DataFrame]:
    defects_df = load_defects(db_path)
    guidance_df = build_guidance_dataframe(
        defects_df,
        min_feature_total=min_feature_total,
        min_match_count=min_match_count,
        min_precision=min_precision,
        min_lift=min_lift,
        top_function_count=top_function_count,
        top_project_count=top_project_count,
        top_owner_count=top_owner_count,
    )

    output_root.mkdir(parents=True, exist_ok=True)
    final_output_path = output_path or choose_output_path(argparse.Namespace(output=""), output_root)
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    guidance_df.to_csv(final_output_path, index=False, encoding="utf-8-sig")
    return final_output_path, guidance_df


def main() -> int:
    args = parse_args()
    db_path = _as_repo_path(args.db_path)
    output_root = _as_repo_path(args.output_root)
    output_path = _as_repo_path(args.output) if args.output else choose_output_path(args, output_root)

    generated_path, guidance_df = generate_guidance(
        db_path=db_path,
        output_root=output_root,
        output_path=output_path,
        min_feature_total=args.min_feature_total,
        min_match_count=args.min_match_count,
        min_precision=args.min_precision,
        min_lift=args.min_lift,
        top_function_count=args.top_function_count,
        top_project_count=args.top_project_count,
        top_owner_count=args.top_owner_count,
    )

    print(f"Guidance written to: {generated_path}")
    print(f"Rows: {len(guidance_df)}")
    print("This generator writes only the main guidance CSV by default.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())