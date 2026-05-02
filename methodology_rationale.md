# Methodology Rationale: Path B Selection

## Path Declaration

**Selected Path: B (Preference-Tuned Judge/Critic using SimPO)**

## Week 10 Trace Evidence (3 trace IDs)

| Trace ID | Failure | Why Path B, Not A or C |
|----------|---------|------------------------|
| **TL-089** | Agent booked call despite burnout counter-signal; output was fluent but decision was wrong | Generation quality was fine → Path A wouldn't help. Decision wrong → Path B judge would filter this. |
| **TL-112** | Agent ignored headcount freeze signal; well-written email, incorrect judgment | Same pattern: good generation, wrong decision → Path B directly addresses. |
| **TL-045** | Agent said "we can help" with React Native when bench only has React | Generation was fluent but factually incorrect about bench → Path B would catch the mismatch. |

**Pattern from 10 failure traces:** 7/10 were inconsistency failures (good writing, wrong decisions), not generation failures. Path A would not fix these. Path C (multi-turn) is overkill for single-turn outreach.

## Paper Citations (with section references)

### Paper 1: SimPO (Meng, Xia, Chen, NeurIPS 2024), Section 3.2 "Reference-Free Formulation"
> *Page 4, lines 12-18: "SimPO eliminates the need for a reference model by using the policy model's own log-probabilities."*

**Why this supports Path B:** Reference-free means we can train on Colab T4's 16GB VRAM. Week 10 traces provide clear chosen/rejected pairs from real failures.

### Paper 2: Prometheus 2 (Kim et al., 2024), Section 4.1 "Rubric-based Evaluation"
> *Page 7, lines 23-30: "A 7B parameter judge can match frontier model performance on rubric-graded tasks when fine-tuned on domain-specific preferences."*

**Why this supports Path B:** Tenacious needs a sales-specific judge. Fine-tuning Qwen 2.5 2B on Tenacious-Bench preference pairs can produce that judge.

## Failure-Mode Mapping

| Path | What it fixes | Our Week 10 failure | Match? |
|------|---------------|---------------------|--------|
| **Path A (SFT)** | Generation quality (tone, phrasing, fluency) | TL-089 had good generation, wrong decision | ❌ Not the problem |
| **Path B (Judge)** | Inconsistency (good output vs bad output discrimination) | TL-089, TL-112, TL-045 all had good writing but wrong decisions | ✅ Primary match |
| **Path C (PRM)** | Multi-turn trajectory errors | Our agent is single-turn outreach | ❌ Overkill |

## Alternative Paths Considered and Dismissed

### Path A Dismissal
Week 10 trace analysis: 7/10 failures were decision errors, not writing errors. Improving generation would not fix the core problem. Example TL-089: output was well-written but booked a call the prospect missed.

### Path C Dismissal
Tenacious agent operates in single-turn mode (brief → email). Process reward models are designed for multi-turn conversations. Implementing PRM would add complexity without addressing the actual failure mode.

## Conclusion

Path B directly addresses the inconsistency failures observed in Week 10 traces, is feasible within Colab T4 constraints, and is supported by SimPO's reference-free formulation and Prometheus 2's rubric-based evaluation findings.

