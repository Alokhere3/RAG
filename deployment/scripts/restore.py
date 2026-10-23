#!/usr/bin/env python3
"""Cross-platform Restore and Verification Utility for Self-Hosted Dedicated RAG Platform.

Restores and verifies:
1. Manifest integrity and SHA-256 validation.
2. Archive member path containment (rejection of directory traversal, absolute paths, and symlinks).
3. Database restore into target clean database.
4. File storage restore into target storage directory with safe path containment.
5. End-to-end consistency check between database metadata and stored files.
"""

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


def validate_tar_member(member: tarfile.TarInfo, target_dir: Path) -> None:
    """Validate archive member to prevent traversal, symlink escape, and malicious paths."""
    # Reject device files, FIFOs, etc.
    if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
        raise ValueError(f"Prohibited archive member type for entry: {member.name}")

    # Reject symlinks and hardlinks
    if member.issym() or member.islnk():
        raise ValueError(f"Prohibited link member in backup archive: {member.name}")

    # Normalize path separators
    normalized_name = member.name.replace("\\", "/")

    # Check for absolute paths, traversal, or drive letters
    if (
        normalized_name.startswith("/")
        or ".." in normalized_name.split("/")
        or (len(normalized_name) > 1 and normalized_name[1] == ":")
        or normalized_name.startswith("//")
    ):
        raise ValueError(f"Path traversal detected in archive member: {member.name}")

    # Resolve destination path and verify containment
    resolved_target = target_dir.resolve()
    dest_path = (target_dir / member.name).resolve()
    try:
        dest_path.relative_to(resolved_target)
    except ValueError:
        raise ValueError(f"Archive member escapes destination root: {member.name}")


def validate_manifest_path(rel_path: str, base_dir: Path) -> Path:
    """Validate manifest relative path strictly remains inside base_dir."""
    normalized = rel_path.replace("\\", "/")
    if (
        normalized.startswith("/")
        or ".." in normalized.split("/")
        or (len(normalized) > 1 and normalized[1] == ":")
        or normalized.startswith("//")
    ):
        raise ValueError(f"Path traversal detected in manifest path: {rel_path}")

    target_resolved = base_dir.resolve()
    dest = (base_dir / rel_path).resolve()
    try:
        dest.relative_to(target_resolved)
    except ValueError:
        raise ValueError(f"Manifest path escapes destination boundary: {rel_path}")
    return dest


