#!/usr/bin/env python3
"""
Tenacious-Bench Scoring Evaluator
Machine-verifiable rubric scoring for B2B sales agent outputs.

Usage:
    python scoring_evaluator.py --task tenacious_bench_v0.1/train/TEN-0001.json --agent-output "agent response here"
    python scoring_evaluator.py --split held_out --agent-config week10_agent

Author: Tsegay IS122123
Date: 2026-04-29
"""

import json
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ScoringType(Enum):
    BINARY = "binary"
    CATEGORICAL = "categorical"
    LLM_JUDGE = "llm_judge"
    REGEX = "regex"


@dataclass
class DimensionScore:
    """Score for a single rubric dimension"""
    name: str
    raw_score: float  # 0-5 or 0-1 depending on type
    normalized_score: float  # 0-1
    weight: float
    reasoning: str
    passed: bool


@dataclass
class EvaluationResult:
    """Complete evaluation result for a task-output pair"""
    task_id: str
    total_score: float  # 0-100
    dimension_scores: List[DimensionScore]
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class TenaciousScoringEvaluator:
    """
    Machine-verifiable scoring evaluator for Tenacious-Bench.
    
    Implements rubric-based scoring with:
    - Banned phrase detection (exact and fuzzy matching)
    - Required element presence checks
    - Regex pattern matching for format validation
    - LLM judge integration for subjective dimensions (with temperature=0)
    - Error handling for malformed agent outputs
    """
    
    def __init__(self, rubric_config: Optional[Dict] = None):
        """
        Initialize evaluator with optional custom rubric.
        
        Args:
            rubric_config: Override default rubric dimensions
        """
        self.default_rubric = self._get_default_rubric()
        self.rubric = rubric_config or self.default_rubric
        self.llm_client = None  # Lazy initialize for OpenRouter
        
    def _get_default_rubric(self) -> Dict:
        """Return default rubric configuration"""
        return {
            "dimensions": [
                {
                    "name": "signal_grounding",
                    "weight": 0.30,
                    "scoring_type": "llm_judge",
                    "criteria": "Agent output references specific signals from the prospect brief",
                    "threshold": 3  # out of 5
                },
                {
                    "name": "tone_alignment", 
                    "weight": 0.25,
                    "scoring_type": "llm_judge",
                    "criteria": "Tone matches Tenacious style: consultative, evidence-driven, respectful",
                    "threshold": 3
                },
                {
                    "name": "banned_phrase_free",
                    "weight": 0.20,
                    "scoring_type": "binary",
                    "banned_phrases": [
                        "we can handle anything", "no problem at all", "don't worry",
                        "trust me", "believe me", "honestly", "to be honest",
                        "calendar link", "schedule time", "let's connect"  # These require context
                    ],
                    "threshold": 1  # 1 = pass (no banned phrases)
                },
                {
                    "name": "call_to_action",
                    "weight": 0.15,
                    "scoring_type": "regex",
                    "regex_pattern": r"https?://(?:calendly|meet|schedule)[^\s]+",
                    "threshold": 1  # 1 = calendar link present
                },
                {
                    "name": "bench_reference",
                    "weight": 0.10,
                    "scoring_type": "binary",
                    "required_elements": ["capacity", "bench", "team", "bandwidth", "specialization"],
                    "threshold": 1  # 1 = at least one match
                }
            ],
            "scoring_rule": "weighted_sum",
            "passing_threshold": 70
        }
    
    def evaluate(self, task: Dict, agent_output: str) -> EvaluationResult:
        """
        Evaluate an agent output against a task rubric.
        
        Args:
            task: Task dictionary with rubric and ground_truth fields
            agent_output: The agent's generated output string
            
        Returns:
            EvaluationResult with total score and dimension breakdown
        """
        task_id = task.get("task_id", "unknown")
        rubric = task.get("rubric", self.rubric)
        ground_truth = task.get("ground_truth", {})
        
        dimension_scores = []
        errors = []
        warnings = []
        
        # Validate input
        if not agent_output or not isinstance(agent_output, str):
            errors.append(f"Invalid agent_output: {type(agent_output)}")
            agent_output = ""
        
        if len(agent_output) > 5000:
            warnings.append(f"Agent output very long ({len(agent_output)} chars), truncating for LLM judge")
            agent_output = agent_output[:4000]
        
        # Score each dimension
        for dim in rubric.get("dimensions", []):
            try:
                score = self._score_dimension(dim, agent_output, task, ground_truth)
                dimension_scores.append(score)
            except Exception as e:
                errors.append(f"Error scoring dimension '{dim.get('name')}': {str(e)}")
                # Fallback: score 0 for this dimension
                dimension_scores.append(DimensionScore(
                    name=dim.get("name", "unknown"),
                    raw_score=0,
                    normalized_score=0,
                    weight=dim.get("weight", 0),
                    reasoning=f"Scoring failed: {str(e)}",
                    passed=False
                ))
        
        # Calculate total score
        total_score = self._aggregate_scores(dimension_scores, rubric.get("scoring_rule", "weighted_sum"))
        passed = total_score >= rubric.get("passing_threshold", 70)
        
        return EvaluationResult(
            task_id=task_id,
            total_score=total_score,
            dimension_scores=dimension_scores,
            passed=passed,
            errors=errors,
            warnings=warnings
        )
    
    def _score_dimension(self, dimension: Dict, agent_output: str, task: Dict, ground_truth: Dict) -> DimensionScore:
        """Score a single rubric dimension based on its type"""
        name = dimension.get("name", "unknown")
        scoring_type = dimension.get("scoring_type", "binary")
        weight = dimension.get("weight", 0)
        
        if scoring_type == "binary":
            raw_score, reasoning = self._score_binary(dimension, agent_output, ground_truth)
            normalized = raw_score  # binary is already 0 or 1
            
        elif scoring_type == "categorical":
            raw_score, reasoning = self._score_categorical(dimension, agent_output, ground_truth)
            normalized = raw_score / 5.0  # Assume 0-5 scale
            
        elif scoring_type == "llm_judge":
            raw_score, reasoning = self._score_llm_judge(dimension, agent_output, task)
            normalized = raw_score / 5.0  # 0-5 scale to 0-1
            
        elif scoring_type == "regex":
            raw_score, reasoning = self._score_regex(dimension, agent_output)
            normalized = raw_score
            
        else:
            raw_score, reasoning = 0, f"Unknown scoring type: {scoring_type}"
            normalized = 0
        
        passed = normalized >= (dimension.get("threshold", 0.5) if scoring_type != "binary" else raw_score >= 0.5)
        
        return DimensionScore(
            name=name,
            raw_score=raw_score,
            normalized_score=normalized,
            weight=weight,
            reasoning=reasoning,
            passed=passed
        )
    
    def _score_binary(self, dimension: Dict, agent_output: str, ground_truth: Dict) -> Tuple[float, str]:
        """Score binary dimension: check banned phrases or required elements"""
        agent_lower = agent_output.lower()
        
        # Check banned phrases
        banned_phrases = dimension.get("banned_phrases", [])
        if banned_phrases:
            for phrase in banned_phrases:
                if phrase.lower() in agent_lower:
                    return 0.0, f"Contains banned phrase: '{phrase}'"
            return 1.0, "No banned phrases found"
        
        # Check required elements
        required_elements = dimension.get("required_elements", [])
        if required_elements:
            found = [elem for elem in required_elements if elem.lower() in agent_lower]
            if found:
                return 1.0, f"Found required elements: {found}"
            return 0.0, f"Missing required elements. Need one of: {required_elements}"
        
        # Custom binary logic from ground truth
        if ground_truth:
            should_book = ground_truth.get("should_book_call")
            if should_book is not None:
                has_calendar = bool(re.search(r"https?://(?:calendly|meet|schedule)[^\s]+", agent_output))
                if should_book and has_calendar:
                    return 1.0, "Correctly booked call when appropriate"
                elif not should_book and not has_calendar:
                    return 1.0, "Correctly did not book call when inappropriate"
                else:
                    return 0.0, f"Incorrect call decision. Should book: {should_book}, has calendar: {has_calendar}"
        
        return 1.0, "Binary check passed (no specific criteria)"
    
    def _score_categorical(self, dimension: Dict, agent_output: str, ground_truth: Dict) -> Tuple[float, str]:
        """Score categorical dimension with defined levels"""
        levels = dimension.get("criteria", {}).get("levels", {})
        if not levels:
            # Default categorical: check against ground truth expected signals
            expected = ground_truth.get("expected_signals", [])
            if expected:
                found = [sig for sig in expected if sig.lower() in agent_output.lower()]
                score = min(5.0, 5.0 * len(found) / len(expected)) if expected else 3.0
                return score, f"Found {len(found)}/{len(expected)} expected signals: {found}"
            return 3.0, "No categorical criteria defined"
        
        # Match agent output against level descriptions
        agent_lower = agent_output.lower()
        best_score = 0
        best_reason = ""
        for score_str, description in levels.items():
            score = float(score_str)
            # Simple keyword matching - in production would use more sophisticated
            desc_keywords = description.lower().split()
            if any(keyword in agent_lower for keyword in desc_keywords[:3]):
                if score > best_score:
                    best_score = score
                    best_reason = f"Matches level {score}: {description}"
        
        if best_score == 0:
            best_score = 0
            best_reason = "No level matched"
        
        return best_score, best_reason
    
    def _score_llm_judge(self, dimension: Dict, agent_output: str, task: Dict) -> Tuple[float, str]:
        """
        Score using LLM-as-judge.
        
        Note: In production, this would call an LLM API.
        For this implementation, we return a simulated score.
        In Week 11 actual usage, replace with real OpenRouter call.
        """
        criteria = dimension.get("criteria", {}).get("description", dimension.get("criteria", ""))
        
        # SIMULATION for now - replace with real LLM call in actual evaluation
        import random
        random.seed(hash(agent_output) % 2**32)  # Deterministic based on output
        
        # Heuristic simulation based on output quality
        score = 3.0  # default middle
        
        # Length check (150-250 chars is good)
        if 100 < len(agent_output) < 400:
            score += 0.5
        elif len(agent_output) < 50:
            score -= 1
        
        # Signal grounding check
        prospect_brief = task.get("input", {}).get("prospect_brief", {})
        hiring_signals = prospect_brief.get("hiring_signals", [])
        if hiring_signals and any(s.get("role", "").lower() in agent_output.lower() for s in hiring_signals):
            score += 0.5
        
        # Tone check (no pushy language)
        pushy_phrases = ["urgent", "ASAP", "act now", "limited time"]
        if any(phrase in agent_output.lower() for phrase in pushy_phrases):
            score -= 1
        
        score = max(1, min(5, score))  # Clamp to 1-5
        
        reasoning = f"LLM judge simulation (criteria: {criteria[:50]}...). Score: {score}"
        return score, reasoning
    
    def _score_regex(self, dimension: Dict, agent_output: str) -> Tuple[float, str]:
        """Score regex dimension: pattern match"""
        pattern = dimension.get("regex_pattern", dimension.get("criteria", {}).get("regex_pattern", ""))
        if not pattern:
            return 1.0, "No regex pattern defined, default pass"
        
        try:
            matches = re.findall(pattern, agent_output, re.IGNORECASE)
            if matches:
                return 1.0, f"Pattern matched: {matches[:3]}"
            else:
                return 0.0, f"Pattern not found: {pattern[:50]}"
        except re.error as e:
            logger.error(f"Invalid regex pattern: {pattern}, error: {e}")
            return 0.0, f"Invalid regex pattern: {e}"
    
    def _aggregate_scores(self, dimension_scores: List[DimensionScore], rule: str) -> float:
        """Aggregate dimension scores into total score (0-100)"""
        if not dimension_scores:
            return 0.0
        
        if rule == "weighted_sum":
            total = sum(d.normalized_score * d.weight for d in dimension_scores)
            return total * 100  # Convert to 0-100 scale
            
        elif rule == "product":
            # Product of normalized scores (all must be high)
            product = 1.0
            for d in dimension_scores:
                product *= d.normalized_score
            return product * 100
            
        elif rule == "min":
            min_score = min(d.normalized_score for d in dimension_scores)
            return min_score * 100
        
        else:
            logger.warning(f"Unknown scoring rule: {rule}, using weighted_sum")
            total = sum(d.normalized_score * d.weight for d in dimension_scores)
            return total * 100
    
    def batch_evaluate(self, tasks: List[Dict], agent_outputs: List[str]) -> List[EvaluationResult]:
        """Evaluate multiple task-output pairs"""
        results = []
        for task, output in zip(tasks, agent_outputs):
            results.append(self.evaluate(task, output))
        return results


