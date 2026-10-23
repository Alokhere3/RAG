import asyncio
import time
import httpx

def main():
    client = httpx.Client(base_url="http://127.0.0.1:8001", timeout=30.0)

    # 1. Login
    print("[1] Logging in as admin...")
    login_res = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "AdminPass123!"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    login_data = login_res.json()
    access_token = login_data.get("accessToken") or login_data.get("access_token")
    headers = {"Authorization": f"Bearer {access_token}"}
    print("Logged in successfully. Token obtained.")

    # 2. Upload Markdown Document
    print("\n[2] Uploading markdown document...")
    md_content = b"""# Self-Hosted RAG Architecture
This document details the core parser engine and pipeline architecture.

## Ingestion Pipeline
1. Ingestion jobs are created durably.
2. Background workers claim tasks using concurrency-safe locks.
3. Extracted text artifacts are persisted to durable storage.
"""
    files = {
        "file": ("rag_architecture.md", md_content, "text/markdown")
    }
    upload_res = client.post("/api/v1/documents", headers=headers, files=files)
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
    doc = upload_res.json()
    doc_id = doc["id"]
    print(f"Document uploaded: id={doc_id}, filename={doc['filename']}, status={doc['status']}")

    # 3. Check ingestion job status
    print("\n[3] Checking initial ingestion job status...")
    status_res = client.get(f"/api/v1/documents/{doc_id}/ingest/status", headers=headers)
    assert status_res.status_code == 200, f"Status check failed: {status_res.text}"
    status_data = status_res.json()
    print("Initial Ingestion Status:", status_data)

    # 4. Trigger processing directly or let worker run
    print("\n[4] Triggering job processing...")
    # Trigger processing via service directly to confirm end-to-end execution
    from app.db.session import async_session_factory
    from app.services.ingestion_service import ingestion_service
    import uuid

    async def run_job():
        async with async_session_factory() as session:
            job = await ingestion_service.claim_next_job(session, "test_worker_1")
            if job:
                print(f"Worker claimed job {job.id} for document {job.document_id}")
                finished = await ingestion_service.process_job(session, job.id, "test_worker_1")
                print(f"Job finished: status={finished.status}, extracted_text_key={finished.extracted_text_key}")
                return finished
            else:
                print("No queued job found to claim.")

    asyncio.run(run_job())

    # 5. Check document metadata and ingestion status again
    print("\n[5] Verifying final document status...")
    doc_res = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert doc_res.status_code == 200
    doc_final = doc_res.json()
    print("Final Document:", doc_final)
    assert doc_final["status"] == "ready", f"Expected document to be ready, got: {doc_final['status']}"

    status_final = client.get(f"/api/v1/documents/{doc_id}/ingest/status", headers=headers).json()
    print("Final Ingestion Status:", status_final)
    assert status_final["currentJob"]["status"] == "succeeded"

    print("\nSUCCESS: Phase 4 Ingestion Pipeline verified end-to-end!")

if __name__ == "__main__":
    main()
