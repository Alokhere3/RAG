#!/usr/bin/env python3
"""Pre-flight Deployment and Production Configuration Validator.

Verifies that the target environment satisfies all security and operational
requirements prior to spinning up production containers or serving live traffic.
"""

import os
from pathlib import Path
import sys

# Ensure backend modules can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


def validate_production_readiness() -> bool:
    """Validate all production prerequisites."""
    print("=" * 60)
    print(" RAG Platform - Production Pre-flight Validation")
    print("=" * 60)

    errors = []
    warnings = []

    # 1. Environment and Debug Mode
    app_env = os.environ.get("APP_ENV", "development").lower()
    debug_mode = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

    print(f"[*] APP_ENV: {app_env}")
    print(f"[*] DEBUG:   {debug_mode}")

    if app_env == "production" and debug_mode:
        errors.append("P001: DEBUG must be set to 'false' in production.")

    # 2. JWT Secret Validation
    jwt_secret = os.environ.get("JWT_SECRET", "").strip()
    if app_env == "production":
        if not jwt_secret:
            errors.append("P002: JWT_SECRET must be set and non-empty in production.")
        elif len(jwt_secret) < 32:
            errors.append(f"P002: JWT_SECRET must be at least 32 characters (current: {len(jwt_secret)}).")
        elif "replace-with" in jwt_secret or "secret" == jwt_secret:
            errors.append("P002: Insecure placeholder JWT_SECRET detected.")
        else:
            print("[+] JWT_SECRET meets entropy requirements (>=32 chars).")

    # 3. CORS Policy
    cors = os.environ.get("CORS_ORIGINS", "")
    if app_env == "production":
        if "*" in cors:
            errors.append("P003: Wildcard CORS ('*') is prohibited in production.")
        elif not cors:
            warnings.append("CORS_ORIGINS is empty; no browser cross-origin requests will be accepted.")
        else:
            print(f"[+] CORS_ORIGINS configured explicitly: {cors}")

    # 4. Database Configuration
    db_url = os.environ.get("DATABASE_URL", "")
    if app_env == "production":
        if not db_url or "sqlite" in db_url:
            errors.append("P004: Production database must be PostgreSQL (sqlite prohibited).")
        else:
            print("[+] PostgreSQL database configuration detected.")

    # 5. Storage Directory Permissions
    storage_dir = Path(os.environ.get("STORAGE_DIR", "./data/storage")).resolve()
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        test_file = storage_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        print(f"[+] Storage directory writable: {storage_dir}")
    except Exception as e:
        errors.append(f"Storage path {storage_dir} is not writable: {e}")

    # Print Summary
    print("-" * 60)
    if warnings:
        print("[!] Warnings:")
        for w in warnings:
            print(f"    - {w}")

    if errors:
        print("[-] Pre-flight Validation FAILED with errors:")
        for e in errors:
            print(f"    [X] {e}")
        print("=" * 60)
        return False

    print("[+] All production pre-flight checks PASSED.")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = validate_production_readiness()
    sys.exit(0 if success else 1)
