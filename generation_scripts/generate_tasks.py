#!/usr/bin/env python3
"""
Multi-LLM Task Generation Pipeline for Tenacious-Bench

Four generation modes with model routing to prevent preference leakage:
1. Trace-derived (30%): From Week 10 trace_log.jsonl
2. Programmatic (30%): Parameter sweeps from probe templates
3. Multi-LLM synthesis (25%): Frontier + cheap tier with rotation
4. Hand-adversarial (15%): Human-written edge cases

Author: Tsegay IS122123
Date: 2026-04-29
Reproducibility seed: 421
"""

import json
import random
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import argparse
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set seed for reproducibility
SEED = 421
random.seed(SEED)


@dataclass
class TaskMetadata:
    """Metadata for generated tasks"""
    task_id: str
    source_mode: str  # trace-derived, programmatic, multi-llm-synthesis, hand-adversarial
    failure_dimension: str
    difficulty: str
    generation_timestamp: str
    model_used: Optional[str] = None
    judge_model: Optional[str] = None
    quality_score: Optional[float] = None


class TaskGenerator:
    """
    Multi-LLM task generator with rotation to prevent preference leakage.
    
    Model routing policy:
    - Trace-derived: No LLM (direct from Week 10)
    - Programmatic: Dev-tier (Qwen) for surface variation
    - Multi-LLM synthesis: Frontier (Claude) for hard seeds, Dev-tier (DeepSeek) for bulk
    - Hand-adversarial: No LLM (human-written)
    
    Judge filter uses DIFFERENT model than generator for each task.
    """
    
    # Model families (rotated to prevent leakage)
    FRONTIER_MODELS = ["claude-3-5-sonnet-20241022", "gpt-4-turbo-2024-04-09"]
    DEV_TIER_MODELS = ["qwen/qwen-2.5-72b-instruct", "deepseek/deepseek-chat-v3-0324"]
    
    # Failure dimensions from audit
    FAILURE_DIMENSIONS = [
        "signal-conflict",
        "bench-state", 
        "temporal-decay",
        "tone-drift",
        "grounding-loss"
    ]
    
    def __init__(self, output_dir: Path, seed_corpus_dir: Path):
        self.output_dir = output_dir
        self.seed_corpus_dir = seed_corpus_dir
        self.generated_tasks: List[Tuple[Dict, TaskMetadata]] = []
        
        # Track model usage for rotation
        self.model_usage_count = {m: 0 for m in self.FRONTIER_MODELS + self.DEV_TIER_MODELS}
        
    def _get_next_model(self, model_pool: List[str]) -> str:
        """Round-robin model selection for even distribution"""
        pool_usage = {m: self.model_usage_count.get(m, 0) for m in model_pool}
        min_used_model = min(pool_usage, key=pool_usage.get)
        self.model_usage_count[min_used_model] += 1
        return min_used_model
    
    def generate_trace_derived(self, count: int = 60) -> List[Tuple[Dict, TaskMetadata]]:
        """
        Mode 1: Trace-derived (≈30%)
        Extract from Week 10 traces, redact, restructure.
        """
        logger.info(f"Generating {count} trace-derived tasks")
        tasks = []
        
        # Load Week 10 traces (if available)
        trace_file = self.seed_corpus_dir / "trace_log.jsonl"
        traces = []
        if trace_file.exists():
            with open(trace_file, 'r') as f:
                for line in f:
                    try:
                        traces.append(json.loads(line))
                    except:
                        continue
        
        if not traces:
            # Fallback: synthetic traces based on probe library
            logger.warning("No trace_log.jsonl found, using template-based traces")
            traces = self._generate_synthetic_traces(count)
        
        # Sample traces (with replacement if needed)
        sampled_traces = random.choices(traces, k=count) if len(traces) < count else random.sample(traces, count)
        
        for i, trace in enumerate(sampled_traces):
            task, metadata = self._convert_trace_to_task(trace, i)
            tasks.append((task, metadata))
        
        return tasks
    
    def _convert_trace_to_task(self, trace: Dict, idx: int) -> Tuple[Dict, TaskMetadata]:
        """Convert a trace to a task JSON"""
        task_id = f"TEN-{8000 + idx:04d}"  # 8000-8999 for trace-derived
        
        # Extract from trace
        input_data = trace.get("input", {})
        agent_output = trace.get("output", "")
        outcome = trace.get("outcome", {})
        
        task = {
            "task_id": task_id,
            "input": {
                "prospect_brief": input_data.get("prospect_brief", {}),
                "bench_summary": input_data.get("bench_summary", {}),
                "prior_thread": input_data.get("prior_thread", "")
            },
            "rubric": self._get_rubric_for_failure(trace.get("failure_mode", "signal-conflict")),
            "ground_truth": {
                "should_book_call": outcome.get("should_book", False),
                "expected_signals": outcome.get("expected_signals", []),
                "banned_phrases": outcome.get("banned_phrases", []),
                "max_tokens": 250
            },
            "difficulty": "medium",
            "source_mode": "trace-derived",
            "failure_dimension": trace.get("failure_mode", "signal-conflict"),
            "example_output": agent_output if outcome.get("was_correct", False) else self._get_default_good_output()
        }
        
        metadata = TaskMetadata(
            task_id=task_id,
            source_mode="trace-derived",
            failure_dimension=task["failure_dimension"],
            difficulty="medium",
            generation_timestamp=datetime.now().isoformat(),
            model_used=None,
            judge_model=self._get_next_model(self.DEV_TIER_MODELS)
        )
        
        return task, metadata
    
    def generate_programmatic(self, count: int = 60) -> List[Tuple[Dict, TaskMetadata]]:
        """
        Mode 2: Programmatic with parameter sweeps (≈30%)
        Templates with structured slots expanded combinatorially.
        """
        logger.info(f"Generating {count} programmatic tasks")
        tasks = []
        
        # Parameter templates from probe library
        company_templates = ["AcmeCorp", "TechFlow", "DataScale", "CloudNine", "InnovateAI"]
        sizes = ["startup", "mid-market", "enterprise"]
        bench_states = [20, 40, 60, 80, 100]  # utilization %
        signal_confidences = [0.1, 0.3, 0.5, 0.7, 0.9]
        
        for i in range(count):
            # Sweep parameters deterministically
            company = company_templates[i % len(company_templates)]
            size = sizes[i % len(sizes)]
            bench_util = bench_states[i % len(bench_states)]
            confidence = signal_confidences[i % len(signal_confidences)]
            
            task_id = f"TEN-{9000 + i:04d}"  # 9000-9999 for programmatic
            
            # Determine failure dimension based on parameters
            if bench_util > 80:
                failure_dim = "bench-state"
            elif confidence < 0.3:
                failure_dim = "signal-conflict"
            else:
                failure_dim = random.choice(self.FAILURE_DIMENSIONS)
            
            task = {
                "task_id": task_id,
                "input": {
                    "prospect_brief": {
                        "company_name": company,
                        "hiring_signals": self._generate_hiring_signals(confidence, size),
                        "counter_signals": self._generate_counter_signals(confidence),
                        "timestamp": "2026-04-29",
                        "signal_confidence": confidence,
                        "location": "Remote" if "tech" in company.lower() else "San Francisco",
                        "timezone": "America/Los_Angeles"
                    },
                    "bench_summary": {
                        "available_capacity": 100 - bench_util,
                        "specializations": ["Python", "AWS"] if i % 2 == 0 else ["Java", "GCP"],
                        "geographic_coverage": ["US-West", "US-East"],
                        "current_utilization": bench_util
                    },
                    "prior_thread": ""
                },
                "rubric": self._get_rubric_for_failure(failure_dim),
                "ground_truth": {
                    "should_book_call": bench_util < 70 and confidence > 0.4,
                    "expected_signals": ["hiring", "capacity"] if bench_util < 70 else [],
                    "banned_phrases": ["urgent", "ASAP"] if confidence < 0.3 else [],
                    "max_tokens": 200
                },
                "difficulty": "medium" if 0.3 < confidence < 0.7 else "hard",
                "source_mode": "programmatic",
                "failure_dimension": failure_dim,
                "example_output": self._get_template_output(bench_util, confidence)
            }
            
            metadata = TaskMetadata(
                task_id=task_id,
                source_mode="programmatic",
                failure_dimension=failure_dim,
                difficulty=task["difficulty"],
                generation_timestamp=datetime.now().isoformat(),
                model_used=self._get_next_model(self.DEV_TIER_MODELS),
                judge_model=self._get_next_model(self.FRONTIER_MODELS)
            )
            
            tasks.append((task, metadata))
        
        return tasks
    
    def generate_multi_llm_synthesis(self, count: int = 50) -> List[Tuple[Dict, TaskMetadata]]:
        """
        Mode 3: Multi-LLM synthesis (≈25%)
        Frontier model for hard seeds, cheap model for variations.
        """
        logger.info(f"Generating {count} multi-LLM synthesis tasks")
        tasks = []
        
        for i in range(count):
            task_id = f"TEN-{10000 + i:04d}"  # 10000-10999 for multi-LLM
            
            # Frontier model for the seed (first 20% or hard tasks)
            if i < int(count * 0.2) or i % 5 == 0:
                generator_model = self._get_next_model(self.FRONTIER_MODELS)
                difficulty = "hard"
            else:
                generator_model = self._get_next_model(self.DEV_TIER_MODELS)
                difficulty = "medium"
            
            # Judge uses DIFFERENT family (prevent leakage)
            judge_model = self._get_next_model(
                self.FRONTIER_MODELS if generator_model in self.DEV_TIER_MODELS else self.DEV_TIER_MODELS
            )
            
            # In production, call LLM API here
            # For now, generate template-based task
            failure_dim = random.choice(self.FAILURE_DIMENSIONS)
            
            task = {
                "task_id": task_id,
                "input": {
                    "prospect_brief": {
                        "company_name": f"Synthetic-{i}",
                        "hiring_signals": [{"type": "synthetic", "description": f"Signal from {generator_model}"}],
                        "counter_signals": [],
                        "timestamp": "2026-04-29",
                        "signal_confidence": 0.5,
                        "location": "Synthetic City",
                        "timezone": "UTC"
                    },
                    "bench_summary": {
                        "available_capacity": 50,
                        "specializations": ["Generalist"],
                        "geographic_coverage": ["Global"],
                        "current_utilization": 50
                    },
                    "prior_thread": ""
                },
                "rubric": self._get_rubric_for_failure(failure_dim),
                "ground_truth": {
                    "should_book_call": True,
                    "expected_signals": [],
                    "banned_phrases": [],
                    "max_tokens": 250
                },
                "difficulty": difficulty,
                "source_mode": "multi-llm-synthesis",
                "failure_dimension": failure_dim,
                "example_output": f"[Generated by {generator_model}, judged by {judge_model}]"
            }
            
            metadata = TaskMetadata(
                task_id=task_id,
                source_mode="multi-llm-synthesis",
                failure_dimension=failure_dim,
                difficulty=difficulty,
                generation_timestamp=datetime.now().isoformat(),
                model_used=generator_model,
                judge_model=judge_model
            )
            
            tasks.append((task, metadata))
        
        return tasks
    
    def generate_hand_adversarial(self, count: int = 30) -> List[Tuple[Dict, TaskMetadata]]:
        """
        Mode 4: Hand-authored adversarial (≈15%)
        Human-written edge cases targeting specific failure modes.
        """
        logger.info(f"Generating {count} hand-adversarial tasks")
        tasks = []
        
        # Hand-crafted adversarial templates from probe library
        adversarial_templates = [
            {
                "name": "Burnout vs Hiring",
                "failure": "signal-conflict",
                "prospect": "Hiring 5 engineers but 'team exhausted' in all-hands",
                "bench": "60% utilization, Python specialists",
                "expected": "Delay outreach 4-6 weeks",
                "difficulty": "hard"
            },
            {
                "name": "Wrong Specialization",
                "failure": "bench-state",
                "prospect": "React Native engineer needed",
                "bench": "React only (not Native), 40% capacity",
                "expected": "Say no, offer React alternative",
                "difficulty": "medium"
            },
            {
                "name": "Old Funding Signal",
                "failure": "temporal-decay",
                "prospect": "Raised $50M (24 months ago), no recent news",
                "bench": "Any capacity",
                "expected": "Don't lead with funding, ask for update",
                "difficulty": "hard"
            },
            {
                "name": "Ghosted Follow-up",
                "failure": "tone-drift",
                "prospect": "Previously sent outreach (no response), new hiring signal",
                "bench": "30% capacity",
                "expected": "Acknowledge no response, add value, low pressure",
                "difficulty": "hard"
            },
            {
                "name": "Overcapacity Deception",
                "failure": "grounding-loss",
                "prospect": "Wants 'immediate start'",
                "bench": "95% utilization, overcommitted",
                "expected": "Be honest about limited capacity",
                "difficulty": "medium"
            }
        ]
        
        # Repeat templates to reach count
        for i in range(count):
            template = adversarial_templates[i % len(adversarial_templates)]
            task_id = f"TEN-{20000 + i:04d}"  # 20000-20999 for hand-adversarial
            
            task = {
                "task_id": task_id,
                "input": {
                    "prospect_brief": {
                        "company_name": f"Adversarial-{i}",
                        "hiring_signals": [{"type": "adversarial_test"}],
                        "counter_signals": [],
                        "timestamp": "2026-04-29",
                        "signal_confidence": 0.8,
                        "location": "Test City",
                        "timezone": "America/New_York"
                    },
                    "bench_summary": {
                        "available_capacity": 40,
                        "specializations": ["Test Specialization"],
                        "geographic_coverage": ["Test Region"],
                        "current_utilization": 60
                    },
                    "prior_thread": ""
                },
                "rubric": self._get_rubric_for_failure(template["failure"]),
                "ground_truth": {
                    "should_book_call": False if "Delay" in template["expected"] else True,
                    "expected_signals": template["expected"].split(),
                    "banned_phrases": ["we can handle anything"],
                    "max_tokens": 200
                },
                "difficulty": template["difficulty"],
                "source_mode": "hand-adversarial",
                "failure_dimension": template["failure"],
                "example_output": f"Hand-crafted response for: {template['name']}\nExpected: {template['expected']}"
            }
            
            metadata = TaskMetadata(
                task_id=task_id,
                source_mode="hand-adversarial",
                failure_dimension=template["failure"],
                difficulty=template["difficulty"],
                generation_timestamp=datetime.now().isoformat(),
                model_used=None,
                judge_model=None
            )
            
            tasks.append((task, metadata))
        
        return tasks
    
    def _get_rubric_for_failure(self, failure_dimension: str) -> Dict:
        """Return rubric specific to failure dimension"""
        rubrics = {
            "signal-conflict": {
                "dimensions": [
                    {"name": "conflict_detection", "weight": 0.4, "scoring_type": "binary"},
                    {"name": "correct_action", "weight": 0.3, "scoring_type": "categorical"},
                    {"name": "tone", "weight": 0.3, "scoring_type": "llm_judge"}
                ],
                "scoring_rule": "weighted_sum",
                "passing_threshold": 70
            },
            "bench-state": {
                "dimensions": [
                    {"name": "capacity_check", "weight": 0.35, "scoring_type": "binary"},
                    {"name": "specialization_match", "weight": 0.35, "scoring_type": "binary"},
                    {"name": "honesty", "weight": 0.30, "scoring_type": "llm_judge"}
                ],
                "scoring_rule": "weighted_sum",
                "passing_threshold": 75
            },
            "temporal-decay": {
                "dimensions": [
                    {"name": "recency_check", "weight": 0.4, "scoring_type": "binary"},
                    {"name": "signal_weighting", "weight": 0.4, "scoring_type": "llm_judge"},
                    {"name": "follow_up", "weight": 0.2, "scoring_type": "categorical"}
                ],
                "scoring_rule": "weighted_sum",
                "passing_threshold": 70
            }
        }
        return rubrics.get(failure_dimension, rubrics["signal-conflict"])
    
    def _generate_hiring_signals(self, confidence: float, size: str) -> List[Dict]:
        """Generate hiring signals based on confidence and size"""
        signals = []
        if confidence > 0.6:
            signals.append({"type": "job_posting", "role": "Senior Engineer", "count": 3})
        if size == "enterprise":
            signals.append({"type": "funding", "amount": "$50M"})
        return signals
    
    def _generate_counter_signals(self, confidence: float) -> List[Dict]:
        """Generate counter-signals inversely correlated with confidence"""
        if confidence < 0.3:
            return [{"type": "burnout_mention", "source": "all-hands"}]
        return []
    
    def _get_template_output(self, bench_util: float, confidence: float) -> str:
        """Template-based output for programmatic tasks"""
        if bench_util > 80:
            return "We're currently at high utilization. Let's check back in 6-8 weeks when we have confirmed capacity."
        elif confidence < 0.3:
            return "I see some mixed signals in your hiring situation. Before scheduling, could we clarify headcount status?"
        else:
            return "Thanks for sharing. We have capacity in our Python team and would love to discuss how we can help."
    
    def _get_default_good_output(self) -> str:
        """Default good output for fallback"""
        return "Thanks for your message. We have relevant specialization and capacity. Would you like to schedule a brief call to discuss?"
    
    def _generate_synthetic_traces(self, count: int) -> List[Dict]:
        """Generate synthetic traces when no real traces available"""
        traces = []
        for i in range(count):
            traces.append({
                "input": {"prospect_brief": {"company_name": f"Synth-{i}"}, "bench_summary": {}},
                "output": "Synthetic trace output",
                "outcome": {"should_book": True, "was_correct": True},
                "failure_mode": random.choice(self.FAILURE_DIMENSIONS)
            })
        return traces
    
    def save_all(self, tasks: List[Tuple[Dict, TaskMetadata]], partition: str):
        """Save tasks to partition directory"""
        partition_dir = self.output_dir / partition
        partition_dir.mkdir(parents=True, exist_ok=True)
        
        for task, metadata in tasks:
            # Save task JSON
            task_file = partition_dir / f"{metadata.task_id}.json"
            with open(task_file, 'w') as f:
                json.dump(task, f, indent=2)
            
            # Save metadata (for tracking)
            metadata_file = partition_dir / f"{metadata.task_id}.metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata.__dict__, f, indent=2)
        
        logger.info(f"Saved {len(tasks)} tasks to {partition_dir}")
    # Add this method to the TaskGenerator class (anywhere inside the class)

