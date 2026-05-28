# ClearComm911 Architecture

**Status:** Pre-implementation. This document describes the intended architecture and the
reasoning behind it. It will evolve as the first versions are built and validated against real
dispatch audio. Component selections noted here are current candidate defaults, not commitments —
the system is deliberately designed so they can change without rewrites.

> This document is engineering design, not legal advice or a compliance certification. For the
> compliance posture specifically, see [CJIS-CONSIDERATIONS.md](CJIS-CONSIDERATIONS.md).

---

## 1. The problem, stated precisely

When a caller with limited English proficiency reaches a 911 or administrative dispatch line, the
common path today is: place the caller on hold, conference in a third-party interpreter, and
conduct the call three ways. It works, but it costs time and clarity at the exact moment both are
most scarce. The need is not occasional — roughly one in twelve U.S. residents speaks English less
than "very well," and language access during emergencies is a standing legal obligation for
agencies that receive federal funding.

ClearComm911 narrows that gap: transcribe the caller in real time, translate it for the
dispatcher, and translate and voice the dispatcher's response back to the caller — without a hold
and without removing the human dispatcher from control of the call.

This is life-safety software. The architecture is organized around two facts that follow from
that: **a translation error can cause harm**, and **the data on these calls is sensitive and
belongs to the agency**. Every significant decision below traces back to one of those two facts.

---

## 2. Design principles

1. **Data-boundary first.** The single most important question for any component is *what data
   crosses the agency's network boundary, and to where*. This determines what is permissible, not
   just what is convenient. See §4.
2. **Provider-agnostic by construction.** Speech-to-text, translation, and speech synthesis sit
   behind narrow interfaces. Swapping a cloud provider for an on-premises model is a configuration
   and deployment change, not a code rewrite. See §5.
3. **Safety over fluency.** The translation shown to a dispatcher and spoken to a caller must be
   faithful and predictable before it is eloquent. The system favors deterministic translation on
   the critical path and keeps a human in the loop. See §6.
4. **Stream everything.** Emergency conversation is turn-based and time-sensitive. Audio,
   transcription, and translation are processed incrementally; nothing waits for a full recording.
   See §7.
5. **Degrade without dropping the call.** The voice path between caller and dispatcher must never
   depend on the translation pipeline staying up. If any AI component fails, the call survives and
   the system falls back gracefully. See §11.
6. **Open and auditable.** The pipeline is open source so agencies and reviewers can see exactly
   how calls are handled, and every translation decision is logged for after-action review.

---

## 3. System overview

ClearComm911 is a streaming pipeline that sits alongside an existing phone system. It does not
replace call handling; it observes a call's audio and provides a translated channel between the
two parties.

The conversation has two directions, with different requirements:

**Caller → dispatcher (the critical path).** This is where speed and faithfulness matter most. The
dispatcher must understand the caller quickly and accurately.

```
Caller audio ─▶ Voice activity detection ─▶ Speech-to-text ─▶ Translation ─▶ Dispatcher display
                                                                   │
                                                                   └─▶ Audit log
```

**Dispatcher → caller (the return path).** The dispatcher speaks or types a response, which is
translated and voiced back to the caller.

```
Dispatcher speech/text ─▶ Translation ─▶ Speech synthesis ─▶ Caller audio
```

A browser-based dispatcher console renders the live transcript — interim results as they stream,
committed results once stable — alongside controls for the return path and clear status when any
component is degraded.

---

## 4. The PSAP network data boundary

The organizing principle of the architecture is the boundary of the agency's (PSAP's) controlled
network. Caller audio and its transcript may contain personal and sensitive information. Where that
data is processed — inside the agency network, or in a cloud service, and if so which one — is the
decision everything else hangs on.

Rather than pick one answer, the architecture supports **two deployment tiers** that share the same
code and interfaces and differ only in where processing happens:

| | **Pilot tier** | **Production tier** |
|---|---|---|
| **Context** | Administrative (non-emergency) lines, controlled testing | Live dispatch lines |
| **Audio handling** | Audio may transit vetted cloud services | Audio stays within the agency network where possible; only text crosses the boundary, over a compliant channel |
| **Processing** | Cloud speech-to-text / translation / synthesis | On-premises speech-to-text; on-premises or government-cloud translation and synthesis |
| **Goal** | Validate the pipeline and the dispatcher experience quickly | Meet the data-handling bar required for live emergency traffic |