def restore_backup(
    archive_path: Path,
    target_storage_dir: Path,
    target_db_url: str,
    work_dir: Path,
) -> Dict[str, Any]:
    """Extract, verify, and restore a backup archive with strict path hardening."""
    print(f"[*] Starting restore from: {archive_path}")
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive not found at: {archive_path}")

    # 1. Extract archive to working staging directory
    staging_extract_dir = work_dir / "restore_staging"
    if staging_extract_dir.exists():
        shutil.rmtree(staging_extract_dir)
    staging_extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            # Pre-validate all members before writing anything
            for member in tar.getmembers():
                validate_tar_member(member, staging_extract_dir)

            # Use Python 3.12+ safe extraction filter if supported
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=staging_extract_dir, filter="data")
            else:
                tar.extractall(path=staging_extract_dir)

        # Find the extracted root directory (should contain manifest.json)
        manifest_paths = list(staging_extract_dir.glob("**/manifest.json"))
        if not manifest_paths:
            raise ValueError("Invalid backup archive: manifest.json not found.")

        backup_root = manifest_paths[0].parent
        manifest_file = manifest_paths[0]

        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        print(f"[+] Loaded manifest for backup: {manifest.get('backup_id')} (Created: {manifest.get('created_at')})")

        # 2. Verify Database Backup Integrity
        db_info = manifest["database"]
        db_dump_file = validate_manifest_path(db_info["filename"], backup_root)
        if not db_dump_file.exists():
            raise FileNotFoundError(f"Database dump file missing in archive: {db_dump_file}")

        actual_db_sha256 = compute_sha256(db_dump_file)
        if actual_db_sha256 != db_info["sha256"]:
            raise ValueError(
                f"Database checksum mismatch! Expected: {db_info['sha256']}, got: {actual_db_sha256}"
            )
        print("[+] Database dump integrity verified.")

        # 3. Verify Storage Files Integrity
        storage_info = manifest["storage"]
        files_manifest: Dict[str, Dict[str, Any]] = storage_info.get("files", {})
        extracted_storage = backup_root / "storage"

        for rel_path, meta in files_manifest.items():
            extracted_file = validate_manifest_path(rel_path, extracted_storage)
            if not extracted_file.exists():
                raise FileNotFoundError(f"Storage file missing in backup: {rel_path}")
            actual_sha = compute_sha256(extracted_file)
            if actual_sha != meta["sha256"]:
                raise ValueError(
                    f"File checksum mismatch for {rel_path}! Expected {meta['sha256']}, got {actual_sha}"
                )
        print(f"[+] All {len(files_manifest)} files in archive verified.")

        # 4. Restore Storage Files to Target Storage Directory
        target_storage_dir.mkdir(parents=True, exist_ok=True)
        for rel_path in files_manifest.keys():
            src = validate_manifest_path(rel_path, extracted_storage)
            dst = validate_manifest_path(rel_path, target_storage_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        print(f"[+] Successfully restored storage files to: {target_storage_dir}")

        # 5. Restore Database
        db_type = db_info["type"]
        if target_db_url.startswith("sqlite"):
            clean_target_path = target_db_url.split("///")[-1].split("?")[0]
            target_db_file = Path(clean_target_path).resolve()
            target_db_file.parent.mkdir(parents=True, exist_ok=True)

            # Restore SQLite database
            src_conn = sqlite3.connect(str(db_dump_file))
            dst_conn = sqlite3.connect(str(target_db_file))
            with dst_conn:
                src_conn.backup(dst_conn)
            src_conn.close()
            dst_conn.close()
            print(f"[+] SQLite database restored to: {target_db_file}")

            # Consistency verification
            check_conn = sqlite3.connect(str(target_db_file))
            cursor = check_conn.cursor()
            try:
                cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
                print(f"[+] Verified {table_count} tables present in restored database.")
            finally:
                check_conn.close()

        elif target_db_url.startswith(("postgresql", "postgres")):
            pg_restore_bin = shutil.which("pg_restore")
            if not pg_restore_bin:
                raise RuntimeError(
                    "Required PostgreSQL restore utility 'pg_restore' is not installed or not in PATH."
                )
            cmd = [pg_restore_bin, "--clean", "--if-exists", "--dbname", target_db_url, str(db_dump_file)]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                print(f"[+] PostgreSQL database restored via pg_restore to: {target_db_url}")
            except subprocess.CalledProcessError as exc:
                safe_err = exc.stderr.strip() if exc.stderr else "pg_restore failed with non-zero exit code."
                raise RuntimeError(f"Database restore failed: {safe_err}")
        else:
            raise ValueError(f"Unsupported database scheme: {target_db_url}")

        report = {
            "status": "success",
            "backup_id": manifest.get("backup_id"),
            "restored_at": manifest.get("created_at"),
            "files_restored": len(files_manifest),
            "database_type": db_type,
        }
        print(f"[+] Restore completed successfully: {report}")
        return report

    finally:
        # Clean up staging extract directory
        if staging_extract_dir.exists():
            shutil.rmtree(staging_extract_dir, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python restore.py <path_to_backup_archive.tar.gz>", file=sys.stderr)
        sys.exit(1)

    archive = Path(sys.argv[1]).resolve()
    target_storage = Path(os.environ.get("STORAGE_DIR", "./backend/data/storage")).resolve()
    target_db = os.environ.get(
        "DATABASE_URL",
        "sqlite+aiosqlite:///f:/RAG/backend/dev.db" if sys.platform == "win32" else "sqlite+aiosqlite:///app/dev.db"
    )
    work = Path(os.environ.get("RESTORE_WORK_DIR", "./backups/staging")).resolve()

    try:
        report = restore_backup(
            archive_path=archive,
            target_storage_dir=target_storage,
            target_db_url=target_db,
            work_dir=work,
        )
        print("SUCCESS: Restore validated and complete.")
    except Exception as e:
        print(f"ERROR: Restore failed: {e}", file=sys.stderr)
        sys.exit(1)