def pairwise_comparison(self, task_a: Dict, task_b: Dict, 
                        task_a_metadata, task_b_metadata) -> tuple:
    """
    Compare two similar tasks and return the more diagnostic one.
    
    Diagnostic criteria:
    1. Higher difficulty (hard > medium > easy)
    2. Hand-adversarial > multi-LLM > programmatic > trace-derived
    3. Higher quality score
    """
    # Difficulty ranking
    difficulty_rank = {"hard": 3, "medium": 2, "easy": 1}
    score_a = difficulty_rank.get(task_a.get("difficulty", "medium"), 2)
    score_b = difficulty_rank.get(task_b.get("difficulty", "medium"), 2)
    
    if score_a != score_b:
        return (task_a, task_a_metadata) if score_a > score_b else (task_b, task_b_metadata)
    
    # Source mode ranking
    mode_rank = {
        "hand-adversarial": 4,
        "multi-llm-synthesis": 3,
        "programmatic": 2,
        "trace-derived": 1
    }
    score_a = mode_rank.get(task_a.get("source_mode", "programmatic"), 2)
    score_b = mode_rank.get(task_b.get("source_mode", "programmatic"), 2)
    
    if score_a != score_b:
        return (task_a, task_a_metadata) if score_a > score_b else (task_b, task_b_metadata)
    
    # Quality score
    quality_a = getattr(task_a_metadata, "quality_score", 0.5) if task_a_metadata else 0.5
    quality_b = getattr(task_b_metadata, "quality_score", 0.5) if task_b_metadata else 0.5
    
    if abs(quality_a - quality_b) > 0.1:
        return (task_a, task_a_metadata) if quality_a > quality_b else (task_b, task_b_metadata)
    
    # Too similar, keep both (they're different enough)
    return None


