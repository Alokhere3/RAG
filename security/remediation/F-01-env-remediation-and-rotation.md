# F-01 Remediation: `.env` Access Control and Secret Rotation Assessment

**Target:** `F:\RAG\.env`  
**Date:** 2026-10-23  
**Status:** **REMEDIATED**  

---

## 1. Access Control Analysis & Remediation

### Prior Insecure Baseline
- **Observed ACL:** `Everyone` had `FileSystemRights: -1` (`FullControl`), `AccessControlType: Allow`.
- **Parent Directory:** `F:\RAG` also inherited or was configured with `Everyone: FullControl`.
- **Exposure Risk:** Any local unauthenticated process or standard user on the host system could read live database credentials, JWT secrets, and external provider API keys.

### Remediation Action
1. Disabled inheritance on `F:\RAG\.env`.
2. Purged broad public identities (`Everyone`, `Authenticated Users`, `BUILTIN\Users`).
3. Set exclusive explicit access rules granting `FullControl` solely to:
   - Current authenticated operator (`$env:USERDOMAIN\$env:USERNAME` / `as\as`)
   - `BUILTIN\Administrators`
   - `NT AUTHORITY\SYSTEM`
4. Provided automated hardening script: `deployment/scripts/harden_env_acl.ps1`.
5. Provided non-secret automated verification script: `deployment/scripts/verify_env_security.ps1`.

---

## 2. Git Tracking and Ignore Verification

- **Git Status:** `.env` is covered by root `.gitignore` (`.env`, `.env.*`).
- **`git ls-files .env`:** Exited with non-zero status (file is **NOT tracked** in version control).
- **Public Template:** `.env.example` contains only safe placeholder templates with no sensitive defaults.

---

## 3. Credential-by-Credential Rotation Checklist

Because the `.env` file on host previously had `Everyone` read permissions, all live secrets stored within it must be rotated in their respective provider consoles / managers before production launch.

| Parameter Key | Category | Exposure Severity | Rotation Procedure | Required Action |
| :--- | :--- | :--- | :--- | :--- |
| `POSTGRES_PASSWORD` | Database | HIGH | Update in PostgreSQL cluster/RDS and in deployment secret store. | Rotate before staging/prod release. |
| `DATABASE_URL` | Database | HIGH | Re-generate connection string with new password and update deployment. | Rotate before staging/prod release. |
| `REDIS_URL` | Cache/Broker | MEDIUM | If password-protected or external, rotate auth credentials. | Rotate before staging/prod release. |
| `JWT_SECRET` | Auth Signing | HIGH | Generate new 64-char cryptographically secure random string; update config. Invalidates existing tokens. | Rotate immediately. |
| `OPENAI_API_KEY` | External LLM | HIGH | Revoke key in OpenAI platform dashboard; mint new scoped project key. | Rotate immediately. |
| `GEMINI_API_KEY` | External LLM | HIGH | Revoke key in Google AI Studio / GCP IAM; mint new key. | Rotate immediately. |
| `STORAGE_BUCKET` | Cloud Storage | LOW | If S3/GCS IAM keys are associated, rotate cloud IAM secret keys. | Verify IAM access controls. |
| `APP_ENV` | Application | NONE | Non-sensitive configuration parameter. | None. |
| `PORT` / `HOST` | Networking | NONE | Non-sensitive configuration parameter. | None. |
| `ORGANIZATION_*` | White-Label | NONE | Non-sensitive branding information. | None. |
| `ASSISTANT_*` | Persona | NONE | Non-sensitive branding information. | None. |
| `PRIMARY_COLOR` | Theme | NONE | Non-sensitive branding information. | None. |

---

## 4. Verification Command & Evidence

To verify `.env` security non-secretly at any time, run:
```powershell
powershell -ExecutionPolicy Bypass -File deployment/scripts/verify_env_security.ps1
```
The script confirms:
- Exit code `0` on success.
- `.env` is NOT tracked in Git.
- Broad principals (`Everyone`) are absent from the ACL.
- Redacted table of authorized identities is output without disclosing secret values.
