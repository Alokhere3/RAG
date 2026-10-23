#!/usr/bin/env python3
"""Cross-platform Backup Utility for Self-Hosted Dedicated RAG Platform.

Takes a consistent snapshot of:
1. Application Database (PostgreSQL or SQLite)
2. Uploaded Document Storage
Generates a verifiable manifest with SHA-256 checksums and creates a compressed archive.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from typing import Any, Dict


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest for a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_backup(
    output_dir: Path,
    storage_dir: Path,
    db_url: str,
    app_version: str = "0.1.0",
) -> Path:
    """Create a complete, verifiable backup archive."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    backup_id = f"rag_backup_{timestamp}"
    staging_dir = output_dir / backup_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    tarball_path = output_dir / f"{backup_id}.tar.gz"

    try:
        db_backup_file = staging_dir / "database.dump"
        db_type = "unknown"

        print(f"[*] Starting backup: {backup_id}")
        print(f"[*] Staging path: {staging_dir}")

        # 1. Database Backup
        if db_url.startswith("sqlite"):
            db_type = "sqlite"
            clean_path = db_url.split("///")[-1].split("?")[0]
            source_db = Path(clean_path).resolve()
            if not source_db.exists():
                raise FileNotFoundError(f"SQLite database file not found at: {source_db}")

            # Safe online SQLite backup
            src_conn = sqlite3.connect(str(source_db))
            dst_conn = sqlite3.connect(str(db_backup_file))
            with dst_conn:
                src_conn.backup(dst_conn)
            src_conn.close()
            dst_conn.close()
            print(f"[+] SQLite database backed up safely: {db_backup_file.name}")
        elif db_url.startswith(("postgresql", "postgres")):
            db_type = "postgresql"
            pg_dump_bin = shutil.which("pg_dump")
            if not pg_dump_bin:
                raise RuntimeError(
                    "Required PostgreSQL backup utility 'pg_dump' is not installed or not in system PATH."
                )
            cmd = [pg_dump_bin, "--dbname", db_url, "--format=custom", "--file", str(db_backup_file)]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                print(f"[+] PostgreSQL database backed up safely via pg_dump: {db_backup_file.name}")
            except subprocess.CalledProcessError as exc:
                safe_err = exc.stderr.strip() if exc.stderr else "pg_dump failed with non-zero exit code."
                raise RuntimeError(f"Database dump failed: {safe_err}")
        else:
            raise ValueError(f"Unsupported database URL scheme: {db_url}")

        db_checksum = compute_sha256(db_backup_file)

        # 2. File Storage Backup
        staging_storage = staging_dir / "storage"
        staging_storage.mkdir(parents=True, exist_ok=True)

        files_manifest: Dict[str, Dict[str, Any]] = {}
        total_bytes = 0

        if storage_dir.exists():
            for root, _, files in os.walk(storage_dir):
                for file in files:
                    src_file = Path(root) / file
                    rel_path = src_file.relative_to(storage_dir).as_posix()
                    dst_file = staging_storage / rel_path
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)

                    checksum = compute_sha256(dst_file)
                    file_size = dst_file.stat().st_size
                    total_bytes += file_size
                    files_manifest[rel_path] = {
                        "sha256": checksum,
                        "size_bytes": file_size,
                    }
            print(f"[+] Backed up {len(files_manifest)} storage files ({total_bytes} bytes)")
        else:
            print("[!] Storage directory is empty or does not exist yet.")

        # 3. Create Manifest
        manifest = {
            "backup_id": backup_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "app_version": app_version,
            "database": {
                "type": db_type,
                "filename": db_backup_file.name,
                "sha256": db_checksum,
                "size_bytes": db_backup_file.stat().st_size,
            },
            "storage": {
                "file_count": len(files_manifest),
                "total_bytes": total_bytes,
                "files": files_manifest,
            },
        }

        manifest_file = staging_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print(f"[+] Manifest created: {manifest_file.name}")

        # 4. Create Compressed Tarball
        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(staging_dir, arcname=backup_id)

        # Clean up staging directory
        shutil.rmtree(staging_dir)
        print(f"[+] Backup complete: {tarball_path}")
        print(f"[+] Archive SHA-256: {compute_sha256(tarball_path)}")

        return tarball_path
    except Exception:
        # Clean up partial staging on failure to avoid leaking temporary files
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if tarball_path.exists():
            tarball_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    out_dir = Path(os.environ.get("BACKUP_OUTPUT_DIR", "./backups")).resolve()
    stor_dir = Path(os.environ.get("STORAGE_DIR", "./backend/data/storage")).resolve()
    database_url = os.environ.get(
        "DATABASE_URL",
        "sqlite+aiosqlite:///f:/RAG/backend/dev.db" if sys.platform == "win32" else "sqlite+aiosqlite:///app/dev.db"
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        archive = create_backup(
            output_dir=out_dir,
            storage_dir=stor_dir,
            db_url=database_url,
        )
        print(f"SUCCESS: Backup created at {archive}")
    except Exception as e:
        print(f"ERROR: Backup failed: {e}", file=sys.stderr)
        sys.exit(1)
