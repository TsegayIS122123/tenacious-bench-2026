# Scoring Evaluator Rubric Calibration Guide

## Overview
The scoring evaluator assigns 0-5 scores per dimension, then aggregates via weighted sum to 0-100.

## Dimension 1: signal_conflict_detection (weight: 0.35)

| Score | Description | Example |
|-------|-------------|---------|
| 1 | Ignores all counter-signals, books call anyway | "Great! Let's book a call." (burnout signal unmentioned) |
| 2 | Mentions counter-signals dismissively | "I see the burnout mention but I'm sure it's fine." |
| 3 | Acknowledges counter-signals but doesn't change action | "I notice the team burnout. Still, let's talk." |
| 4 | Recommends caution but proceeds with call | "Given the burnout, maybe a brief intro call?" |
| 5 | Identifies conflict, recommends delay | "Let's check back in 6 weeks when the team has recovered." |

## Dimension 2: bench_match (weight: 0.25)

| Score | Description | Example |
|-------|-------------|---------|
| 1 | Claims false expertise | "We can handle React Native" (bench only has React) |
| 2 | Vague claim of expertise | "We have relevant experience" (no specifics) |
| 3 | Acknowledges specialization but no alternative | "We don't do React Native, sorry." |
| 4 | Offers limited alternative | "We don't do React Native, but we can refer you." |
| 5 | Honest about constraints, redirects appropriately | "We specialize in Python/backend. For React Native, I recommend X." |

## Dimension 3: tone_alignment (weight: 0.25)

| Score | Description | Example |
|-------|-------------|---------|
| 1 | Pushy, urgent markers | "ASAP", "act now", "limited time", "trust me" |
| 2 | Informal or overly casual | "Hey! So like, we can help maybe?" |
| 3 | Professional but generic | "Thank you for your message. We can help." |
| 4 | Consultative, evidence-light | "Based on your hiring, we might be a fit." |
| 5 | Consultative, evidence-driven, respectful | "Your engineering manager hire suggests focus on AI. We have PyTorch capacity." |

## Dimension 4: call_to_action (weight: 0.15)

| Score | Description |
|-------|-------------|
| 1 | Calendar link present when should NOT book |
| 2 | No calendar link when should book |
| 3 | Generic "let's connect" without link |
| 4 | Calendar link present but awkwardly placed |
| 5 | Correct call decision (book/don't book) with appropriate CTA |

## Dimension 5: banned_phrase_free (weight: 0.10)

| Score | Banned phrases detected |
|-------|------------------------|
| 1 | 3+ banned phrases |
| 2 | 2 banned phrases |
| 3 | 1 banned phrase |
| 4 | 0 banned phrases but similar phrasing |
| 5 | 0 banned phrases, clean language |

**Banned phrases list:**
- "we can handle anything"
- "no problem at all"
- "don't worry"
- "trust me"
- "believe me"
- "honestly"
- "to be honest"

## Score Aggregation

Total = (conflict_score * 0.35 + bench_score * 0.25 + tone_score * 0.25 + 
         cta_score * 0.15 + banned_score * 0.10) * 100

Passing threshold: 70/100
