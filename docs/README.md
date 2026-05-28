# ClearComm911 Documentation

Design and reference documentation for ClearComm911 — real-time language translation for 911
dispatch. The project is in its architecture phase; these documents describe the intended design
and the reasoning behind it, ahead of implementation.

## Contents

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — the system design: the translation loop, the
  agency-network data boundary that organizes every decision, the two deployment tiers, the
  provider-agnostic component interfaces, the translation safety model, the latency budget, the
  candidate stack, and the versioned scope.
- **[CJIS-CONSIDERATIONS.md](CJIS-CONSIDERATIONS.md)** — how the project approaches CJIS and the
  handling of sensitive call data, and how the architecture is shaped to support an agency's
  compliance review. Considerations, not certification or legal advice.

## A note on these documents

Component and vendor names that appear in these docs are current candidate defaults recorded for
transparency, not endorsements or commitments. The architecture is deliberately built so that
speech-to-text, translation, and speech synthesis can be swapped by configuration. Where a question
is unresolved, it is stated as open rather than papered over.
