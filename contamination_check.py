
#!/usr/bin/env python3
"""
Contamination Prevention Checks for Tenacious-Bench

Three checks:
1. N-gram overlap (threshold: <8-gram overlap)
2. Embedding similarity (threshold: cosine < 0.85)
3. Time-shift verification (dates within Mar-Apr 2026)

Author: Tsegay IS122123
Date: 2026-04-29
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import hashlib

# ============================================================
# CONFIGURATION
# ============================================================
NGRAM_SIZE = 8
EMBEDDING_THRESHOLD = 0.85
TIME_WINDOW_START = datetime(2026, 3, 1)
TIME_WINDOW_END = datetime(2026, 4, 29)
SEED = 421

# ============================================================
# CHECK 1: N-gram Overlap
# ============================================================
def get_ngrams(text: str, n: int = NGRAM_SIZE):
    """Extract n-grams from text"""
    if len(text) < n:
        return set()
    return set(text[i:i+n] for i in range(len(text) - n + 1))

def check_ngram_overlap(train_dir: Path, held_out_dir: Path) -> dict:
    """Check n-gram overlap between train and held-out"""
    print("\n" + "="*60)
    print(f"CHECK 1: {NGRAM_SIZE}-GRAM OVERLAP")
    print("="*60)
    
    # Build train n-grams from input fields
    train_ngrams = set()
    train_files = list(train_dir.glob("*.json"))
    
    for f in train_files:
        if ".metadata" in str(f):
            continue
        with open(f, 'r') as fp:
            task = json.load(fp)
            # Extract input text for n-gram analysis
            input_text = json.dumps(task.get("input", {}))
            train_ngrams.update(get_ngrams(input_text, NGRAM_SIZE))
    
    print(f"  Train n-grams: {len(train_ngrams)} unique")
    
    # Check held-out tasks
    violations = []
    held_out_files = list(held_out_dir.glob("*.json"))
    
    for f in held_out_files:
        if ".metadata" in str(f):
            continue
        with open(f, 'r') as fp:
            task = json.load(fp)
            input_text = json.dumps(task.get("input", {}))
            task_ngrams = get_ngrams(input_text, NGRAM_SIZE)
            overlap = train_ngrams.intersection(task_ngrams)
            
            if len(overlap) > 0:
                violations.append({
                    "task_id": task.get("task_id", f.stem),
                    "overlap_count": len(overlap),
                    "file": str(f)
                })
    
    print(f"  Held-out tasks with overlap: {len(violations)}")
    for v in violations[:5]:
        print(f"    - {v['task_id']}: {v['overlap_count']} overlapping n-grams")
    
    return {
        "check": "ngram",
        "threshold": NGRAM_SIZE,
        "violations": violations,
        "passed": len(violations) == 0
    }

# ============================================================
# CHECK 2: Embedding Similarity (lightweight implementation)
# ============================================================
def get_text_fingerprint(task: dict) -> str:
    """Create a fingerprint for embedding using TF-IDF style features"""
    prospect = task.get("input", {}).get("prospect_brief", {})
    bench = task.get("input", {}).get("bench_summary", {})
    
    features = []
    features.append(prospect.get("company_name", ""))
    features.append(prospect.get("location", ""))
    features.append(str(prospect.get("signal_confidence", "")))
    features.extend([s.get("role", "") for s in prospect.get("hiring_signals", [])])
    features.extend([str(b.get("available_capacity", "")) for b in [bench]])
    features.extend(bench.get("specializations", []))
    
    return " ".join(features).lower()

def simple_similarity(text_a: str, text_b: str) -> float:
    """Simple Jaccard similarity as lightweight embedding alternative"""
    words_a = set(re.findall(r'\b\w+\b', text_a))
    words_b = set(re.findall(r'\b\w+\b', text_b))
    
    if not words_a or not words_b:
        return 0.0
    
    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)
    
    return len(intersection) / len(union)

def check_embedding_similarity(train_dir: Path, held_out_dir: Path) -> dict:
    """Check embedding similarity between train and held-out"""
    print("\n" + "="*60)
    print(f"CHECK 2: SIMILARITY (threshold: {EMBEDDING_THRESHOLD})")
    print("="*60)
    
    # Build train fingerprints
    train_fingerprints = []
    train_files = list(train_dir.glob("*.json"))
    
    for f in train_files:
        if ".metadata" in str(f):
            continue
        with open(f, 'r') as fp:
            task = json.load(fp)
            fingerprint = get_text_fingerprint(task)
            train_fingerprints.append((task.get("task_id", f.stem), fingerprint))
    
    print(f"  Train tasks: {len(train_fingerprints)}")
    
    # Check held-out
    violations = []
    held_out_files = list(held_out_dir.glob("*.json"))
    
    for f in held_out_files:
        if ".metadata" in str(f):
            continue
        with open(f, 'r') as fp:
            task = json.load(fp)
            held_fingerprint = get_text_fingerprint(task)
            
            for train_id, train_fingerprint in train_fingerprints:
                similarity = simple_similarity(held_fingerprint, train_fingerprint)
                if similarity > EMBEDDING_THRESHOLD:
                    violations.append({
                        "task_id": task.get("task_id", f.stem),
                        "similar_to": train_id,
                        "similarity": similarity
                    })
                    break  # Only need one match per held-out task
    
    print(f"  Held-out tasks with high similarity: {len(violations)}")
    for v in violations[:5]:
        print(f"    - {v['task_id']} similar to {v['similar_to']} ({v['similarity']:.3f})")
    
    return {
        "check": "embedding",
        "threshold": EMBEDDING_THRESHOLD,
        "violations": violations,
        "passed": len(violations) == 0
    }

# ============================================================
# CHECK 3: Time-Shift Verification
# ============================================================
def parse_date(date_str: str):
    """Parse various date formats"""
    if not date_str:
        return None
    try:
        if 'T' in date_str:
            return datetime.fromisoformat(date_str.split('T')[0])
        return datetime.strptime(date_str, '%Y-%m-%d')
    except:
        return None

def check_time_shift(held_out_dir: Path) -> dict:
    """Verify all timestamps are within the documented window"""
    print("\n" + "="*60)
    print("CHECK 3: TIME-SHIFT VERIFICATION")
    print("="*60)
    
    violations = []
    held_out_files = list(held_out_dir.glob("*.json"))
    
    for f in held_out_files:
        if ".metadata" in str(f):
            continue
        with open(f, 'r') as fp:
            task = json.load(fp)
            
            timestamp = task.get("input", {}).get("prospect_brief", {}).get("timestamp", "")
            if timestamp:
                ts_date = parse_date(timestamp)
                if ts_date:
                    if ts_date < TIME_WINDOW_START or ts_date > TIME_WINDOW_END:
                        violations.append({
                            "task_id": task.get("task_id", f.stem),
                            "timestamp": timestamp,
                            "reason": f"Outside window {TIME_WINDOW_START.date()} to {TIME_WINDOW_END.date()}"
                        })
    
    print(f"  Held-out tasks: {len(held_out_files)}")
    print(f"  Timestamp violations: {len(violations)}")
    for v in violations[:5]:
        print(f"    - {v['task_id']}: {v['timestamp']}")
    
    return {
        "check": "time_shift",
        "window_start": TIME_WINDOW_START.isoformat(),
        "window_end": TIME_WINDOW_END.isoformat(),
        "violations": violations,
        "passed": len(violations) == 0
    }

# ============================================================
# MAIN
# ============================================================
def main():
    base = Path("tenacious_bench_v0.1")
    
    print("="*60)
    print("CONTAMINATION PREVENTION CHECKS")
    print("="*60)
    print(f"Seed: {SEED}")
    
    # Run all checks
    results = []
    
    # Check 1: N-gram (train vs held-out)
    result1 = check_ngram_overlap(base / "train", base / "held_out")
    results.append(result1)
    
    # Also check dev vs held-out
    result1_dev = check_ngram_overlap(base / "dev", base / "held_out")
    results.append(result1_dev)
    
    # Check 2: Embedding similarity
    result2 = check_embedding_similarity(base / "train", base / "held_out")
    results.append(result2)
    
    # Check 3: Time-shift
    result3 = check_time_shift(base / "held_out")
    results.append(result3)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_passed = all(r["passed"] for r in results)
    
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"  {status} | {r['check']}: {len(r.get('violations', []))} violations")
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Held-out partition is clean")
    else:
        print("❌ CONTAMINATION DETECTED - Review violations above")
    print("="*60)
    
    # Emit structured report
    report = {
        "seed": SEED,
        "timestamp": datetime.now().isoformat(),
        "checks": results,
        "overall_passed": all_passed
    }
    
    with open("contamination_report.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    print("\n📁 Report saved to: contamination_report.json")

if __name__ == "__main__":
    main()
