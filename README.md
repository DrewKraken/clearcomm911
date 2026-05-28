# ClearComm911

**Real-time language translation for 911 dispatch.**

---

## The Problem

When a non-English speaker calls 911, most dispatch centers have one option: put the caller on hold, dial a third-party interpreter service, and attempt a three-way conversation while the incident unfolds. It is slow. It is awkward. In a fast-moving emergency, it costs time that matters.

Language barriers in 911 are not an edge case. They are a daily operational reality for PSAPs across the country, and the current standard of care is not good enough.

## What ClearComm911 Does

ClearComm911 provides real-time, two-way language translation for 911 and administrative dispatch calls. A non-English speaking caller is understood immediately. The dispatcher sees a live English transcript of what the caller is saying. The dispatcher's response is translated back and delivered to the caller in their language. No hold. No interpreter line. No three-way fumble.

Both parties speak their own language. The call moves forward.

## Status

Early planning and architecture phase. First implementation targeting controlled pilot on administrative lines at a real PSAP.

Architecture documentation and CJIS compliance considerations are published in [`docs/`](docs/) — see [**Architecture**](docs/ARCHITECTURE.md) and [**CJIS Considerations**](docs/CJIS-CONSIDERATIONS.md). These describe the intended design and the reasoning behind it, ahead of implementation.

## Background

ClearComm911 is built by a DOCJT-certified former 911 telecommunicator with six years deploying mission-critical communications infrastructure for public safety, utility, and federal customers. This is not a solution designed from the outside looking in.

## Data Handling & Privacy

ClearComm911 is designed around the principle that the agency owns its data and that sensitive call content should leave the PSAP network only when, and only as far as, an agency explicitly permits. These commitments guide the architecture:

- **No retention of caller audio.** Audio is processed in real time and is not stored after the session. Any audit logging captures transcript and translation metadata, not recorded audio, and remains under the agency's control.
- **No training on customer data.** Caller audio, transcripts, and translations are never used to train models.
- **Network-boundary awareness.** The architecture is explicitly designed so that what data crosses the PSAP network boundary — and to which processor — is a deliberate, documented configuration choice, including a path where audio never leaves the agency network.
- **CJIS posture.** We treat CJIS Security Policy alignment as a first-class requirement and are willing to execute a CJIS Security Addendum with agencies and their state CJIS Systems Agency for production deployments.

Nothing in this section is legal advice or a compliance certification.

## Roadmap

- [x] Architecture and stack documentation
- [x] CJIS compliance considerations doc
- [ ] v0.1 prototype: inbound STT + English transcript display
- [ ] v0.2: outbound TTS translation back to caller
- [ ] Admin line pilot at partner PSAP
- [ ] Public release

## Contributing

ClearComm911 is open source under the Apache License 2.0. Contribution guidelines will be published alongside the first implementation. If you work in public safety, dispatch, or PSAP technology and want to be involved early, open an issue or reach out directly.

## Contact

Drew Swanigan — [drewswanigan.dev](https://drewswanigan.dev) — drew.swanigan@gmail.com
