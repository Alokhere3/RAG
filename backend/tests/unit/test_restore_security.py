"""Unit tests for F-04: Restore security, path traversal mitigation, and safe extraction."""

import io
import json
from pathlib import Path
import sqlite3
import sys
import tarfile
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deployment.scripts.backup import create_backup
from deployment.scripts.restore import restore_backup, validate_tar_member, validate_manifest_path


def create_adversarial_tar(tar_path: Path, member_name: str, content: bytes, is_symlink: bool = False, link_target: str = ""):
    """Helper to craft synthetic adversarial tar archives."""
    with tarfile.open(tar_path, "w:gz") as tar:
        ti = tarfile.TarInfo(name=member_name)
        if is_symlink:
            ti.type = tarfile.SYMTYPE
            ti.linkname = link_target
            tar.addfile(ti)
        else:
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))


def test_restore_rejects_path_traversal_archive(tmp_path):
    """Ensure archives containing '../' traversal entries are rejected."""
    bad_tar = tmp_path / "traversal.tar.gz"
    create_adversarial_tar(bad_tar, "../../../outside.txt", b"malicious content")

    work_dir = tmp_path / "work"
    storage_dir = tmp_path / "storage"
    target_db = f"sqlite:///{tmp_path / 'restored.db'}"

    with pytest.raises(ValueError) as exc_info:
        restore_backup(
            archive_path=bad_tar,
            target_storage_dir=storage_dir,
            target_db_url=target_db,
            work_dir=work_dir,
        )

    assert "Path traversal detected" in str(exc_info.value) or "escapes destination" in str(exc_info.value)
    # Ensure nothing was written outside
    assert not (tmp_path.parent / "outside.txt").exists()


def test_restore_rejects_absolute_path_archive(tmp_path):
    """Ensure archives containing absolute root paths are rejected."""
    bad_tar = tmp_path / "absolute.tar.gz"
    create_adversarial_tar(bad_tar, "/etc/shadow", b"malicious")

    work_dir = tmp_path / "work"
    storage_dir = tmp_path / "storage"
    target_db = f"sqlite:///{tmp_path / 'restored.db'}"

    with pytest.raises(ValueError) as exc_info:
        restore_backup(
            archive_path=bad_tar,
            target_storage_dir=storage_dir,
            target_db_url=target_db,
            work_dir=work_dir,
        )

    assert "Path traversal detected" in str(exc_info.value) or "escapes destination" in str(exc_info.value)


def test_restore_rejects_symlink_archive(tmp_path):
    """Ensure archives containing symlinks are rejected."""
    bad_tar = tmp_path / "symlink.tar.gz"
    create_adversarial_tar(bad_tar, "link_to_root", b"", is_symlink=True, link_target="/")

    work_dir = tmp_path / "work"
    storage_dir = tmp_path / "storage"
    target_db = f"sqlite:///{tmp_path / 'restored.db'}"

    with pytest.raises(ValueError) as exc_info:
        restore_backup(
            archive_path=bad_tar,
            target_storage_dir=storage_dir,
            target_db_url=target_db,
            work_dir=work_dir,
        )

    assert "Prohibited link member" in str(exc_info.value)


def test_restore_rejects_malicious_manifest_path(tmp_path):
    """Ensure malicious relative paths in manifest.json are rejected before file copy."""
    # Build a valid archive first
    backups_dir = tmp_path / "backups"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True)
    (storage_dir / "sample.txt").write_text("Valid File", encoding="utf-8")

    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test (id INT)")
    conn.commit()
    conn.close()

    archive = create_backup(
        output_dir=backups_dir,
        storage_dir=storage_dir,
        db_url=f"sqlite:///{db_file.as_posix()}",
    )

    # Tamper with archive manifest
    extract_dir = tmp_path / "tamper"
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(path=extract_dir)

    manifest_file = list(extract_dir.glob("**/manifest.json"))[0]
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    # Inject adversarial manifest path
    manifest["storage"]["files"]["../../escaped.txt"] = {"sha256": "fake", "size_bytes": 10}
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    tampered_archive = tmp_path / "tampered.tar.gz"
    with tarfile.open(tampered_archive, "w:gz") as tar:
        tar.add(manifest_file.parent, arcname=manifest_file.parent.name)

    restore_storage = tmp_path / "restored_storage"
    target_db = f"sqlite:///{tmp_path / 'restored.db'}"
    work_dir = tmp_path / "work"

    with pytest.raises(ValueError) as exc_info:
        restore_backup(
            archive_path=tampered_archive,
            target_storage_dir=restore_storage,
            target_db_url=target_db,
            work_dir=work_dir,
        )

    assert "Path traversal detected in manifest path" in str(exc_info.value)
    assert not (tmp_path / "escaped.txt").exists()


def test_valid_archive_roundtrip_restores_cleanly(tmp_path):
    """Verify valid backup restores successfully and cleans up staging."""
    backups_dir = tmp_path / "backups"
    storage_dir = tmp_path / "src_storage"
    storage_dir.mkdir(parents=True)
    (storage_dir / "doc.txt").write_text("Secret Content Canary", encoding="utf-8")

    src_db = tmp_path / "src.db"
    conn = sqlite3.connect(str(src_db))
    conn.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO records (note) VALUES ('persisted_entry')")
    conn.commit()
    conn.close()

    archive = create_backup(
        output_dir=backups_dir,
        storage_dir=storage_dir,
        db_url=f"sqlite:///{src_db.as_posix()}",
    )

    target_storage = tmp_path / "dst_storage"
    target_db_file = tmp_path / "dst.db"
    target_db_url = f"sqlite:///{target_db_file.as_posix()}"
    work_dir = tmp_path / "work"

    report = restore_backup(
        archive_path=archive,
        target_storage_dir=target_storage,
        target_db_url=target_db_url,
        work_dir=work_dir,
    )

    assert report["status"] == "success"
    assert (target_storage / "doc.txt").read_text(encoding="utf-8") == "Secret Content Canary"

    # Verify restored database
    check_conn = sqlite3.connect(str(target_db_file))
    cur = check_conn.cursor()
    cur.execute("SELECT note FROM records WHERE id = 1")
    row = cur.fetchone()
    check_conn.close()
    assert row[0] == "persisted_entry"

    # Verify staging cleaned up
    assert not (work_dir / "restore_staging").exists()
