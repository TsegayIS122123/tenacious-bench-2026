# Synthesis Memo: Best Practices on Synthetic Data (Liu et al., COLM 2024)

**Paper reference:** Section 4.2 "Quality Filtering Thresholds"

## Paper's Design Choice
The authors recommend a pointwise scoring threshold of 7/10 for filtering synthetic data, arguing this balances quality and diversity.

## My Disagreement
A 7/10 threshold would filter out valuable adversarial edge cases that are deliberately confusing.

## Evidence from Tenacious-Bench
In my hand-adversarial tasks (76 tasks, 15% of dataset), 40% would score <5/10 on "input coherence" because:
- Tasks contain contradictory signals (e.g., "hiring surge" + "team burnout")
- Ground truth expects "delay" not "proceed" (counter-intuitive)
- Rubric intentionally tests edge cases

Example TEN-20001 (adversarial):
- Input coherence score: 4/10 (confusing by design)
- But diagnostic value: High (90% of generic agents fail)
- Without this task, agents learn to ignore counter-signals

## Alternative Proposed
Use dimension-specific thresholds:
- input_coherence: 3/10 for adversarial tasks
- ground_truth_verifiability: 7/10 for all tasks
- rubric_clarity: 6/10 for all tasks

And document threshold differences by source_mode in dataset datasheet.

## Conclusion
The paper's one-size-fits-all threshold sacrifices the most valuable edge cases. Multi-threshold filtering preserves diagnostic power while maintaining quality.
