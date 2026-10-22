# Proactive allocation: seeded comparison

Measured on 2026-10-22. Each replay uses ten providers and six simulated hours
(08:00–14:00) in a fresh in-memory database. The baseline is backend commit
`eb8384e5da3cb1c69fbb0119b1cf822a750cb5c9`; the updated policy is the working tree.
Both versions use the same evaluator. Matching workload hashes confirm identical
minute-by-minute usage and usable capacity for each paired scenario.

| Measure | Normal, seed 4281: before → after | Volatile, seed 9017: before → after |
|---|---:|---:|
| Shortage provider-minutes | 217 → 217 | 256 → 256 |
| Fully covered in advance | 0 → 171 (78.80%) | 0 → 200 (78.12%) |
| Unresolved provider-minutes | 195 → 46 | 216 → 56 |
| CPU point forecast MAE | 4.203 → 1.232 | 4.641 → 2.662 |
| RAM point forecast MAE | 7.022 → 2.763 | 9.085 → 3.561 |
| Mean predictive contract lead time, minutes | 240.00 → 232.02 | 240.00 → 165.24 |
| Unused reserved CPU-minutes | 0.00 → 4,970.97 | 0.00 → 8,847.91 |
| Unused reserved RAM GB-minutes | 0.00 → 4,558.15 | 0.00 → 19,217.73 |

## What the measures mean

A shortage provider-minute is a minute in which a provider's raw CPU or RAM
deficit exceeds that scenario's unchanged emergency threshold. Advance coverage
requires predictive contracts to cover **both** actual deficits, with the
existing 0.01-unit tolerance. Supplier delivery is limited by observed spare
capacity and shared proportionally among concurrent outgoing contracts; a
face-value promise from an overloaded supplier does not count as prevention.

Unused reservation time is booked capacity beyond the consumer's actual deficit,
measured separately for CPU and RAM. Point forecast errors are measured at their
target times; they are not errors of the upper planning bound. Mean lead time
includes replacement contracts and short uncovered tails, not just first alerts.

## Tradeoffs and limits

Advance coverage and point error improved in these two cases. Conservative
whole-window bounds also reserve substantial unused capacity: about 56%/66% of
CPU reservation-time and 53%/82% of RAM reservation-time in Normal/Volatile.
Reducing that padding and contract fragmentation remains useful follow-up work.

The updated runs contain 258/892 predictive contract rows, including replacements
and small time segments, versus three baseline rows in each case. This is **not**
258/892 independently prevented incidents. The updated runs happen to create no
emergency contract rows, but still leave 46/56 unresolved provider-minutes;
zero emergency rows must not be described as perfect prevention. Budgets, supply
constraints, and genuinely unexpected events still limit recovery.

This is a small reproducible experiment, not a general performance guarantee or
an evaluation against real cloud telemetry. The predictor still uses the declared
simulator baseline as a prior and never reads future observations/events.

Raw results: `proactive_before.json` and `proactive_after.json`.
Reproduce the updated cases from `backend/`:

```powershell
.venv\Scripts\python.exe scripts/evaluate_proactive.py --cases Normal:4281 Volatile:9017 --output benchmarks/proactive_after.json
```

To reproduce the baseline, archive the commit above and pass its `backend/` folder
using `--backend-root` to the **same** evaluator, with `--label before`.
