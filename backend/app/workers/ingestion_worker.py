"""Background worker process executing document ingestion jobs from PostgreSQL queue."""

import asyncio
import logging
import signal
import sys
from typing import Optional
import uuid

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.ingestion_service import ingestion_service

logger = logging.getLogger(__name__)


class IngestionWorker:
    """Worker polling the durable PostgreSQL queue and executing ingestion tasks."""

    def __init__(self, worker_id: Optional[str] = None) -> None:
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.running = False
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        """Signal the worker to stop processing new jobs and shut down cleanly."""
        logger.info("WORKER_SHUTDOWN_SIGNAL_RECEIVED worker_id=%s", self.worker_id)
        self.running = False
        self._stop_event.set()

    async def run(
        self,
        poll_interval: float = 1.0,
        max_jobs: Optional[int] = None,
    ) -> int:
        """Run worker polling loop until cancelled or max_jobs processed."""
        self.running = True
        self._stop_event.clear()
        processed_count = 0

        logger.info("WORKER_STARTED worker_id=%s poll_interval=%.2fs", self.worker_id, poll_interval)

        while self.running:
            try:
                async with async_session_factory() as session:
                    job = await ingestion_service.claim_next_job(session, self.worker_id)

                    if job:
                        logger.info("WORKER_PROCESSING_JOB worker_id=%s job_id=%s", self.worker_id, job.id)
                        await ingestion_service.process_job(session, job.id, self.worker_id)
                        processed_count += 1

                        if max_jobs and processed_count >= max_jobs:
                            logger.info("WORKER_MAX_JOBS_REACHED worker_id=%s count=%d", self.worker_id, processed_count)
                            break
                        continue

            except Exception as exc:
                logger.error("WORKER_LOOP_ERROR worker_id=%s err=%s", self.worker_id, exc, exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=poll_interval)
                break
            except asyncio.TimeoutError:
                pass

        logger.info("WORKER_STOPPED worker_id=%s total_processed=%d", self.worker_id, processed_count)
        return processed_count


async def main() -> None:
    """CLI entrypoint for standalone background worker."""
    settings = get_settings()
    if settings.is_production:
        settings.validate_production_safety()

    worker = IngestionWorker()

    def _handle_signal(*_):
        worker.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
