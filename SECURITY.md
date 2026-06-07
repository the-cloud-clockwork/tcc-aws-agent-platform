# Security Policy

## Supported Versions

The project follows a rolling-release model on the `main` branch. Only the
latest published version receives security fixes.

| Version | Supported |
| ------- | --------- |
| Latest (`main`) | Yes |
| Older tags / pinned releases | No — upgrade to the latest release |

> If you need a specific version range to be supported, open a discussion so
> the maintainers can assess feasibility.

## Reporting a Vulnerability

**Please do not open a public GitHub issue, pull request, or discussion to
report a security vulnerability.** Public disclosure before a fix is available
puts all users at risk.

### Preferred: GitHub Private Vulnerability Reporting

Use GitHub's built-in private advisory workflow:

**[Submit a private security advisory](https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform/security/advisories/new)**

This keeps the report confidential, lets the maintainers collaborate with you
on a fix, and produces a coordinated CVE disclosure when a patch is ready.

### Secondary: GitHub Discussions (private message)

If you cannot use the GitHub advisory form, open a
[GitHub Discussion](https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform/discussions)
marked **Security** and flag it as sensitive in the body. A maintainer will
move the conversation to a private channel within one business day.

## What to Include in Your Report

A useful report helps us triage and reproduce quickly. Please include:

- **Component** — which module, file, or feature is affected (`core/`, a
  specific Terraform module, a blueprint field, etc.)
- **Description** — a clear explanation of the vulnerability and its potential
  impact
- **Steps to reproduce** — the minimal configuration or code path that
  triggers the issue
- **Environment** — Python version, Terraform version, AWS region, any
  relevant blueprint settings
- **Suggested severity** — your assessment (Critical / High / Medium / Low)
  based on impact and exploitability
- **Proof of concept** (optional but appreciated) — a script, payload, or
  configuration snippet that demonstrates the issue

## What NOT to Include

**Never paste real secrets, credentials, API keys, tokens, AWS account IDs,
or private configuration values into a security report, GitHub issue, or pull
request.** Redact or replace them with clearly-marked placeholders (e.g.
`REDACTED`, `<your-api-key>`). Credentials shared in issues or PRs are
immediately public and cannot be unseen.

If an active credential was exposed as part of the vulnerability, rotate it
immediately and note that rotation has occurred in your report.

## Expected Response Timeline

| Milestone | Target |
| --------- | ------ |
| Acknowledgment of receipt | 3 business days |
| Initial triage and severity assessment | 7 business days |
| Fix or mitigation available | Varies by severity — Critical: best effort within 14 days; High: 30 days; Medium/Low: next scheduled release |
| Public disclosure / CVE assignment | Coordinated with reporter after fix is available |

These are targets, not guarantees. Complex vulnerabilities or issues affecting
upstream dependencies may take longer. We will keep you informed throughout
the process.

## Disclosure Policy

This project follows **coordinated disclosure**. We ask that you:

1. Give us a reasonable window (see table above) to develop and release a fix
   before any public disclosure.
2. Avoid actively exploiting the vulnerability against production systems or
   user data.
3. Avoid sharing details of the vulnerability with others until a fix is
   released.

In return, we will:

- Acknowledge your contribution in the security advisory (unless you prefer
  to remain anonymous).
- Work with you to understand and validate the issue.
- Keep you informed of progress toward a fix and the planned disclosure date.

## Scope

Reports are in scope for:

- The Python runtime and SDK integration code (`core/`, `artifacts/`,
  `prompts/`, `cli/`)
- Terraform modules (`modules/`) — including IAM policy scope, KMS key
  usage, and networking configurations
- Blueprint schema parsing and validation
- Dependency vulnerabilities in packages this project pins or vendors

Out of scope:

- Vulnerabilities in AWS services themselves (report those to
  [AWS Security](https://aws.amazon.com/security/vulnerability-reporting/))
- Issues in third-party upstream libraries where a fix must come from the
  upstream maintainer (we will still appreciate the heads-up and will update
  the dependency once upstream publishes a fix)
- Findings from automated scanners with no accompanying proof of exploitability

## Thank You

Security research is a public good. We appreciate responsible disclosure and
the effort required to find and report issues carefully.
