# Baseline Verification Commands and Expected Outcomes

**Baseline Recorded:** 2026-10-23  
**Environment:** Windows (PowerShell), Python 3.13.9, Node 24.1.0, Docker 28.5.2  

---

## 1. Version Control & Working Tree Baseline

```powershell
git status
```
- **Exit Code:** `0`
- **Baseline Output:** `On branch master`, `No commits yet`, untracked files present.
- **Note:** Working tree contains untracked project files. Branch `master` has no prior commits.

---

## 2. `.env` Access Control Baseline (F-01)

```powershell
(Get-Acl -Path "F:\RAG\.env").Access | Select-Object IdentityReference, FileSystemRights, AccessControlType
```
- **Exit Code:** `0`
- **Baseline Output:**
  ```text
  IdentityReference FileSystemRights AccessControlType
  ----------------- ---------------- -----------------
  Everyone                        -1             Allow
  ```
- **Status:** Vulnerable (`Everyone` granted Full Control).

---

## 3. Backend Test Suite Baseline

### Unit Tests
```powershell
# Executed from F:\RAG
F:\RAG\backend\.venv\Scripts\pytest.exe backend/tests/unit
```
- **Exit Code:** `1`
- **Baseline Result:** `101 passed, 2 failed in 11.37s`
- **Failures:**
  - `test_settings_load_defaults`: Failed due to `ENABLE_DOCUMENTS=true` loaded from local `.env`.
  - `test_production_missing_jwt_secret`: Throws `SQLite database cannot be used in production environment` first because `DATABASE_URL` in local `.env` is SQLite.

### Integration Tests
```powershell
# Executed from F:\RAG\backend (required for alembic.ini relative path)
cd F:\RAG\backend
.\.venv\Scripts\pytest.exe tests/integration
```
- **Exit Code:** `0`
- **Baseline Result:** `106 passed, 0 failed in 90.5s`

---

## 4. Frontend Test Suite Baseline

```powershell
# Executed from F:\RAG\frontend
cd F:\RAG\frontend
npm test
```
- **Exit Code:** `0`
- **Baseline Result:** `7 test files passed, 45 tests passed in 33.64s`

---

## 5. Security & Build Tooling Inventory

```powershell
@('pip-audit', 'safety', 'bandit', 'semgrep', 'trivy', 'gitleaks', 'ruff', 'mypy', 'black', 'flake8', 'git', 'docker', 'npm', 'node', 'pytest') | ForEach-Object { $cmd = Get-Command $_ -ErrorAction SilentlyContinue; if ($cmd) { "$_ : $($cmd.Source)" } else { "$_ : NOT AVAILABLE" } }
```
- **Baseline Result:**
  - `pip-audit`: NOT AVAILABLE
  - `safety`: NOT AVAILABLE
  - `bandit`: NOT AVAILABLE
  - `semgrep`: NOT AVAILABLE
  - `trivy`: NOT AVAILABLE
  - `gitleaks`: NOT AVAILABLE
  - `ruff`: `C:\Users\AS\Anaconda3\Scripts\ruff.exe`
  - `mypy`: `C:\Users\AS\Anaconda3\Scripts\mypy.exe`
  - `black`: `C:\Users\AS\Anaconda3\Scripts\black.exe`
  - `flake8`: `C:\Users\AS\Anaconda3\Scripts\flake8.exe`
  - `git`: `C:\Program Files\Git\cmd\git.exe`
  - `docker`: `C:\Program Files\Docker\Docker\resources\bin\docker.exe`
  - `npm`: `C:\nvm4w\nodejs\npm.ps1`
  - `node`: `C:\nvm4w\nodejs\node.exe`
  - `pytest`: `F:\RAG\backend\.venv\Scripts\pytest.exe`