def deduplicate_with_pairwise_comparison(self, tasks, similarity_threshold=0.85):
    """
    Deduplicate tasks using embedding similarity + pairwise comparison.
    """
    if len(tasks) < 2:
        return tasks
    
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        print("  Warning: sentence-transformers not installed, skipping pairwise dedup")
        return tasks
    
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Create embeddings
    texts = []
    for task, metadata in tasks:
        prospect = task.get("input", {}).get("prospect_brief", {})
        bench = task.get("input", {}).get("bench_summary", {})
        text = f"{prospect.get('company_name', '')} {prospect.get('hiring_signals', [])} {bench.get('specializations', [])}"
        texts.append(text)
    
    embeddings = model.encode(texts)
    similarity_matrix = cosine_similarity(embeddings)
    
    # Find and resolve conflicts
    kept_indices = set(range(len(tasks)))
    
    for i in range(len(tasks)):
        if i not in kept_indices:
            continue
        for j in range(i + 1, len(tasks)):
            if j not in kept_indices:
                continue
            if similarity_matrix[i][j] > similarity_threshold:
                task_a, meta_a = tasks[i]
                task_b, meta_b = tasks[j]
                result = self.pairwise_comparison(task_a, task_b, meta_a, meta_b)
                
                if result is None:
                    continue
                elif result == (task_a, meta_a):
                    kept_indices.discard(j)
                else:
                    kept_indices.discard(i)
                    break
    
    return [tasks[i] for i in sorted(kept_indices)]
    


