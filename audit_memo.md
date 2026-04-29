# Audit Memo: What Public Benchmarks Miss for Tenacious-Style Sales

## The Core Claim

Public benchmarks (τ²-Bench retail, AgentBench, ToolBench) cannot grade **signal-grounding accuracy against conflicting evidence** — a core Tenacious requirement where a prospect's hiring signal contradicts their bench state or team health. τ²-Bench assumes signals are additive; Tenacious requires trade-off reasoning.

## Gap 1: Signal-Conflict Resolution

**What τ²-Bench fails to grade:** When a prospect has "hiring for 3 senior engineers" (strong signal) but also "engineering team reports 60% burnout in last all-hands" (counter-signal), the correct Tenacious action is **delay outreach** until burnout resolves. Generic benchmarks score this as a false negative.

**Week 10 evidence:**
- **Probe PR-014** ("bench is ready but team is burnt out") → agent booked call anyway
- **Probe PR-027** ("hiring signal + layoffs last month") → agent ignored layoff recovery period
- **Probe PR-041** ("high headcount + low engineering satisfaction") → agent treated as pure positive
- **Probe PR-058** ("CEO says 'growing carefully' + aggressive hiring post") → agent misread caution
- **Probe PR-063** ("new funding + Glassdoor 2.8 rating") → agent ignored retention risk
- **Probe PR-079** ("open roles + hiring freeze rumor") → agent treated rumor as noise
- **Probe PR-082** ("Q4 hiring surge + Q1 reorg announced") → agent missed timing conflict
- **Probe PR-094** ("signal confidence 0.3 + explicit 'maybe' language") → agent over-weighted weak signal

**Trace evidence:**
- **Trace TL-089:** Prospect brief showed "hiring 2 backend engineers" + "team post-mortem on burnout". Agent sent calendar link. Prospect no-showed, later said "we're not ready."
- **Trace TL-112:** Signal: "CTO says AI investment" + bench had AI capacity. Agent booked call. But prospect's headcount was frozen for 2 quarters — agent missed.
- **Trace TL-134:** Two positive signals (new funding + open roles) but Glassdoor showed 2.4 rating. Agent sent outreach. No response.
- **Trace TL-156:** "Growing carefully" in CEO letter + aggressive job posting. Agent treated as unqualified positive. Call booked, prospect confused.
- **Trace TL-178:** Q2 hiring surge (Q2 data) + Q1 reorg (older) — agent didn't timestamp-weight correctly. Called in reorg month.

**Why this is non-obvious:** Most benchmarks assume signals are independent and additive. Tenacious requires multiplicative trade-off: one negative counter-signal can zero out multiple positives. No public benchmark tests this.

## Gap 2: Bench-State Awareness Beyond Headcount

**What τ²-Bench fails to grade:** Whether the agent knows Tenacious's own bench capacity, specialization constraints, and geographical availability when evaluating a prospect.

**Week 10 evidence:**
- **Probe PR-103** (bench has Python specialists → prospect needs Go) → agent didn't check
- **Probe PR-108** (bench all in US-East → prospect in EU hours) → agent ignored timezone
- **Probe PR-112** (bench already overcommitted 120%) → agent still booked call
- **Probe PR-117** (prospect needs security clearance → bench has none) → agent missed

**Trace evidence:**
- **Trace TL-045:** Prospect needed React Native (bench has React, not Native). Agent said "we can help." Wrong.
- **Trace TL-067:** Prospect in Singapore. Bench in US-West. Agent booked 9am PT call (midnight SG). No-show.
- **Trace TL-123:** Bench utilization 95% (3 active projects). Prospect wanted immediate start. Agent said "yes." Overcommit.

## Gap 3: Temporal Signal Decay

**What τ²-Bench fails to grade:** Whether the agent correctly weights signals by recency. A layoff from 6 months ago matters differently than 2 weeks ago.

**Week 10 evidence:**
- **Probe PR-129** (funding from 18 months ago + no update) → agent treated as current
- **Probe PR-133** (old signal + newer counter-signal) → agent averaged incorrectly

**Trace evidence:**
- **Trace TL-034:** Prospect raised $50M (24 months old) + no recent news. Agent led with funding. Prospect said "that was two years ago."

## Summary of Gaps

| Gap | Public Benchmark Coverage | Tenacious Requirement |
|-----|--------------------------|----------------------|
| Signal-conflict resolution | None | Trade-off reasoning, negative signal zeroing |
| Bench-state awareness | Partial (only headcount) | Specialization, geography, utilization |
| Temporal signal decay | None | Recency weighting, decay curves |

These gaps are **machine-verifiable** through:
1. Banned conflict patterns (if signal A present AND signal B present → score 0)
2. Required bench-state checks (if prospect location X AND bench no coverage → disqualify)
3. Timestamp comparison (if signal age > threshold → reduced weight)