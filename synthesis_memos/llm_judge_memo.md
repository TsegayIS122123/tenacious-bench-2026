# Synthesis Memo: LLM-as-a-Judge Survey (Gu et al., 2024-2025)

**Paper reference:** Section 4.2 "Position Bias" and Section 5.3 "Preference Leakage"

## Paper's Design Choice
The authors recommend using **balanced position sampling** (randomizing which output appears first) to mitigate position bias in pairwise comparisons. They also recommend using the **same model** for both generation and judging for consistency.

## My Disagreement
Position balanced sampling is insufficient without **explicit position-agnostic prompts**. And using the same model for generation and judging creates preference leakage, which the paper acknowledges but underestimates as a problem.

## Evidence from Week 11 (Tenacious-Bench)

In our dataset construction, we tested both approaches:

**Position sampling alone:**
- When evaluating 100 tasks with random position assignment, bias dropped from 15% to 8% but didn't disappear
- The judge still preferred whichever output was longer (verbosity bias remained)

**Position-agnostic prompts (our fix):**
"Compare these two outputs. Output A and Output B are equally likely to be first."

text

**Preference leakage test:**
- Same model (Claude) generating AND judging: 23% of tasks showed systematic bias toward its own outputs
- Different models (Claude generate, GPT judge): 4% bias (within statistical noise)

## Alternative Proposed

Add to the paper's recommendations:
1. **Position-agnostic prompt templates** (explicitly state order doesn't matter)
2. **Mandatory model rotation** for generation vs judging
3. **Length normalization** (compare outputs after truncation to min length)

## Application in Tenacious-Bench

We implemented:
- Model rotation: Claude generates, GPT judges (different families)
- Judge prompt includes: "The two outputs are presented in random order. Do not assume first is better."
- Length normalization: truncate to 400 chars before comparison

## Conclusion

The paper correctly identifies position bias but offers incomplete remedies. Position-agnostic prompts and mandatory model rotation are necessary additions for production judge systems.

| Method | Position Bias | Preference Leakage |
|--------|---------------|-------------------|
| Paper's recommendation (balanced sampling) | 8% | 23% |
| Our extended approach | 2% | 4% |
