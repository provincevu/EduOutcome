"""Debug Chonkie SemanticChunker without modifying the user's original test text.

Usage:
  python debug_chonkie_semantic.py --source path/to/old_semantic_test.py
  python debug_chonkie_semantic.py --source path/to/old_semantic_test.py --threshold 0.7
  python debug_chonkie_semantic.py --source path/to/old_semantic_test.py --thresholds 0.4,0.5,0.6,0.7

A source .py/.txt with a literal `text = '''...'''` and optional constant
MODEL_NAME / SemanticChunker(...) parameters is supported. Code is not executed.
"""
from __future__ import annotations

import argparse
import ast
import csv
import importlib.metadata
import json
import math
from pathlib import Path
from typing import Any


def load_original_script(path: Path) -> dict[str, Any]:
    """Safely read literals from the old script (do not execute source code)."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    constants: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"text", "MODEL_NAME"}:
                    try:
                        constants[target.id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
                if isinstance(target, ast.Name) and target.id == "chunker" and isinstance(node.value, ast.Call):
                    cfg = {}
                    for kw in node.value.keywords:
                        if kw.arg:
                            try:
                                cfg[kw.arg] = ast.literal_eval(kw.value)
                            except (ValueError, TypeError):
                                pass
                    constants["chunker_options"] = cfg
    if not isinstance(constants.get("text"), str):
        raise ValueError("Không tìm thấy biến `text = ...` dạng chuỗi literal trong file nguồn.")
    return constants


def snippet(value: str, limit: int = 160) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[:limit] + "…"


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def stable_indices(groups, sentences) -> list[list[int]]:
    """Map Sentence objects back to one-based sentence indices by identity."""
    lookups = {id(sentence): i + 1 for i, sentence in enumerate(sentences)}
    return [[lookups[id(sentence)] for sentence in group] for group in groups]


def main():
    parser = argparse.ArgumentParser(description="Inspect each phase of Chonkie SemanticChunker")
    parser.add_argument("--source", type=Path, required=True, help="Original test script (.py or .txt)")
    parser.add_argument("--output", type=Path, default=Path("debug_chonkie_output"))
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--thresholds", type=str, default=None,
                        help="Comma-separated list; uses the same embeddings")
    args = parser.parse_args()

    source = load_original_script(args.source)
    text = source["text"]
    model_name = source.get("MODEL_NAME", "AITeamVN/Vietnamese_Embedding_v2")
    options = dict(source.get("chunker_options", {}))
    for key in ("embedding_model",):
        options.pop(key, None)
    options.setdefault("threshold", 0.5)
    options.setdefault("chunk_size", 2048)
    options.setdefault("similarity_window", 1)
    options.setdefault("delim", [". "])
    options.setdefault("include_delim", "prev")
    if args.threshold is not None:
        options["threshold"] = args.threshold
    thresholds = (
        [float(x.strip()) for x in args.thresholds.split(",")]
        if args.thresholds else [float(options["threshold"])]
    )

    import numpy as np
    from chonkie import SemanticChunker, SentenceTransformerEmbeddings

    args.output.mkdir(parents=True, exist_ok=True)
    embedder = SentenceTransformerEmbeddings(model=model_name)
    underlying = getattr(embedder, "model", None)
    if underlying is not None:
        underlying.max_seq_length = 2048

    chunker = SemanticChunker(embedding_model=embedder, **options)
    config = {"model": model_name, "max_seq_length": getattr(underlying, "max_seq_length", None),
              "chonkie_version": importlib.metadata.version("chonkie"), "options": options,
              "thresholds": thresholds, "source": str(args.source)}
    (args.output / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    # Phase 1: split sentences using Chonkie's own implementation
    sentences = chunker._prepare_sentences(text)
    sentence_rows = [
        {"sentence_id": i, "token_count": s.token_count, "characters": len(s.text),
         "text": s.text, "preview": snippet(s.text)}
        for i, s in enumerate(sentences, 1)
    ]
    write_csv(args.output / "01_sentences.csv", sentence_rows,
              ["sentence_id", "token_count", "characters", "preview", "text"])

    # Phase 2: Chonkie's exact raw similarity array, just once for all thresholds
    sims = [float(s) for s in chunker._get_similarity(sentences)] if len(sentences) > chunker.similarity_window else []
    w = chunker.similarity_window
    similarity_rows = []
    for i, score in enumerate(sims):
        # index i compares sentence window [i, i+w) against sentence i+w
        left = "".join(s.text for s in sentences[i:i+w])
        right = sentences[i+w].text
        similarity_rows.append({
            "boundary_before_sentence": i + w + 1, "similarity": score,
            "left_sentence_ids": f"{i+1}-{i+w}", "right_sentence_id": i+w+1,
            "left_text": snippet(left), "right_text": snippet(right),
        })
    write_csv(args.output / "02_similarity.csv", similarity_rows,
              ["boundary_before_sentence", "similarity", "left_sentence_ids", "right_sentence_id", "left_text", "right_text"])

    report = []
    report.append("CHONKIE SEMANTIC CHUNKER - PHASE-BY-PHASE DEBUG")
    report.append("=" * 85)
    report.append(f"Model: {model_name}")
    report.append(f"Chonkie version: {config['chonkie_version']}")
    report.append(f"Config: {options}")
    report.append(f"Source: {args.source}")
    report.append(f"Total sentence units: {len(sentences)}; similarity scores: {len(sims)}")
    report.append("NOTE: 'sentence' means Chonkie's delimiter-split unit, not necessarily a linguistic sentence.")
    report.append("\n=== 1. SENTENCE SPLITTING ===")
    for row in sentence_rows:
        report.append(f"S{row['sentence_id']:03d} ({row['token_count']} tokens): {row['preview']}")
    report.append("\n=== 2. RAW SIMILARITY ===")
    for row in similarity_rows:
        report.append(f"Before S{row['boundary_before_sentence']:03d}: {row['similarity']:.5f} | "
                      f"S{row['left_sentence_ids']} → S{row['right_sentence_id']} | "
                      f"{row['left_text']} || {row['right_text']}")

    for threshold in thresholds:
        chunker.threshold = threshold
        if len(sentences) <= w:
            split_indices = []
        else:
            split_indices = list(chunker._get_split_indices(sims))
        semantic_groups = chunker._group_sentences(sentences, split_indices)
        if chunker.skip_window > 0:
            semantic_groups = chunker._skip_and_merge(semantic_groups)
        final_groups = chunker._split_groups(semantic_groups)
        semantic_ranges = stable_indices(semantic_groups, sentences)
        final_ranges = stable_indices(final_groups, sentences)

        semantic_boundary = {r[0] for r in semantic_ranges[1:] if r}
        final_boundary = {r[0] for r in final_ranges[1:] if r}
        token_boundary = final_boundary - semantic_boundary
        threshold_tag = f"{threshold:g}".replace(".", "p")

        # Real user-facing output for consistency check (may recompute embeddings)
        # Diagnostic stages follow the current Chonkie source. chunk() itself is
        # not re-run by default to keep runtime manageable.
        final_rows = []
        for i, (grp, ids) in enumerate(zip(final_groups, final_ranges), 1):
            group_text = "".join(s.text for s in grp)
            final_rows.append({"chunk_id": i, "sentence_start": ids[0], "sentence_end": ids[-1],
                               "token_count": sum(s.token_count for s in grp), "text": group_text})
        write_csv(args.output / f"03_chunks_t{threshold_tag}.csv", final_rows,
                  ["chunk_id", "sentence_start", "sentence_end", "token_count", "text"])

        boundary_rows = []
        report.append(f"\n=== 3. THRESHOLD={threshold:g} | SEMANTIC AND TOKEN BOUNDARIES ===")
        report.append(f"Semantic group count: {len(semantic_groups)}; final chunks: {len(final_groups)}")
        report.append(f"Semantic boundary sentence IDs: {sorted(semantic_boundary)}")
        report.append(f"Token-limit additional boundaries: {sorted(token_boundary)}")
        for before in sorted(final_boundary):
            kind = "SEMANTIC" if before in semantic_boundary else "TOKEN_LIMIT"
            sim_index = before - w - 1
            score = sims[sim_index] if 0 <= sim_index < len(sims) else float('nan')
            prev = sentences[before-2] if before >= 2 else None
            nxt = sentences[before-1]
            item = {"before_sentence": before, "reason": kind,
                    "raw_similarity": score, "left": snippet(prev.text if prev else ""),
                    "right": snippet(nxt.text)}
            boundary_rows.append(item)
            report.append(f"--- BEFORE S{before:03d} [{kind}] raw_similarity={score:.5f}")
            report.append(f"LEFT : {item['left']}")
            report.append(f"RIGHT: {item['right']}")
        write_csv(args.output / f"04_boundaries_t{threshold_tag}.csv", boundary_rows,
                  ["before_sentence", "reason", "raw_similarity", "left", "right"])
        report.append("\n=== 4. FINAL CHUNKS (this threshold) ===")
        for item in final_rows:
            report.append(f"\nCHUNK {item['chunk_id']} | S{item['sentence_start']}..S{item['sentence_end']} "
                          f"| {item['token_count']} tokens\n{item['text']}")

        # Catch limitations of sentence token budget
        oversized = [r for r in sentence_rows if r["token_count"] > options["chunk_size"]]
        if oversized:
            report.append("\nWARNING: Sentence units exceed chunk_size; _split_groups does not split within a sentence:")
            report.extend([f"  S{r['sentence_id']}: {r['token_count']} tokens" for r in oversized])
        report.append("\nIMPORTANT: semantic boundary detected by peak filtering is NOT a direct raw-similarity < threshold rule.")

    report_path = args.output / "debug_report.txt"
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Model: {model_name}")
    print(f"Sentence units: {len(sentences)}")
    for th in thresholds:
        tag = f"{th:g}".replace(".", "p")
        print(f"Threshold {th:g}: {args.output / ('03_chunks_t' + tag + '.csv')}")
    print("Debug report:", report_path)
    print("Similarity CSV:", args.output / "02_similarity.csv")
    print("Sentence CSV:", args.output / "01_sentences.csv")


if __name__ == "__main__":
    main()
