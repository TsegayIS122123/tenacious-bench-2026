#!/usr/bin/env python3
"""
LLM-as-Judge Filter for Tenacious-Bench
Applies pointwise scoring on three dimensions with per-mode thresholds
"""

import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# ============================================================
# PER-DIMENSION JUDGE THRESHOLDS (documented in code)
# ============================================================
# Each dimension is scored 1-5.
# Threshold varies by source_mode to preserve edge cases.
# ============================================================

JUDGE_THRESHOLDS = {
    "input_coherence": {
        "trace-derived": 4,       # High bar for real traces
        "programmatic": 4,        # High bar for templates
        "multi-llm-synthesis": 3, # Lower bar for synthetic
        "hand-adversarial": 3     # Lowest bar for edge cases
    },
    "ground_truth_verifiability": {
        "trace-derived": 4,
        "programmatic": 4,
        "multi-llm-synthesis": 4,
        "hand-adversarial": 3     # Adversarial can be less verifiable
    },
    "rubric_application_clarity": {
        "trace-derived": 4,
        "programmatic": 3,        # Programmatic rubrics are simpler
        "multi-llm-synthesis": 3,
        "hand-adversarial": 4     # Adversarial needs clarity
    }
}

# Model rotation to prevent preference leakage
# Never use the same model family for generation and judging
ALLOWED_JUDGE_MODELS = {
    "generator_claude": "gpt-4",        # Different family
    "generator_gpt": "claude-3",        # Different family
    "generator_qwen": "deepseek",       # Different family
    "generator_deepseek": "qwen"        # Different family
}


@dataclass
class JudgeResult:
    """Result of judge filtering"""
    passed: bool
    scores: Dict[str, int]
    reasoning: str
    model_used: str


class TaskJudgeFilter:
    """
    LLM-as-Judge filter with per-dimension thresholds.
    
    Three scoring dimensions:
    1. input_coherence: Does the task make logical sense?
    2. ground_truth_verifiability: Can a script verify correctness?
    3. rubric_application_clarity: Can an LLM apply the rubric consistently?
    """
    
    def __init__(self, model_name: str = "qwen/qwen-2.5-72b-instruct"):
        self.model_name = model_name
        self.usage_count = 0
    
    def score_dimension(self, task: Dict, dimension: str) -> Tuple[int, str]:
        """
        Score a single dimension 1-5.
        
        In production, this calls an LLM API.
        For simulation, returns heuristic scores.
        """
        # Simulated scoring for demonstration
        # In production, replace with actual API call:
        #
        # response = openrouter.call(
        #     model=self.model_name,
        #     prompt=f"Rate the following task on {dimension} from 1-5..."
        # )
        
        if dimension == "input_coherence":
            # Check if task has all required fields
            has_input = "input" in task
            has_prospect = "prospect_brief" in task.get("input", {})
            has_bench = "bench_summary" in task.get("input", {})
            
            if has_input and has_prospect and has_bench:
                score = 4
                reasoning = "Task has all required input fields"
            else:
                score = 2
                reasoning = "Task missing required fields"
                
        elif dimension == "ground_truth_verifiability":
            # Check if ground truth is machine-verifiable
            gt = task.get("ground_truth", {})
            has_should_book = "should_book_call" in gt
            has_banned = "banned_phrases" in gt
            
            if has_should_book and has_banned:
                score = 5
                reasoning = "Ground truth has verifiable binary and banned phrase checks"
            elif has_should_book:
                score = 3
                reasoning = "Ground truth has binary check but no banned phrases"
            else:
                score = 1
                reasoning = "Ground truth missing verifiable checks"
                
        elif dimension == "rubric_application_clarity":
            # Check if rubric has clear mechanical criteria
            rubric = task.get("rubric", {})
            dimensions = rubric.get("dimensions", [])
            
            has_binary = any(d.get("scoring_type") == "binary" for d in dimensions)
            has_regex = any(d.get("scoring_type") == "regex" for d in dimensions)
            
            if has_binary and has_regex:
                score = 5
                reasoning = "Rubric has binary and regex checks"
            elif has_binary:
                score = 3
                reasoning = "Rubric has binary checks only"
            else:
                score = 2
                reasoning = "Rubric lacks mechanical checks"
        else:
            score = 3
            reasoning = f"Unknown dimension {dimension}"
        
        return score, reasoning
    
    def evaluate_task(self, task: Dict, source_mode: str) -> JudgeResult:
        """
        Evaluate a task against all three dimensions.
        Returns PASS if all dimensions meet thresholds for this source_mode.
        """
        scores = {}
        reasonings = []
        
        for dimension in ["input_coherence", "ground_truth_verifiability", "rubric_application_clarity"]:
            score, reasoning = self.score_dimension(task, dimension)
            scores[dimension] = score
            reasonings.append(f"{dimension}: {score}/5 - {reasoning}")
        
        # Check thresholds
        passed = True
        for dimension, score in scores.items():
            threshold = JUDGE_THRESHOLDS[dimension].get(source_mode, 3)
            if score < threshold:
                passed = False
                reasonings.append(f"❌ {dimension} score {score} < threshold {threshold} for {source_mode}")
        
        return JudgeResult(
            passed=passed,
            scores=scores,
            reasoning=" | ".join(reasonings),
            model_used=self.model_name
        )
    
    def filter_tasks(self, tasks: List[Tuple[Dict, str]]) -> List[Tuple[Dict, str, JudgeResult]]:
        """
        Filter a list of (task, source_mode) pairs.
        Returns (task, source_mode, judge_result) for tasks that pass.
        """
        results = []
        for task, source_mode in tasks:
            result = self.evaluate_task(task, source_mode)
            if result.passed:
                results.append((task, source_mode, result))
        return results


def get_judge_model_for_generator(generator_model: str) -> str:
    """Get appropriate judge model to prevent preference leakage"""
    for gen_pattern, judge_model in ALLOWED_JUDGE_MODELS.items():
        if gen_pattern in generator_model.lower():
            return judge_model
    return "gpt-4"  # Default fallback


if __name__ == "__main__":
    # Test the judge filter
    print("Testing Judge Filter...")
    judge = TaskJudgeFilter()
    
    # Test task
    test_task = {
        "task_id": "TEST-001",
        "input": {"prospect_brief": {}, "bench_summary": {}},
        "ground_truth": {"should_book_call": True, "banned_phrases": []},
        "rubric": {
            "dimensions": [
                {"scoring_type": "binary"},
                {"scoring_type": "regex"}
            ]
        }
    }
    
    result = judge.evaluate_task(test_task, "programmatic")
    print(f"Source mode: programmatic")
    print(f"Passed: {result.passed}")
    print(f"Scores: {result.scores}")
    print(f"Reasoning: {result.reasoning[:100]}...")
    
    print("\n✅ Judge filter ready")