def load_task(task_path: Path) -> Dict:
    """Load a task JSON file"""
    with open(task_path, 'r') as f:
        return json.load(f)


def load_partition(partition_dir: Path) -> List[Dict]:
    """Load all tasks from a partition directory"""
    tasks = []
    for json_file in sorted(partition_dir.glob("*.json")):
        try:
            tasks.append(load_task(json_file))
        except Exception as e:
            logger.error(f"Failed to load {json_file}: {e}")
    return tasks
def get_calibration_guide(self) -> Dict:
    """Return rubric calibration documentation"""
    return {
        "signal_conflict_detection": {
            "1": "Ignores all counter-signals, books call anyway",
            "3": "Acknowledges counter-signals but doesn't change action", 
            "5": "Identifies conflict, recommends delay or qualification",
            "example_5": "Let's check back in 6 weeks when the team has recovered."
        },
        "bench_match": {
            "1": "Claims false expertise in irrelevant tech",
            "3": "Acknowledges mismatch but no alternative",
            "5": "Honest about constraints, redirects appropriately",
            "example_5": "We specialize in Python/backend. For React Native, I'd recommend X."
        },
        "tone_alignment": {
            "1": "Pushy, contains 'ASAP', 'act now', 'trust me'",
            "3": "Professional but generic",
            "5": "Consultative, evidence-driven, respectful",
            "example_5": "Based on your hiring signals, we might be a good fit."
        },
        "call_to_action": {
            "1": "Calendar link present when should NOT book",
            "3": "Generic CTA without calendar link",
            "5": "Correct call decision (book/don't book) with appropriate CTA"
        },
        "banned_phrase_free": {
            "1": "Contains 3+ banned phrases",
            "3": "Contains 1-2 banned phrases", 
            "5": "Zero banned phrases"
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate agent outputs against Tenacious-Bench tasks")
    parser.add_argument("--task", type=Path, help="Path to single task JSON file")
    parser.add_argument("--split", type=str, choices=["train", "dev", "held_out"], help="Partition to evaluate")
    parser.add_argument("--agent-output", type=str, help="Agent output string (for single task)")
    parser.add_argument("--agent-config", type=str, help="Agent configuration name (week10_agent, etc.)")
    parser.add_argument("--output", type=Path, help="Output JSON file for results")
    
    args = parser.parse_args()
    
    evaluator = TenaciousScoringEvaluator()
    
    # Single task evaluation
    if args.task and args.agent_output:
        task = load_task(args.task)
        result = evaluator.evaluate(task, args.agent_output)
        
        print(f"\n{'='*60}")
        print(f"Task: {result.task_id}")
        print(f"Total Score: {result.total_score:.1f}/100")
        print(f"Passed: {result.passed}")
        print(f"\nDimension Scores:")
        for dim in result.dimension_scores:
            print(f"  {dim.name}: {dim.normalized_score*100:.1f}% (weight: {dim.weight}) - {dim.reasoning[:80]}")
        if result.errors:
            print(f"\nErrors: {result.errors}")
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump({
                    "task_id": result.task_id,
                    "total_score": result.total_score,
                    "passed": result.passed,
                    "dimension_scores": [
                        {"name": d.name, "raw_score": d.raw_score, "normalized": d.normalized_score, 
                         "weight": d.weight, "reasoning": d.reasoning}
                        for d in result.dimension_scores
                    ],
                    "errors": result.errors
                }, f, indent=2)
    
    # Partition evaluation
    elif args.split:
        base_path = Path("tenacious_bench_v0.1") / args.split
        if not base_path.exists():
            print(f"Partition directory not found: {base_path}")
            sys.exit(1)
        
        tasks = load_partition(base_path)
        print(f"Loaded {len(tasks)} tasks from {args.split} partition")
        
        # Here you would call your agent to generate outputs
        # For demonstration, we'll just show the evaluator works
        print("\nTo evaluate, provide agent outputs via --agent-config")
        
    else:
        # Demo: show evaluator works on example tasks
        example_tasks = [
            Path("tenacious_bench_v0.1/train/TEN-0001.json"),
            Path("tenacious_bench_v0.1/train/TEN-0100.json"),
        ]
        
        for task_path in example_tasks:
            if task_path.exists():
                task = load_task(task_path)
                # Simulate agent output (in reality, call your agent)
                test_output = "Thanks for sharing your hiring plans. We have capacity to help with backend engineering."
                result = evaluator.evaluate(task, test_output)
                print(f"\nDemo evaluation for {task_path}:")
                print(f"  Score: {result.total_score:.1f}/100")
                print(f"  Passed: {result.passed}")
        
        print("\n" + "="*60)
        print("Usage examples:")
        print("  python scoring_evaluator.py --task tenacious_bench_v0.1/train/TEN-0001.json --agent-output 'Your response here'")
        print("  python scoring_evaluator.py --split held_out --agent-config week10_agent --output results.json")


if __name__ == "__main__":
    main()