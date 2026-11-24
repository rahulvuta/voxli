# Context AI evaluation (Card 4)

Hand-labeled sets: `eval/context/names.jsonl` (50 items, synthetic text written by us, not real speech) and `eval/context/replies.jsonl` (12 snippets). Each item runs through the production `ContextEngine.on_final` utterance by utterance (same prompt, validation, auto-apply and introduced-to-next-speaker rules). Prices are OpenRouter list prices per 1M tokens (in/out).

## Names: model comparison

| model | precision | recall | false-name items (negatives with any name) | wrong names / predictions | wrong auto-applied | latency (all calls) | cost |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | 100% (38/38) | 100% (38/38) | 0% (0/23) | 0% (0/38) | 0 | 1.32s median, 2.24s p90, 100% within 4s, 0 failed | $0.0215 |
| anthropic/claude-sonnet-5.5 | 100% (38/38) | 100% (38/38) | 0% (0/23) | 0% (0/38) | 0 | 1.24s median, 1.81s p90, 100% within 4s, 0 failed | $0.3422 |

Precision/recall count exact (speaker, name, kind) events. Precision counts the kind too, so a right name with the wrong kind is both a miss and a false event.

## Reply / interrupt / incomplete annotation (target utterance only)

| model | reply_to correct | interrupts correct | incomplete correct |
|---|---|---|---|
| anthropic/claude-haiku-5.5 | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| anthropic/claude-sonnet-5.5 | 100% (12/12) | 100% (12/12) | 100% (12/12) |

## Verbatim guard

- anthropic/claude-haiku-5.5: 0 violations across 144 emitted events (events carry only ids, thread labels, names present in the evidence text; utterance text never mutated, asserted per snippet).
- anthropic/claude-sonnet-5.5: 0 violations across 144 emitted events (events carry only ids, thread labels, names present in the evidence text; utterance text never mutated, asserted per snippet).
- Adversarial check (rewritten text field, unknown id, free-text thread, hallucinated name, extra catch-up field): 5/5 rejected.

## anthropic/claude-haiku-5.5

Per category (TP / gold / predicted):

- self_intro: 8/8/8 over 8 items
- multi_intro: 10/10/10 over 6 items
- introduced: 4/4/4 over 4 items
- correction: 6/6/6 over 3 items
- mention: 0/0/0 over 7 items
- negative: 0/0/0 over 12 items
- hard: 10/10/10 over 10 items

Name misses and false names:

Reply/interrupt misses:

## anthropic/claude-sonnet-5.5

Per category (TP / gold / predicted):

- self_intro: 8/8/8 over 8 items
- multi_intro: 10/10/10 over 6 items
- introduced: 4/4/4 over 4 items
- correction: 6/6/6 over 3 items
- mention: 0/0/0 over 7 items
- negative: 0/0/0 over 12 items
- hard: 10/10/10 over 10 items

Name misses and false names:

Reply/interrupt misses:

