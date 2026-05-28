# CJIS Considerations

**Status:** These are design considerations, not a compliance assessment, not a certification, and
not legal advice. ClearComm911 is pre-implementation. Any production deployment on live dispatch
traffic must be reviewed by qualified counsel and by the relevant CJIS authority before use. This
document explains how the project *thinks about* compliance and how the architecture is shaped to
support it — see [ARCHITECTURE.md](ARCHITECTURE.md) for the technical design.

---

## Why this matters here

Dispatch calls can carry sensitive information. Some of it may fall under the FBI's Criminal Justice
Information Services (CJIS) Security Policy, which governs how criminal justice information is
handled, transmitted, and stored. Because a single 911 call's audio can contain such information,
the responsible default is to treat the entire audio stream — and any transcript derived from it —
as potentially in scope, and to design accordingly.

A translation system that handles this audio therefore sits inside the area an agency's security
officer will scrutinize. Building for that from the start, rather than retrofitting it, is a core
goal of the project.

## What "CJIS compliance" actually is (and isn't)

A point worth stating plainly, because it is widely misunderstood:

- **There is no FBI "CJIS certification" for a product or vendor.** No software can be bought
  pre-stamped as "CJIS certified." Compliance is established operationally and contractually —
  through the way a system is configured and run, and through agreements (such as the CJIS Security
  Addendum) executed with the relevant state CJIS Systems Agency.
- **It is a shared responsibility.** A cloud environment may provide compliant infrastructure, but
  the entity running the application is still responsible for how data is handled on top of it.
  Using a "compliant" service does not by itself make a system compliant.
- **It extends to subprocessors.** Any service that touches unencrypted criminal justice
  information falls within the perimeter. A pipeline cannot quietly route sensitive data through a
  service that sits outside the agreed boundary.

ClearComm911's role is to be architected so that an agency *can* operate it within these
requirements — and to make the data-handling choices transparent enough that the agency's own
review is straightforward.

## The architectural lever: the network boundary

The most effective way to manage CJIS scope is to control what data leaves the agency's network.
The architecture's two-tier model (see [ARCHITECTURE.md §4](ARCHITECTURE.md)) exists largely for
this reason:

- **Keep audio in the agency network where possible.** In the production tier, speech-to-text runs
  on-premises so that raw caller audio does not leave the agency's control. Where cloud processing
  is used, the aim is for only text — not audio — to cross the boundary, over an encrypted,
  compliant channel to an appropriate government-cloud environment.
- **Make the boundary explicit and configurable.** What crosses the boundary, and to where, is a
  documented deployment decision rather than a hidden default — including a configuration in which
  audio never leaves the agency network at all.

This turns "is it compliant?" from an all-or-nothing property of a vendor into a concrete,
inspectable question about a specific deployment's data flows.

## Practices the project builds in

These follow from the policy areas most relevant to a system like this and are reflected in the
architecture and data-handling design:

- **Encryption in transit and at rest**, using appropriately validated cryptography, for any
  sensitive data the system handles.
- **Access control and accountability** — authenticated access to the dispatcher console and to
  logs, with the controls an agency expects around who can see what.
- **Audit logging** — an after-action record of translation activity (identifiers, timestamps,
  source and translated text, the model used, latency), held under the agency's control. The audit
  record is text and metadata; it is not a recording of the call.
- **No audio retention and no training on call data** — audio is processed in real time and
  discarded; call content is never used to train models.
- **Willingness to execute a CJIS Security Addendum** with an agency and its state CJIS Systems
  Agency for production deployments.

## The pilot vs. production distinction

The project deliberately separates a lower-stakes pilot from a production deployment:

- A **pilot on administrative (non-emergency) lines** is a setting where the data classification may
  differ and where the system can be validated without first solving every production-grade
  requirement. The appropriate classification of administrative-line audio is a question for the
  agency and its CJIS authority — not an assumption the project makes — and getting that
  determination in writing is part of standing up a pilot.
- A **production deployment on live dispatch traffic** is held to the full data-handling bar
  described above, with counsel and CJIS-authority review.

This staging lets the project build and prove the compliance-relevant machinery (encryption, audit
logging, access control, the in-boundary processing path) before it is ever pointed at live
emergency calls.

## What still requires expert review

Honestly stated, several questions are outside what software design alone can answer and require the
appropriate humans:

- Whether specific call audio (and administrative-line audio in particular) is classified as
  criminal justice information in a given jurisdiction.
- The CJIS Security Addendum and the agreements with the relevant state CJIS Systems Agency.
- Liability allocation and data-processing terms in any agency agreement.
- Final validation that a given deployment's configuration meets the current CJIS Security Policy.

ClearComm911 aims to make these reviews *easier* — through transparency, a controllable data
boundary, and built-in logging and encryption — not to substitute for them.

---

*This document will be updated as the project matures, as deployments are validated, and as the
relevant policy guidance evolves. Nothing here is legal advice.*
