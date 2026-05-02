
#!/usr/bin/env python3
"""
LLM-as-Judge Filter for Tenacious-Bench

Features:
- Pointwise scoring on 3 dimensions (input_coherence, ground_truth_verifiability, rubric_clarity)
- Pairwise comparison for duplicate tasks
- Dev-tier vs eval-tier separation (dev for bulk, eval for calibration)
- Persistent logging (JSONL with scores and reasons)

Author: Tsegay IS122123
Date: 2026-05-02
"""

import json
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict

# ============================================================
# CONFIGURATION
# ============================================================
SEED = 421
random.seed(SEED)

# Per-dimension thresholds by source mode
JUDGE_THRESHOLDS = {
    "input_coherence": {
        "trace-derived": 4,
        "programmatic": 4,
        "multi-llm-synthesis": 3,
        "hand-adversarial": 3
    },
    "ground_truth_verifiability": {
        "trace-derived": 4,
        "programmatic": 4,
        "multi-llm-synthesis": 4,
        "hand-adversarial": 3
    },
    "rubric_application_clarity": {
        "trace-derived": 4,
        "programmatic": 3,
        "multi-llm-synthesis": 3,
        "hand-adversarial": 4
    }
}

# Model rotation (prevents preference leakage Li et al., 2025)
DEV_TIER_MODELS = ["qwen/qwen-2.5-72b-instruct", "deepseek/deepseek-chat-v3-0324"]
EVAL_TIER_MODELS = ["claude-3-5-sonnet-20241022", "gpt-4-turbo-2024-04-09"]

# Rotation rule: same family never used for generation and judging
ALLOWED_JUDGE_MODELS = {
    "claude": "gpt-4",
    "gpt": "claude-3",
    "qwen": "deepseek",
    "deepseek": "qwen"
}


@dataclass
class JudgeResult:
    """Per-task judge result with full logging"""
    task_id: str
    source_mode: str
    passed: bool
    scores: Dict[str, int]
    thresholds: Dict[str, int]
    reasoning: str
    model_used: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    is_calibration_sample: bool = False


