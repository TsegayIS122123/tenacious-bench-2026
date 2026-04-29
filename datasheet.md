# Datasheet for Tenacious-Bench v0.1

## Motivation

**For what purpose was the dataset created?**
Tenacious-Bench evaluates B2B sales agents on three capabilities missing from public benchmarks: signal-conflict resolution, bench-state awareness, and temporal signal decay.

**Who created the dataset?**
Tsegay IS122123 for TRP1 Week 11 deliverable.

**What funding supported the creation?**
Educational/research purposes only.

## Composition

**What do the instances represent?**
Each instance is a (prospect_brief, bench_summary, rubric) tuple simulating a B2B sales outreach scenario.

**How many instances?**
Total: 503 tasks

| Source Mode | Count | Percentage |
|-------------|-------|------------|
| trace-derived | 151 | 30% |
| programmatic | 151 | 30% |
| multi-llm-synthesis | 125 | 25% |
| hand-adversarial | 76 | 15% |

**Partition split:**
| Partition | Count |
|-----------|-------|
| Train | 253 (50%) |
| Dev | 150 (30%) |
| Held-out | 100 (20%) |

**Failure dimensions:**
| Dimension | Count |
|-----------|-------|
| signal-conflict | 101 |
| bench-state | 117 |
| temporal-decay | 107 |
| tone-drift | 92 |
| grounding-loss | 86 |

**Is there any missing information?**
No. All tasks have complete prospect briefs, bench summaries, and rubrics.

**Does the dataset contain confidential data?**
No. All company names are synthetic or redacted from public sources.

## Collection Process

**How was the data collected?**
Four generation modes:
1. Trace-derived (30%): From Week 10 agent traces
2. Programmatic (30%): Parameter sweeps from probe templates
3. Multi-LLM synthesis (25%): Claude + Qwen with rotation
4. Hand-adversarial (15%): Human-written edge cases

**What mechanisms or procedures were used?**
Multi-LLM router with preference leakage prevention (different models for generation vs judging).

## Preprocessing

**Was any preprocessing performed?**
- Redaction of personal/company identifiers from traces
- Date normalization to 2026-03-01 to 2026-04-29 window
- Deduplication via n-gram (6-gram) and embedding similarity

**Is the software used to preprocess available?**
Yes, in `/generation_scripts/` and `/contamination_check.py`.

## Uses

**What tasks can the dataset be used for?**
- Evaluating B2B sales agents on signal grounding
- Training preference models for outreach quality
- Testing LLM judge alignment on rubric dimensions

**What tasks should the dataset not be used for?**
- General dialogue evaluation (domain-specific)
- Non-English sales scenarios

## Distribution

**How will the dataset be distributed?**
HuggingFace Hub under CC-BY-4.0 license.

**When will the dataset be released?**
After Week 11 final submission (April 30, 2026).

## Maintenance

**Who will maintain the dataset?**
Tsegay IS122123 (author).

**How can users report issues?**
GitHub issues on repository.

**Will the dataset be updated?**
v0.2 planned with expanded adversarial tasks and real-world prospect signals.

---

## Layered Detail (Pushkarna et al.)

### Telescopic (High-level)
Tenacious-Bench v0.1: 503-task evaluation suite for B2B sales agent alignment. Four source modes, five failure dimensions, 50/30/20 partition split.

### Periscopic (Internal structure)
- Signal-conflict tasks (101): Test detection of contradictory signals
- Bench-state tasks (117): Test capacity/specialization awareness
- Temporal-decay tasks (107): Test recency weighting
- Tone-drift tasks (92): Test voice consistency
- Grounding-loss tasks (86): Test signal reference accuracy

### Microscopic (Per-example)
Example task TEN-0001 (programmatic):
- Prospect: 3 backend openings + burnout mention
- Expected: Delay outreach, no calendar link
- Difficulty: medium

