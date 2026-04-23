"""Sync orchestrator — coordinates the full sync workflow for a project.

Workflow:
  1. Parse current strings.xml (user has already committed their changes)
  2. Load previous snapshot (from DB or git HEAD~1)
  3. Diff to detect new/modified strings
  4. Translate new strings for each target language
  5. Merge translations into values-{lang}/strings.xml
  6. Commit translation files on the current branch
  7. Save snapshot
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from transync.config import AppConfig
from transync.database import Database
from transync.models.project import Project, StringEntry, SyncRecord, SyncStatus
from transync.services.diff_engine import DiffEngine
from transync.services.git_service import GitService
from transync.services.translation_service import TranslationService
from transync.services.xml_processor import XmlProcessor

logger = logging.getLogger(__name__)


class SyncError(Exception):
    """Raised when the sync workflow encounters an unrecoverable error."""


class SyncOrchestrator:
    def __init__(self, config: AppConfig, db: Database) -> None:
        self._config = config
        self._db = db
        self._translation_svc = TranslationService(config)
        self._xml = XmlProcessor()
        self._diff = DiffEngine()

    def sync_project(self, project: Project, dry_run: bool | None = None) -> SyncRecord:
        """Run the full sync workflow for a project. Returns a SyncRecord."""
        dry_run = dry_run if dry_run is not None else self._config.sync.dry_run

        record = SyncRecord(
            id=None,
            project_id=project.id,  # type: ignore[arg-type]
            status=SyncStatus.IN_PROGRESS,
        )
        record = self._db.add_sync_record(record)

        try:
            result = self._execute_sync(project, record, dry_run)
            return result
        except Exception as exc:
            record.status = SyncStatus.FAILED
            record.error_message = str(exc)
            record.finished_at = datetime.now(timezone.utc).isoformat()
            self._db.update_sync_record(record)
            logger.exception("Sync failed for project '%s'", project.name)
            raise SyncError(str(exc)) from exc

    def _execute_sync(
        self, project: Project, record: SyncRecord, dry_run: bool
    ) -> SyncRecord:
        git = GitService(project.local_path)

        # Step 1: Parse current strings.xml from disk
        current_entries = self._step_parse_current(project)
        current_dict = XmlProcessor.entries_to_dict(current_entries)

        # Step 2: Get previous snapshot (DB or git HEAD~1)
        previous_dict = self._step_get_previous(project, git)

        # Step 3: Diff
        diff = self._diff.compute_from_dicts(
            previous_dict,
            current_dict,
            detect_modified=self._config.sync.detect_modified,
        )

        if not diff.has_changes:
            logger.info("No new, modified, or removed strings found — nothing to do")
            record.status = SyncStatus.SUCCESS
            record.finished_at = datetime.now(timezone.utc).isoformat()
            self._db.update_sync_record(record)
            self._db.save_snapshot(project.id, current_dict)  # type: ignore[arg-type]
            return record

        record.new_keys = len(diff.new_entries)
        record.modified_keys = len(diff.modified_entries)
        record.removed_keys = len(diff.removed_keys)

        entries_to_translate = diff.new_entries + diff.modified_entries
        target_langs = project.target_languages
        if not target_langs:
            raise SyncError("No target languages configured for this project")
        affected_files: list[Path] = []

        # Step 4a: Translate + merge new/modified strings
        if entries_to_translate:
            affected_files = self._step_translate_and_merge(
                project, entries_to_translate, target_langs
            )

        # Step 4b: Remove deleted keys from all language files
        if diff.removed_keys:
            removed_files = self._step_remove_deleted_keys(
                project, diff.removed_keys, target_langs
            )
            for f in removed_files:
                if f not in affected_files:
                    affected_files.append(f)

        record.languages_synced = len(target_langs)

        # Step 5: Commit on current branch (no push — local only)
        if dry_run:
            logger.info("[DRY RUN] Would commit %d files", len(affected_files))
            record.status = SyncStatus.SUCCESS
        else:
            commit_sha = self._step_commit(git, affected_files)
            record.commit_sha = commit_sha
            record.status = SyncStatus.SUCCESS

        # Step 6: Save snapshot
        self._db.save_snapshot(project.id, current_dict)  # type: ignore[arg-type]

        record.finished_at = datetime.now(timezone.utc).isoformat()
        self._db.update_sync_record(record)
        return record

    # ── Individual Steps ──────────────────────────────────────────

    def _step_parse_current(self, project: Project) -> list[StringEntry]:
        logger.info("Parsing current strings.xml")
        strings_path = project.absolute_strings_path
        if not strings_path.is_file():
            raise SyncError(f"strings.xml not found at {strings_path}")
        return self._xml.parse_strings(strings_path)

    def _step_get_previous(
        self, project: Project, git: GitService
    ) -> dict[str, str]:
        logger.info("Loading previous snapshot")
        snapshot = self._db.get_latest_snapshot(project.id)  # type: ignore[arg-type]
        if snapshot:
            logger.info("Using DB snapshot (%d keys)", len(snapshot))
            return snapshot

        # Fall back to previous git commit
        prev_content = git.get_file_content_at_commit(project.strings_path)
        if prev_content:
            entries = self._xml.parse_strings_from_content(prev_content)
            logger.info("Using git HEAD~1 snapshot (%d keys)", len(entries))
            return XmlProcessor.entries_to_dict(entries)

        logger.info("No previous snapshot — treating all strings as new")
        return {}

    def _step_translate_and_merge(
        self,
        project: Project,
        entries: list[StringEntry],
        target_langs: list[str],
    ) -> list[Path]:
        logger.info("Translating %d entries for %d languages", len(entries), len(target_langs))
        affected: list[Path] = []

        for lang in target_langs:
            translated = self._translation_svc.translate_entries(entries, lang)
            lang_dir = project.absolute_res_directory / f"values-{lang}"
            lang_file = lang_dir / "strings.xml"

            added = self._xml.merge_into_file(
                lang_file, translated, sort_keys=self._config.sync.sort_keys
            )
            if added:
                affected.append(lang_file)
                logger.info("  %s: added %d keys", lang, len(added))
            else:
                logger.info("  %s: no new keys to add", lang)

        return affected

    def _step_remove_deleted_keys(
        self,
        project: Project,
        removed_keys: list[str],
        target_langs: list[str],
    ) -> list[Path]:
        logger.info("Removing %d deleted keys from %d languages", len(removed_keys), len(target_langs))
        affected: list[Path] = []

        for lang in target_langs:
            lang_file = project.absolute_res_directory / f"values-{lang}" / "strings.xml"
            removed = self._xml.remove_keys_from_file(
                lang_file, removed_keys, sort_keys=self._config.sync.sort_keys
            )
            if removed:
                affected.append(lang_file)
                logger.info("  %s: removed %d keys", lang, len(removed))
            else:
                logger.info("  %s: no keys to remove", lang)

        return affected

    def _step_commit(self, git: GitService, files: list[Path]) -> str:
        if not files:
            logger.info("No files to commit")
            return ""

        logger.info("Committing %d translation files", len(files))
        git.stage_files(files)
        result = git.commit(self._config.git.commit_message)
        return result.sha
