"""Daily scheduler — runs sync for all projects at a configured time."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time, timedelta, timezone
from dataclasses import dataclass, field

from transync.config import AppConfig
from transync.database import Database
from transync.services.sync_orchestrator import SyncOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class SchedulerStatus:
    enabled: bool = False
    scheduled_time: str = "00:00"
    next_run: str = ""
    last_run: str = ""
    last_results: list[dict] = field(default_factory=list)


class DailyScheduler:
    """Schedules a sync-all-projects job to run once daily at a fixed time."""

    def __init__(self, config: AppConfig, db: Database) -> None:
        self._config = config
        self._db = db
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._status = SchedulerStatus(
            enabled=config.schedule.enabled,
            scheduled_time=config.schedule.time,
        )
        if self._status.enabled:
            self._schedule_next()

    @property
    def status(self) -> SchedulerStatus:
        return self._status

    def start(self) -> None:
        with self._lock:
            self._status.enabled = True
            self._schedule_next()
        logger.info("Scheduler started — next run at %s", self._status.next_run)

    def stop(self) -> None:
        with self._lock:
            self._status.enabled = False
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._status.next_run = ""
        logger.info("Scheduler stopped")

    def sync_all_now(self) -> list[dict]:
        """Sync all projects immediately. Returns per-project results."""
        return self._run_sync_all()

    def _schedule_next(self) -> None:
        if self._timer:
            self._timer.cancel()

        delay = self._seconds_until_next_run()
        next_dt = datetime.now(timezone.utc) + timedelta(seconds=delay)
        self._status.next_run = next_dt.isoformat()

        self._timer = threading.Timer(delay, self._on_trigger)
        self._timer.daemon = True
        self._timer.start()

    def _seconds_until_next_run(self) -> float:
        now = datetime.now()
        target = self._parse_time(self._status.scheduled_time)
        target_dt = now.replace(
            hour=target.hour, minute=target.minute, second=0, microsecond=0
        )
        if target_dt <= now:
            target_dt += timedelta(days=1)
        return (target_dt - now).total_seconds()

    def _on_trigger(self) -> None:
        logger.info("Scheduled sync triggered at %s", datetime.now(timezone.utc).isoformat())
        try:
            self._run_sync_all()
        except Exception:
            logger.exception("Scheduled sync-all failed")
        finally:
            with self._lock:
                if self._status.enabled:
                    self._schedule_next()

    def _run_sync_all(self) -> list[dict]:
        projects = self._db.list_projects()
        if not projects:
            logger.info("No projects to sync")
            return []

        orchestrator = SyncOrchestrator(self._config, self._db)
        results: list[dict] = []

        for project in projects:
            try:
                logger.info("Syncing project: %s", project.name)
                record = orchestrator.sync_project(project)
                results.append({
                    "project": project.name,
                    "status": record.status.value,
                    "new_keys": record.new_keys,
                    "modified_keys": record.modified_keys,
                    "removed_keys": record.removed_keys,
                    "languages_synced": record.languages_synced,
                })
            except Exception as exc:
                logger.exception("Sync failed for project '%s'", project.name)
                results.append({
                    "project": project.name,
                    "status": "failed",
                    "error": str(exc),
                })

        self._status.last_run = datetime.now(timezone.utc).isoformat()
        self._status.last_results = results
        logger.info("Sync-all complete: %d projects processed", len(results))
        return results

    @staticmethod
    def _parse_time(time_str: str) -> time:
        parts = time_str.split(":")
        return time(hour=int(parts[0]), minute=int(parts[1]) if len(parts) > 1 else 0)
