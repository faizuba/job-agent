# Results

Saved runs of the agent, so I can compare models and prompt changes over time.
Every run here uses the **practice inbox** (`sample_data/fake_inbox.json`, all fictional data),
starts from a fresh tracker (`python main.py reset --fake`), and is scored against the
"What a correct practice run looks like" table in the main README.

## Run index
| Date | Model | Log | Statuses | Skips | Drafts | Steps | Tokens (in + out) | Cost |
|---|---|---|---|---|---|---|---|---|
| 2026-11-16 | claude-sonnet-5-5 | [log](2026-11-16_sonnet-5-5_fake-inbox.txt) | 6/6 | 3/3 | 1/1 | 8 | 65,118 + 4,107 | ~$0.17 |
| 2026-11-16 | claude-haiku-5-5 | [log](2026-11-16_haiku-5-5_fake-inbox.txt) | 6/6 | 3/3 | 1/1 | 7 | 48,974 + 4,751 | ~$0.007 |
| 2026-11-26 | claude-haiku-5-5, caching off | [log](2026-11-26_haiku-5-5_nocache-run1.txt) | 6/6 | 3/3 | 1/1 | 6 | 44,344 + 4,583 | $0.0067 |
| 2026-11-26 | claude-haiku-5-5, caching **on** | [log](2026-11-26_haiku-5-5_cache-run1.txt) | 6/6 | 3/3 | 1/1 | 8 | 63,640 + 4,887 | $0.0044 |
| 2026-11-26 | claude-haiku-5-5, caching off | [log](2026-11-26_haiku-5-5_nocache-run2.txt) | 6/6 | 3/3 | 1/1 | 6 | 45,341 + 4,765 | $0.0069 |
| 2026-11-26 | claude-haiku-5-5, caching **on** | [log](2026-11-26_haiku-5-5_cache-run2.txt) | 6/6 | 3/3 | 1/1 | 7 | 51,791 + 4,311 | $0.0037 |

Cost = input tokens ÷ 1M × input price + output tokens ÷ 1M × output price
(Sonnet 5.5: $2 / $10 per million; Haiku 5.5: $0.10 / $0.50 per million, at the time of these runs).

## What I noticed (2026-11-16)
- **Same score, ~4% of the cost.** On this test set Haiku matched Sonnet on every check.
- **Both models broke the same prompt rule.** Email e06 is a late "we received your application"
  message. Both models tried to move Harbor Capital from `interview` back to `applied`, even though
  the prompt says statuses never move backwards. The rank check in `tracker_db.py` blocked it both
  times. This is why guardrails belong in code, not just in the prompt.
- **Different working styles.** Sonnet updated Harbor Capital across three separate steps and read
  3 emails; Haiku did all its updates in one step and read only 2 emails.
- **Small judgment difference.** Sonnet concluded the Harbor assessment was completed; Haiku flagged
  it as "please confirm." Both are reasonable.
- **Input is most of the cost** (~94% of Sonnet's tokens) because the agent loop re-sends the whole
  conversation on every step.

## Prompt caching experiment (2026-11-26)
**Question:** the agent loop re-sends the whole conversation every step. How much does prompt
caching save?

**Setup:** Haiku 5.5, practice inbox, fresh tracker before every run. Two runs with
`--no-cache`, two with caching on (the default), alternating. Costs come from the token counts
each run printed (see `costs.py` for the prices used).

| | Caching off (avg of 2) | Caching on (avg of 2) | Change |
|---|---|---|---|
| Cost per run | $0.0068 | $0.0041 | **-40%** |
| Input-token cost per run | $0.0045 | $0.0017 | **-62%** |
| Accuracy | 2/2 perfect runs | 2/2 perfect runs | no change |

**Two ways to measure the saving, and why they differ:**
- **Same run, priced both ways:** each cached run reported "without caching ≈ ..., saved 50%".
  This holds the agent's behavior fixed and changes only the price, so it's the cleanest number.
- **Cached runs vs uncached runs:** 40%. Lower because the cached runs happened to take more steps
  (8 and 7 vs 6 and 6). More steps means more tokens, and that's normal run-to-run variation,
  not an effect of caching.

**What the run logs show** (`runs/*.json`, step by step): after step 1, every request read
everything from earlier steps out of the cache and only wrote what the last step added. In run 1,
only 18 of 63,640 input tokens were billed at full price.

**Why it isn't 90%:** caching only discounts *input*. Output tokens (what the model writes) are
5x the price of input and can't be cached. After caching, output is more than half of the bill.

**Sonnet estimate (not measured):** pricing the same cached run 1 token counts at Sonnet 5.5 rates
gives about $0.083 vs $0.176 without caching (-53%). Sonnet's cache reads are relatively
cheaper (0.05x vs 0.1x), so the saving should be at least as large. Confirming it would need real
Sonnet runs.

## Limits / next steps
- Two runs per setting is still a small sample. Models aren't fully deterministic: run each 3+ times.
- The role name isn't always identical: some runs stored "Sales Strategy & Pricing Intern (Summer 2027)".
  An automated eval should match role names loosely.
- Automate the scoring in `tests/test_eval.py` instead of checking by hand.
- Add harder fake emails (e.g. a recruiter writing from a personal address) and re-test.
