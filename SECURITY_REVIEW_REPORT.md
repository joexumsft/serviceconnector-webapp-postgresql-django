# Security Review Report

**Repository:** `joexumsft/serviceconnector-webapp-postgresql-django`  
**Reviewed path:** `/home/runner/work/serviceconnector-webapp-postgresql-django/serviceconnector-webapp-postgresql-django`  
**Review type:** Security-focused static repository review (code + accessible git metadata)

## Executive Summary
The repository contains multiple **confirmed high-risk issues**, including hardcoded secrets, insecure Django production settings, and outdated dependencies.  
In its current state, it is **not safe to remain publicly archived without remediation**.

## Confirmed Findings

| Severity | Finding | Evidence | Risk |
|---|---|---|---|
| **High** | Hardcoded Django `SECRET_KEY` | `azuresite/settings.py:23` | Session/token signing compromise if reused in deployment |
| **High** | `DEBUG=True` in production path | `azuresite/settings.py:26`, `azuresite/production.py:7` | Sensitive error/config disclosure |
| **High** | Committed credentials/password-like values | `env.bat:4,10`, `env.sh:4`, `env.ps1:4` | Secret leakage / bad practice propagation |
| **High** | Outdated dependency pins | `requirements.txt:1-6` | Known or likely CVE exposure from EOL/old packages |
| **Medium** | Wildcard `ALLOWED_HOSTS` | `azuresite/settings.py:28` | Host header abuse risk if wrong settings module used |
| **Medium** | Missing explicit prod TLS/cookie hardening flags | `azuresite/production.py` (no secure flags present) | Weaker transport/session protection |
| **Medium** | PostgreSQL config lacks explicit SSL enforcement in active block | `azuresite/production.py:32-39` | Potential cleartext/misconfigured DB transport |
| **Medium** | README suggests broad DB firewall opening (`0.0.0.0 - 255.255.255.255`) | `README.md:95` | Excessive exposure during setup if left in place |

## Potential Concerns (Context-dependent)

1. **Infrastructure metadata leakage** in `.azure` local context files  
   - Evidence: `.azure/.local_context_xichen:5-16`, `.azure/config:2-6`  
   - Concern: Resource naming/user info can help targeted reconnaissance.

2. **No visible in-repo CI security workflows**  
   - `.github` contains templates only; no workflow files found.  
   - Concern: Missing enforced automated security checks.

## False Positives / Not Confirmed as Active Vulnerabilities

- No active SQL injection path found in runtime code; ORM usage is standard (`polls/views.py:21,37,42`).
- Raw SQL and token-fetch examples are commented out (`polls/views.py:79-95`, `azuresite/production.py:72+`).
- CSRF middleware and template token usage are present (`azuresite/settings.py:47`, `polls/templates/polls/detail.html:6`).
- Redirect usage appears internal and not open redirect (`polls/views.py:55`).

## Recommended Remediation Workflow

1. **Containment & Rotation**
   - Rotate all credentials that may have been exposed.
   - Replace all committed secret-like values with placeholders.

2. **Settings Hardening**
   - Move `SECRET_KEY` to environment/secret store.
   - Set `DEBUG=False` for production and enforce startup guard.
   - Replace wildcard `ALLOWED_HOSTS` with explicit host list.
   - Add production security settings: secure cookies, SSL redirect, HSTS, content type sniffing protections.
   - Require DB TLS explicitly (`sslmode=require`).

3. **Dependency Modernization**
   - Upgrade Django from 2.2.x to supported LTS/current secure version.
   - Upgrade `requests`, `psycopg2`, `whitenoise`, and related packages.
   - Run dependency vulnerability audit and patch high/critical issues first.

4. **Repository Hygiene**
   - Remove local context files not meant for source control.
   - Add/strengthen ignore rules for env/secret files.
   - Update README to least-privilege network/firewall guidance.

5. **Validation Pipeline**
   - Run CodeQL security analysis.
   - Enable GitHub secret scanning + push protection.
   - Run dependency review/Dependabot alerts.
   - Run full history secret scan (not only HEAD).

6. **History & Exposure Cleanup**
   - If real secrets were ever committed, perform history rewrite/scrub and force-rotate secrets.
   - Reassess public visibility after cleanup.

## Archive Decision Guidance

- **Current state:** Not safe as-is for long-term public archival.  
- **Recommended path:**  
  - **Remediate first** if repository must remain as reference/sample.  
  - **Delete or make private** if no active business/learning value remains and cleanup effort is not justified.
