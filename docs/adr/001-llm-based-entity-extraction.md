# ADR 001: Use LLM-based entity extraction (not GLiNER2.5) for workshop modules 1–4

- **Status:** Accepted
- **Date:** 2026-10-27
- **Context:** Workshop outline v1 (WORKSHOP_OUTLINE.md) — Module 3 entity extraction
- **Supersedes:** the GLiNER2.5-based extraction design in outline v1 (as amended through the hybrid-pipeline revision)

## Context

The workshop's Module 3 (Long-Term Memory) needs entity + typed-relation extraction from
customer-support conversations on the **Bolt backend** (attendee's own AuraDB), where
extraction runs **client-side, synchronously inside `add_message`**. Attendees run the
full-stack app from **GitHub Codespaces** (default machine: 2 cores / 4 GB RAM) or a
local clone. The workshop is a 2-hour live, run-and-explore session; OpenAI is already
required for chat + embeddings (`text-embedding-3-small`).

Two extraction options are supported by `neo4j-agent-memory`:

1. **GLiNER2.5 (local)** — `extractor_type="gliner2"`: local JointIE model
   (`fastino/gliner2.5-base-v1`, ~407 MB checkpoint; torch/transformers runtime), joint
   entity + relation decoding, opt-in enum-property attribute pass
   (`gliner_extract_attributes`).
2. **LLM-based** — `extractor_type="llm"`: `LLMEntityExtractor` with a provider
   (`MemorySettings.llm="openai/gpt-4o-mini"`), default **temperature 0.0**, using
   `StructuredExtractor.complete_structured` (native structured outputs) on providers
   that support it. The ontology is rendered into the extraction prompt
   (`prompt_fragment`: entity types with annotation-guideline descriptions, legal
   relationship patterns); relations the ontology doesn't permit are dropped at ingest.

Additional constraints from the adversarial review (REVIEW_FEEDBACK.md) informed this
decision: GLiNER's 407 MB download for local-clone attendees (G2), unchoreographed model
cold-start dead air (G11), synchronous CPU inference latency on the per-turn critical
path in a 2-core container (F8), checkpoint/threshold sensitivity and the ~400-word
window-split failure mode (F10), and devcontainer image bloat affecting Codespaces
prebuild reliability (contributes to A3).

Both extractors produce only *structure* — neither fills entity `description` or
`attributes` (GLiNER's JointIE schema carries no node properties beyond enum recovery;
the LLM's `EntityPayload` deliberately excludes them). Rich, multi-property entities
therefore come from the hybrid pipeline regardless of extractor choice: structure from
the extractor, grounded facts from SQLite hydration, external knowledge from Wikipedia
enrichment.

## Decision

**Use LLM-based extraction** where extraction is enabled (modules 3–5):

```python
MemorySettings(
    backend="bolt",
    llm="openai/gpt-4o-mini",           # chat + extraction
    extraction={"extractor_type": "llm"},
    ...
)
```

- Extraction model: same OpenAI account/key attendees already have; small,
  cheap model (gpt-4o-mini class) at **temperature 0** with structured outputs for
  lower variance; temperature zero does not guarantee identical results.
- The **custom Acme Cloud ontology still drives extraction**: entity types,
  annotation-guideline descriptions (negative cases included), aliases, and typed
  relationship patterns are rendered into the LLM prompt; forbidden relations are
  dropped by ingest-time validation.
- **Business attributes — including categorical values (`plan`, `signup_date`) —
  come from SQLite hydration**, not from the extractor. (This replaces the GLiNER enum
  attribute pass; grounding categoricals in the system of record is strictly more
  accurate.)
- Wikimedia is a separate, explicit cached optional workflow; errors remain visible.

## Alternatives considered

| | GLiNER2.5 (local) | **LLM (chosen)** | spaCy | Pipeline (GLiNER + LLM fallback) |
|---|---|---|---|---|
| Setup footprint | 407 MB checkpoint + torch runtime in image; local-cloners download mid-workshop | None (tiny `[openai]` extra) | Small model, but no relations | Worst of both |
| Codespaces fit (2-core/4 GB) | RAM pressure + 1–5 s+ CPU inference per turn, synchronous | ~1–2 s network call, constant | Fast but label set too coarse for custom ontology | Variable |
| Cold start | Tens of seconds first load, ×3 runs in module 3 | None | Small | GLiNER path cold start |
| Determinism | Deterministic but checkpoint/threshold sensitive | temperature 0 + structured outputs ≈ near-deterministic | Deterministic | Mixed |
| Cost | Free | Fractions of a cent per message | Free | Free + LLM |
| Failure mode | Silent (`feasible=False`, window-split relations) | Loud (429s) | N/A | Mixed |
| Typed relations | Decoder-enforced endpoints (JointIE) | Prompt-guided + ingest validation | Not supported | Mixed |
| Enum properties | Opt-in attribute pass (GLiNER-only) | Not extracted — hydrated from SQLite instead | No | GLiNER-only |
| Story continuity | Local-model wow factor; philosophy switch vs. NAMS server-side extraction in module 5 | Matches NAMS server-side (LLM) extraction — one extraction philosophy across the workshop | — | — |

spaCy was rejected: fixed coarse label set, no typed relations, wrong fit for a custom
ontology. The multi-stage pipeline was rejected as unjustified complexity for a 2-hour
workshop.

## Consequences

**Positive:**
- Removes review items **G2** (407 MB local download), **G11** (GLiNER cold-start dead
  air), **F8** (synchronous CPU latency), **F10** (checkpoint pinning, threshold
  sensitivity, window-split relations), and **F2** (enum attribute pass unverified on
  the pinned release — now moot).
- Identical extraction behavior on every attendee machine (no CPU/RAM variance) —
  the whole room sees the same graph.
- Smaller devcontainer → faster, more reliable Codespaces prebuilds (helps A3).
- Module 3 sheds one concept (the attribute pass) from its over-capacity load (helps A2).
- Conceptual continuity with module 5: NAMS extracts server-side with an LLM; modules
  1–4 now use the same philosophy.
- The hybrid pipeline becomes cleaner: **LLM extracts structure, SQLite provides facts,
  Wikipedia enrichs externals** — and the "no invented facts" design principle becomes
  the module's centerpiece rather than a footnote.

**Negative / accepted risks:**
- **Whole-room OpenAI bursts** (chat + embeddings + one extraction call per turn) may
  hit tier-1 rate limits — 429s look like "broken setup" to a struggling attendee.
  Mitigation: paced, serialized scenario scripts; pre-work communicates the key/billing
  requirement and expected cost (<$1); instructor watches for 429s.
- **Per-message extraction cost** — negligible (gpt-4o-mini class, short messages) but
  nonzero; state the ballpark in pre-work.
- **Loses the "runs fully local" wow factor** — accepted; it was never the workshop's
  story.
- **Relation endpoints validated at ingest, not inside the decoder** — slightly looser
  than JointIE's beam-search enforcement; acceptable at workshop dialogue scale.

**Verification follow-ups (from REVIEW_FEEDBACK.md P0, still required):**
- Confirm on the **pinned package release** that `extractor_type="llm"` + ontology
  prompt-fragment behaves as the `main`-branch source shows (release pin: see F4).
- Benchmark end-to-end per-message latency and total scenario cost (chat + embedding +
  extraction) for one scripted scenario.

## Related

- WORKSHOP_OUTLINE.md — Module 3 (updated by this decision)
- ADR 002 — uv + Makefile tooling (lockfile pins the release verified below; scenario targets implement the rate-limit pacing)
- REVIEW_FEEDBACK.md — items G2, G11, F2, F8, F10, A2, A3
