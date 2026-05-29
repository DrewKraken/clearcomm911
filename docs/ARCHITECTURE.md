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

**Dispatcher → caller (the return path).** The dispatcher's response is translated for the caller.
This direction supports two modes, chosen per deployment (see §9):

```
Dispatcher input ─▶ Translation ─┬▶ on-screen reply + pronunciation guide (dispatcher voices it)
                                 └▶ speech synthesis ─▶ caller audio (system voices it)
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

### Two deployment profiles

Where production processing happens is not a single answer — it is a per-agency choice, because the
market is genuinely split. Some agencies are adopting cloud call-handling; others deliberately keep
infrastructure on-premises for cost or control. ClearComm911 supports both as first-class profiles,
selectable by configuration rather than by a code fork:

- **Profile A — audio stays on-premises (default).** Speech-to-text runs inside the agency network;
  caller audio never leaves it. The most defensible data-handling posture, and — because it relies
  on self-hosted models — the one with no per-call service cost.
- **Profile B — compliant cloud.** For agencies that permit audio to leave for a compliant
  government-cloud environment, cloud speech services can be used for lower latency. When any cloud
  step is used on live traffic, the pipeline stays within a **single** compliant environment rather
  than chaining services across providers (see [CJIS-CONSIDERATIONS.md](CJIS-CONSIDERATIONS.md)).

Production is therefore not synonymous with "on-premises" or with "cloud" — it is whichever profile
an agency's requirements call for, on the same codebase.

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

**Calibrated honesty is the governing principle.** No system is ever perfectly accurate — not
deterministic machine translation, not the speech-to-text beneath it, not even a live human
interpreter. They all mishear and misrender sometimes. So the goal is not to promise perfect output;
that goal produces systems that hide their uncertainty in order to *look* confident. The failure
mode that costs lives is not error itself — it is **undetected error presented as certainty.**
ClearComm911 is therefore designed to never present information to a dispatcher as more certain than
it is: where it is confident, it shows that plainly; where it is not, it flags it; critical details
get explicit verification; the caller's original words are always available as ground truth; and a
human interpreter is always one escalation away.

**Deterministic machine translation is the authoritative path.** The translation a dispatcher acts
on, and any translation voiced back to a caller, comes from a translation model whose behavior is
consistent and reviewable. This is the text that drives any spoken output. Faithfulness and
predictability are the priority on this path.

**Large language models, if used, are display-only context — never the authoritative or spoken
output.** An LLM can add helpful context for ambiguous or fragmented speech, but it can also
rephrase, soften, or omit in ways that are unacceptable when a "not" dropped from "not breathing"
changes the meaning. Any such assistance is clearly labeled as context, visually separated from the
authoritative translation, never auto-populated into the dispatcher's outgoing message, and
architecturally prevented from reaching the speech-synthesis path. This separation is enforced in
the structure of the pipeline — not by policy or by a comment.

**Uncertainty is surfaced, not smoothed over.** Low-confidence transcription and translation
segments are visually flagged rather than rendered as silent, confident guesses. Critical content —
weapons, addresses, numbers, names, medical terms — is identified and surfaced prominently, and
numbers and proper nouns are preserved as literally as possible to shrink the surface that
translation can corrupt. When confidence is low or a component fails, the console shows "uncertain"
or "unavailable" rather than a confident-looking wrong answer.

**The design reinforces how dispatchers already work.** Trained call-takers already confirm critical
details by reading them back — "okay, what's happening at 123 Lane Drive?" That repeat-back is
established life-safety practice, and ClearComm911 leans on it rather than replacing it: translated
addresses and other critical entities are surfaced for read-back before they are relied upon. This
adds no new habit for the dispatcher, and it does double duty — the same read-back that confirms the
detail with the caller is also what catches a mistranscription, because the caller hears it and can
correct it.

**A human interpreter remains the backstop.** ClearComm911 assists the dispatcher; it does not
remove the option of a human interpreter. For any call where the stakes or the uncertainty warrant
it, escalation to a human interpreter remains available and is part of the operating procedure, not
an afterthought.

---

## 7. Latency budget

The governing principle is simple: be **dramatically faster than the status quo** it replaces — a
third-party interpreter conference, which typically costs 40 seconds or more just to connect — and,
above that floor, aim for conversational pacing. Equally important, the system **never waits
silently**: if a turn exceeds its ceiling, the dispatcher sees a visible "working…" state, never a
frozen screen.

Targets differ by deployment profile, because on-premises models trade some latency for keeping
audio inside the agency network — an explicit, documented trade-off, not a hidden one. These are
design targets to validate against real 8 kHz telephony audio, not measured results or promises.

| Path | Cloud profile | On-premises profile | Ceiling |
|---|---|---|---|
| Caller → dispatcher, interim text | ≤ 0.5 s | ≤ 1.5 s | — |
| Caller → dispatcher, committed translation | ≤ 1.5 s | ≤ 2.5 s | beyond 3 s → show "working…", treat as degraded |
| Dispatcher → caller, audio begins | ≤ 2 s | ≤ 3 s | — |

The streaming design exists to hit these. Interim transcript is shown to the dispatcher
immediately; translation is triggered on stable segment boundaries rather than on every partial, to
avoid translations that flicker and rewrite themselves. The on-premises numbers in particular will
be finalized only after measurement on real telephony audio.

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

### Getting the dispatcher's response to the caller

Hearing the caller is solved the same way in every deployment. Voicing the dispatcher's response
back is where deployments differ, because a passive recording feed delivers audio *to* the pipeline
but cannot, by design, inject audio *back* into a live call — that passivity is exactly what makes it
non-invasive and easy to authorize. The return direction therefore has two modes:

- **Coached response.** The system shows the dispatcher the translated reply as text with
  pronunciation guidance, and the dispatcher voices it to the caller over the call they are already
  on. This needs no audio injection at all, works in every deployment including a passive recording
  feed, and adds no risk to the call. It is well suited to languages a dispatcher can reasonably
  pronounce.
- **Direct voiced translation.** The system synthesizes the translated reply and plays it to the
  caller directly. This is more natural and scales to languages a dispatcher cannot pronounce, but it
  requires ClearComm911 to be in the call's media path (a bridge), designed so that a failure on our
  side can never drop the call.

Which mode a deployment uses depends on its telephony environment and the languages it serves. The
direct-voiced path in a passive-feed production deployment is the one genuinely
partner-dependent piece, and it is designed together with the first production agency rather than
assumed on paper. The pilot, which already bridges the call, can demonstrate the full two-way loop
before that production case is solved — and the first version sidesteps the question entirely by
scoping to the inbound direction only (see §12).

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

The architecture is language-agnostic — the transcription, translation, and synthesis interfaces are
parameterized by language, and adding one is a configuration and model change, not a redesign.
Spanish is the first supported language because the need is largest there (the majority of limited-
English-proficiency residents), not because anything is built around it; additional languages follow
and each is validated on its own. The return-mode choice in §9 is coupled to this: coached response
fits languages a dispatcher can pronounce, while harder-to-pronounce languages lean on direct voiced
translation.

---

## 13. Open questions

Recorded honestly, because a credible architecture names what it has not yet resolved:

- **On-premises latency, exact numbers.** The §7 targets are set, but the on-premises figures depend
  on how self-hosted models behave on real narrowband telephony audio. They will be confirmed by
  measurement, not assumed.
- **Direct voiced translation in a passive-feed production deployment.** The two return modes are
  defined (§9), but injecting synthesized audio into a live call under a passive recording feed is
  partner-dependent and will be designed with the first production agency's telephony environment.
- **Per-language model quality.** Self-hosted model quality varies by language and by the realities
  of narrowband phone audio; each added language is validated rather than assumed.
- **Language selection.** Whether the system auto-detects the caller's language or the dispatcher
  selects it is an open user-experience question, likely resolved with input from working
  dispatchers.

These are tracked and will be resolved with measurement and with the input of partner agencies, not
settled prematurely on paper.