The pilot tier exists to learn fast on lower-stakes traffic. The production tier is what an agency
can actually run on live calls. Treating these as one architecture — same interfaces, swappable
implementations — is what lets the project move quickly without designing itself into a corner.

---

## 5. Component architecture

The pipeline is composed behind three core interfaces and a telephony transport. Each interface
has multiple implementations (cloud and self-hosted); the active one is chosen by configuration.

- **`Transcriber`** — streaming speech-to-text. Input: audio frames. Output: interim and final
  transcript segments with timing and a language tag.
- **`Translator`** — text translation. Input: a transcript segment and a direction (e.g. ES→EN).
  Output: a translated segment. Implementations may support a glossary for addresses and
  domain terms.
- **`Synthesizer`** — streaming text-to-speech. Input: text and a target voice/language. Output:
  audio frames suitable for telephony.
- **Telephony transport** — delivers call audio in and out of the pipeline bidirectionally, and is
  responsible for the codec/sample-rate handling that phone audio requires.

These are orchestrated by a streaming pipeline framework that handles frame routing, interruption
handling, and provider integrations, so ClearComm911's own code stays focused on the dispatch
domain rather than on transport plumbing.

Because the contracts are narrow, a deployment can mix and match: a cloud transcriber for a pilot,
an on-premises transcriber for production, the same translation interface in front of either a
cloud service or a locally hosted model. Adding a provider means writing one adapter, not touching
the pipeline.

---

## 6. Translation safety model

This is the part of the architecture most specific to life-safety use, and the part where being
careful matters more than being clever.

**Deterministic machine translation is the authoritative path.** The translation a dispatcher acts
on, and any translation voiced back to a caller, comes from a translation model whose behavior is
consistent and reviewable. This is the text that drives the spoken output. Faithfulness and
predictability are the priority on this path.

**Large language models, if used, are display-only context — never the spoken output.** An LLM can
add helpful context for ambiguous or fragmented speech, but it can also rephrase, soften, or omit
in ways that are unacceptable when a "not" dropped from "not breathing" changes the meaning. Any
such assistance is clearly labeled as context for the dispatcher to weigh, is visually separated
from the authoritative translation, and is architecturally prevented from reaching the
speech-synthesis path. This separation is enforced in the pipeline structure, not by convention.

**Addresses and critical details get explicit confirmation.** Locations, names, and numbers are the
highest-risk content in a dispatch call. The console surfaces translated addresses for the
dispatcher to confirm by read-back before they are relied upon.

**A human interpreter remains the backstop.** ClearComm911 assists the dispatcher; it does not
remove the option of a human interpreter. For any call where the stakes or the uncertainty warrant
it, escalation to a human interpreter remains available and is part of the operating procedure, not
an afterthought.

---

## 7. Latency budget

Targets are expressed per direction, because the two paths have different tolerances. These are
design targets to validate against real telephony audio, not measured results.

| Path | Target | Notes |
|---|---|---|
| Caller → dispatcher, interim text on screen | ~½ second | Dispatcher sees the caller's words forming in near real time |
| Caller → dispatcher, committed translation | ~1–1.5 seconds | Stable translated segment the dispatcher can act on |
| Dispatcher → caller, audio begins | ~2 seconds | From dispatcher input to the caller hearing the response |

The streaming design exists to hit these. Interim transcript is shown to the dispatcher
immediately; translation is triggered on stable segment boundaries rather than on every partial, to
avoid translations that flicker and rewrite themselves. The achievable numbers differ between the
two deployment tiers — on-premises models trade some latency for keeping audio inside the agency
network — and the architecture treats that trade-off as an explicit, documented choice rather than
hiding it.

---

## 8. Candidate stack

The following are current candidate defaults, recorded for transparency. They sit behind the
interfaces in §5 and are expected to change as the project validates them against real audio and as
agencies' requirements dictate. **Naming them is not an endorsement or a commitment** — it is a
starting point that any deployment can override.

| Layer | Pilot tier (cloud) | Production tier (in-boundary) |
|---|---|---|
| Telephony transport | Cloud voice API with bidirectional media streaming | Standards-based call recording feed (SIPREC) from the agency's session border controller |
| Voice activity detection | Local, on-device | Local, on-device |
| Speech-to-text | Streaming cloud model | Self-hosted models (per-language) |
| Translation (authoritative) | Cloud translation service with glossary support | Self-hosted open-license translation model, or government-cloud translation |
| Translation (context, display-only) | Cloud LLM, isolated from the spoken path | Optional; same isolation |
| Speech synthesis | Low-latency streaming cloud voice | Self-hosted open-license voice |
| Orchestration | Streaming pipeline framework (same in both tiers) | Same framework, different adapters |
| Dispatcher console | Browser app over a streaming connection | Same |

