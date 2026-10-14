# Quarantined eval cases

Known-failing should-trigger cases deferred to YAN-1114 (skill description tuning).
Excluded from the default `scripts/eval.sh` run via a separate eval directory:

```bash
claude plugin eval ./ycc --eval-dir evals-quarantine --runs 1 --ablation none --no-publish --max-cost-usd 1
```