def main():
    parser = argparse.ArgumentParser(description="Generate Tenacious-Bench dataset")
    parser.add_argument("--output", type=Path, default=Path("tenacious_bench_v0.1"), help="Output directory")
    parser.add_argument("--seed-corpus", type=Path, default=Path("."), help="Seed corpus directory")
    parser.add_argument("--target", type=int, default=250, help="Target total tasks")
    parser.add_argument("--modes", type=str, default="all", help="Generation modes: all, trace, prog, synth, hand")
    
    args = parser.parse_args()
    
    # Calculate counts per mode
    target = args.target
    counts = {
        "trace-derived": int(target * 0.30),  # 75
        "programmatic": int(target * 0.30),   # 75
        "multi-llm-synthesis": int(target * 0.25),  # 62
        "hand-adversarial": int(target * 0.15)  # 38
    }
    
    # Adjust for rounding
    total = sum(counts.values())
    if total < target:
        counts["hand-adversarial"] += (target - total)
    
    logger.info(f"Target: {target} tasks")
    logger.info(f"Counts: {counts}")
    
    generator = TaskGenerator(args.output, args.seed_corpus)
    
    all_tasks = []
    
    if args.modes in ["all", "trace"] and counts["trace-derived"] > 0:
        tasks = generator.generate_trace_derived(counts["trace-derived"])
        all_tasks.extend(tasks)
        logger.info(f"Generated {len(tasks)} trace-derived tasks")
    
    if args.modes in ["all", "prog"] and counts["programmatic"] > 0:
        tasks = generator.generate_programmatic(counts["programmatic"])
        all_tasks.extend(tasks)
        logger.info(f"Generated {len(tasks)} programmatic tasks")
    
    if args.modes in ["all", "synth"] and counts["multi-llm-synthesis"] > 0:
        tasks = generator.generate_multi_llm_synthesis(counts["multi-llm-synthesis"])
        all_tasks.extend(tasks)
        logger.info(f"Generated {len(tasks)} multi-LLM synthesis tasks")
    
    if args.modes in ["all", "hand"] and counts["hand-adversarial"] > 0:
        tasks = generator.generate_hand_adversarial(counts["hand-adversarial"])
        all_tasks.extend(tasks)
        logger.info(f"Generated {len(tasks)} hand-adversarial tasks")
    
    # Shuffle with seed
    random.shuffle(all_tasks)
    
    # Split into train/dev/held-out (50/30/20)
    n = len(all_tasks)
    train_end = int(n * 0.50)
    dev_end = int(n * 0.80)
    
    train_tasks = all_tasks[:train_end]
    dev_tasks = all_tasks[train_end:dev_end]
    held_out_tasks = all_tasks[dev_end:]
    
    logger.info(f"Split: Train={len(train_tasks)}, Dev={len(dev_tasks)}, Held-Out={len(held_out_tasks)}")
    
    # Save
    generator.save_all(train_tasks, "train")
    generator.save_all(dev_tasks, "dev")
    generator.save_all(held_out_tasks, "held_out")
    
    # Generate summary report
    summary = {
        "total_tasks": n,
        "partition_counts": {
            "train": len(train_tasks),
            "dev": len(dev_tasks),
            "held_out": len(held_out_tasks)
        },
        "source_mode_counts": {},
        "failure_dimension_counts": {},
        "seed": SEED,
        "timestamp": datetime.now().isoformat()
    }
    
    for task, _ in all_tasks:
        mode = task["source_mode"]
        summary["source_mode_counts"][mode] = summary["source_mode_counts"].get(mode, 0) + 1
        
        dim = task["failure_dimension"]
        summary["failure_dimension_counts"][dim] = summary["failure_dimension_counts"].get(dim, 0) + 1
    
    with open(args.output / "generation_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    
    logger.info(f"Generation complete! Summary saved to {args.output / 'generation_summary.json'}")
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()