A guiding constraint: self-hosted model choices must carry licenses compatible with use by public
agencies. Models with non-commercial-only licenses are not eligible for production, regardless of
quality.

---

## 9. Audio capture and integration

ClearComm911 is designed to run *alongside* existing dispatch infrastructure, not in place of it.
Two integration mechanisms correspond to the two tiers:

- **Pilot:** a dedicated number on a cloud voice platform bridges the call and streams its audio to
  the pipeline. This requires no change to the agency's call-handling system and can be stood up
  for controlled testing on administrative lines quickly.
- **Production:** a standards-based recording feed (SIPREC) from the agency's session border
  controller delivers call audio passively, the same mechanism agency logging recorders already
  use. This positions ClearComm911 as a recognized category of integration that agencies know how
  to authorize, with no disruption to the call path.

**Open design question (honestly flagged):** the passive recording feed delivers audio *to* the
pipeline but does not, by itself, provide a path to inject synthesized audio *back* into a live
call. The return (dispatcher → caller voice) path in a production deployment therefore depends on an
additional mechanism — for example a conference bridge — that must be designed with the agency's
telephony environment. The first version sidesteps this entirely by scoping to the inbound
direction only (see §12).

---

## 10. Data handling, logging, and retention

- **No retention of caller audio.** Audio is processed in real time and not stored after the
  session.
- **No training on call data.** Caller audio, transcripts, and translations are never used to train
  models.
- **Audit logging is text and metadata, not audio.** For each translated segment the system records
  identifiers, timestamps, source and translated text, the provider/model used, and measured
  latency — the record needed for after-action review and quality assurance, held under the
  agency's control.
- **The boundary is configurable and documented.** What leaves the agency network, and to which
  service, is an explicit deployment decision (see §4), including a configuration where audio never
  leaves the agency network.

These commitments are reflected in the project's public posture and detailed further in
[CJIS-CONSIDERATIONS.md](CJIS-CONSIDERATIONS.md).

---

## 11. Reliability and failure modes

Because this sits in the path of emergency communication, failure handling is a first-class concern.

- **The call is independent of the pipeline.** The voice connection between caller and dispatcher
  does not route through, or depend on, the AI components. If the pipeline degrades or fails, the
  call continues; the system loses translation, not the call.
- **Each provider has a fallback.** Translation and other stages are wrapped so that a provider
  timeout or error fails over to an alternate, or, failing that, surfaces the raw transcript with a
  clear "translation unavailable" indicator rather than presenting nothing or — worse — something
  misleading.
- **Degradation is visible.** The dispatcher console always communicates the current health of each
  stage, so a dispatcher is never misled about whether the translation they see is trustworthy.

---

## 12. Versioned scope

The project is built in deliberate increments, each independently useful and verifiable.

- **v0.1 — Inbound path.** Caller speech → live English transcript on the dispatcher console, with
  audit logging and graceful fallback. No voice back to the caller yet. This validates the core
  value and the latency targets before taking on the return-path complexity.
- **v0.2 — Two-way loop.** Dispatcher response → translation → voice back to the caller, with
  interruption handling and the address-confirmation workflow.
- **Beyond.** In-boundary/production deployment via the standards-based recording feed,
  per-language model expansion, and the operational tooling agencies need to run it on live traffic.

Spanish is the first supported language, reflecting where the need is largest; additional languages
follow.

---

## 13. Open questions

Recorded honestly, because a credible architecture names what it has not yet resolved:

- **On-premises latency vs. targets.** Keeping speech-to-text inside the agency network (production
  tier) is the stronger data-handling posture but adds latency relative to the §7 targets. The
  acceptable trade-off needs measurement on real telephony audio and an explicit decision.
- **Return-path audio in production.** The mechanism for voicing the dispatcher's response back into
  a live call under the passive-recording integration (§9) is unresolved and will be designed with a
  pilot agency's telephony environment.
- **Single-environment processing for production.** When any cloud processing is used on live
  traffic, keeping it within one compliant environment is cleaner than spanning multiple services;
  the production configuration should reflect that.
- **Per-language model quality.** Self-hosted model quality varies by language and by the realities
  of narrowband phone audio; each added language needs validation rather than assumption.

These are tracked and will be resolved with measurement and with the input of partner agencies, not
settled prematurely on paper.