class TaskJudgeFilter:
    """
    LLM-as-Judge filter with:
    1. Pointwise scoring on 3 dimensions
    2. Pairwise comparison for duplicates
    3. Dev-tier for bulk, eval-tier for calibration (sample of 50)
    4. Persistent JSONL logging
    """
    
    def __init__(self, log_path: Path = Path("judge_logs")):
        self.log_path = log_path
        self.log_path.mkdir(exist_ok=True)
        self.calibration_log = []
        self.bulk_log = []
        
    def score_dimension(self, task: Dict, dimension: str, model_tier: str = "dev") -> Tuple[int, str]:
        """
        Score a single dimension 1-5.
        
        model_tier: "dev" for bulk filtering, "eval" for calibration spot-checks
        """
        # In production, this calls actual LLM API
        # For simulation, uses heuristic scoring
        
        if dimension == "input_coherence":
            has_input = "input" in task
            has_prospect = "prospect_brief" in task.get("input", {})
            has_bench = "bench_summary" in task.get("input", {})
            
            if has_input and has_prospect and has_bench:
                score = 4
                reasoning = "All required input fields present"
            elif has_input:
                score = 2
                reasoning = "Missing prospect_brief or bench_summary"
            else:
                score = 1
                reasoning = "Missing input field"
                
        elif dimension == "ground_truth_verifiability":
            gt = task.get("ground_truth", {})
            has_binary = "should_book_call" in gt
            has_banned = "banned_phrases" in gt
            
            if has_binary and has_banned:
                score = 5
                reasoning = "Has binary and banned phrase checks"
            elif has_binary:
                score = 3
                reasoning = "Has binary check only"
            else:
                score = 1
                reasoning = "No verifiable ground truth"
                
        elif dimension == "rubric_application_clarity":
            rubric = task.get("rubric", {})
            dims = rubric.get("dimensions", [])
            has_regex = any(d.get("scoring_type") == "regex" for d in dims)
            
            if has_regex:
                score = 5
                reasoning = "Has regex patterns for mechanical scoring"
            elif dims:
                score = 3
                reasoning = "Has dimensions but no regex"
            else:
                score = 1
                reasoning = "No rubric dimensions"
        else:
            score = 3
            reasoning = f"Unknown dimension: {dimension}"
        
        # If using eval-tier model, add note to reasoning
        if model_tier == "eval":
            reasoning += " [eval-tier calibration]"
        
        return score, reasoning
    
    def evaluate_task(self, task: Dict, source_mode: str, model_tier: str = "dev") -> JudgeResult:
        """Evaluate a task against all dimensions with per-mode thresholds"""
        scores = {}
        reasonings = []
        
        for dimension in ["input_coherence", "ground_truth_verifiability", "rubric_application_clarity"]:
            score, reasoning = self.score_dimension(task, dimension, model_tier)
            scores[dimension] = score
            reasonings.append(f"{dimension}: {score}/5 - {reasoning}")
        
        # Check thresholds
        passed = True
        thresholds_used = {}
        for dimension, score in scores.items():
            threshold = JUDGE_THRESHOLDS[dimension].get(source_mode, 3)
            thresholds_used[dimension] = threshold
            if score < threshold:
                passed = False
                reasonings.append(f"FAIL: {dimension} score {score} < threshold {threshold}")
        
        return JudgeResult(
            task_id=task.get("task_id", "unknown"),
            source_mode=source_mode,
            passed=passed,
            scores=scores,
            thresholds=thresholds_used,
            reasoning=" | ".join(reasonings),
            model_used="dev-tier" if model_tier == "dev" else "eval-tier",
            is_calibration_sample=(model_tier == "eval")
        )
    
    def pairwise_comparison(self, task_a: Dict, meta_a, task_b: Dict, meta_b) -> Optional[Dict]:
        """
        Compare two similar tasks and return the more diagnostic one.
        
        Diagnostic criteria (in order):
        1. Higher difficulty (hard > medium > easy)
        2. Hand-adversarial > multi-LLM > programmatic > trace-derived
        3. Higher passing scores from judge
        """
        difficulty_rank = {"hard": 3, "medium": 2, "easy": 1}
        score_a = difficulty_rank.get(task_a.get("difficulty", "medium"), 2)
        score_b = difficulty_rank.get(task_b.get("difficulty", "medium"), 2)
        
        if score_a != score_b:
            return task_a if score_a > score_b else task_b
        
        mode_rank = {
            "hand-adversarial": 4,
            "multi-llm-synthesis": 3,
            "programmatic": 2,
            "trace-derived": 1
        }
        score_a = mode_rank.get(task_a.get("source_mode", "programmatic"), 2)
        score_b = mode_rank.get(task_b.get("source_mode", "programmatic"), 2)
        
        if score_a != score_b:
            return task_a if score_a > score_b else task_b
        
        # Too similar, keep both
        return None
    
    def filter_tasks_with_logging(self, tasks: List[Tuple[Dict, str]], 
                                   calibration_sample_size: int = 50) -> Tuple[List[Dict], Path]:
        """
        Filter tasks with persistent logging.
        
        - Bulk filtering uses dev-tier models
        - Random 50-task sample uses eval-tier for calibration
        - All results logged to JSONL
        """
        results = []
        passed_tasks = []
        
        # Separate calibration sample
        random.shuffle(tasks)
        calibration_sample = tasks[:calibration_sample_size]
        bulk_tasks = tasks[calibration_sample_size:]
        
        print(f"📊 Judge Filter Pipeline")
        print(f"   Bulk tasks (dev-tier): {len(bulk_tasks)}")
        print(f"   Calibration sample (eval-tier): {len(calibration_sample)}")
        
        # Process bulk with dev-tier
        for task, source_mode in bulk_tasks:
            result = self.evaluate_task(task, source_mode, model_tier="dev")
            results.append(result)
            if result.passed:
                passed_tasks.append(task)
        
        # Process calibration with eval-tier
        for task, source_mode in calibration_sample:
            result = self.evaluate_task(task, source_mode, model_tier="eval")
            results.append(result)
            if result.passed:
                passed_tasks.append(task)
        
        # Save logs
        log_file = self.log_path / f"judge_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        with open(log_file, 'w') as f:
            for result in results:
                f.write(json.dumps(asdict(result)) + '\n')
        
        # Also save summary
        summary = {
            "total_tasks": len(tasks),
            "bulk_count": len(bulk_tasks),
            "calibration_count": len(calibration_sample),
            "passed_count": len(passed_tasks),
            "pass_rate": len(passed_tasks) / len(tasks),
            "timestamp": datetime.now().isoformat()
        }
        
        summary_file = self.log_path / f"judge_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"   Pass rate: {summary['pass_rate']:.1%}")
        print(f"   Log saved to: {log_file}")
        
        return passed_tasks, log_file


# For testing
if __name__ == "__main__":
    # Test with dummy tasks
    test_tasks = []
    for i in range(10):
        dummy_task = {
            "task_id": f"TEST-{i:04d}",
            "input": {"prospect_brief": {"company": "Test"}, "bench_summary": {}},
            "ground_truth": {"should_book_call": True, "banned_phrases": []},
            "rubric": {"dimensions": [{"scoring_type": "regex"}]},
            "difficulty": "medium",
            "source_mode": "programmatic"
        }
        test_tasks.append((dummy_task, "programmatic"))
    
    judge = TaskJudgeFilter()
    passed, log_file = judge.filter_tasks_with_logging(test_tasks, calibration_sample_size=3)
    print(f"\n✅ Judge filter test complete. Passed: {len(passed)}/10")
    print(f"   Log file: {log_file}")
