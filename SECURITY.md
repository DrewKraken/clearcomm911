# Security Policy

ClearComm911 is intended for use in public safety environments. We take the security
and integrity of this software seriously and welcome responsible disclosure of
vulnerabilities.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues, pull
requests, or discussions.**

Report privately through either channel:

1. **GitHub Private Vulnerability Reporting** (preferred) — use the **"Report a
   vulnerability"** button under this repository's **Security** tab.
2. **Email** — drew.swanigan@gmail.com with the subject line `SECURITY: ClearComm911`.

Please include, where possible:

- A description of the vulnerability and its potential impact
- Steps to reproduce, or a proof of concept
- Affected version, commit, or component
- Any suggested remediation

## Our Commitment

- **Acknowledgment** within **48 hours** of receiving your report.
- An initial assessment and severity triage within **5 business days**.
- A remediation target of **90 days** for confirmed vulnerabilities, prioritized by
  severity. We will keep you informed of progress.
- Credit to reporters in the release notes and security advisory, unless you prefer to
  remain anonymous.

We ask that you give us a reasonable opportunity to remediate an issue before any public
disclosure, and that testing does not involve real emergency calls, live 911 traffic, or
any system carrying genuine caller data.

## Scope

Because ClearComm911 may sit in the path of life-safety communications, we are especially
interested in reports concerning:

- Confidentiality of caller audio, transcripts, and translated text (data leakage,
  unintended retention, or exposure across the PSAP network boundary)
- Integrity of translation output (anything that could cause an incorrect translation to
  be presented as authoritative or spoken to a caller)
- Authentication, authorization, and audit-log tampering
- Dependency and supply-chain vulnerabilities

## Coordinated Disclosure

Confirmed vulnerabilities will be documented through
[GitHub Security Advisories](https://docs.github.com/en/code-security/security-advisories)
with an associated CVE where appropriate.
