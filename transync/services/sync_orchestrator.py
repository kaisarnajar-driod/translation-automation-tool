"""Sync orchestrator — coordinates the full sync workflow for a project.

Workflow:
  1. Pull latest changes from the remote repository
  2. Parse current strings file from disk
  3. Load previous snapshot (from DB or git HEAD~1)
  4. Diff to detect new/modified strings
  5. Translate new strings for each target language
  6. Merge translations into platform-specific language directories
  7. Commit and push translation files
  8. Save snapshot
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from transync.config import AppConfig
from transync.database import Database
from transync.models.project import Project, StringEntry, SyncRecord, SyncStatus
from transync.services.diff_engine import DiffEngine
from transync.services.file_processor import get_lang_file_path, get_processor
from transync.services.git_service import GitService
from transync.services.translation_service import TranslationService

logger = logging.getLogger(__name__)


class SyncError(Exception):
    """Raised when the sync workflow encounters an unrecoverable error."""


class SyncOrchestrator:
    def __init__(self, config: AppConfig, db: Database) -> None:
        self._config = config
        self._db = db
        self._translation_svc = TranslationService(config)
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
        processor = get_processor(project.strings_path)

        # Step 0: Pull latest changes from remote
        git.pull(project.branch)

        # Step 1: Parse current strings file from disk
        current_entries = self._step_parse_current(project, processor)
        current_dict = processor.entries_to_dict(current_entries)

        # Step 2: Get previous snapshot (DB or git HEAD~1)
        previous_dict = self._step_get_previous(project, git, processor)

        # Step 3: Diff
        diff = self._diff.compute_from_dicts(
            previous_dict,
            current_dict,
            detect_modified=self._config.sync.detect_modified,
        )

        target_langs = project.target_languages
        if not target_langs:
            raise SyncError("No target languages configured for this project")

        # Detect languages that don't have a strings file yet (newly added)
        new_langs = self._detect_new_languages(project, target_langs)
        existing_langs = [l for l in target_langs if l not in new_langs]

        translatable_entries = [e for e in current_entries if e.translatable]
        affected_files: list[Path] = []

        # Step 4a: Full translation for newly added languages
        new_lang_key_count = 0
        if new_langs and translatable_entries:
            logger.info("New languages detected: %s — translating all strings", ", ".join(new_langs))
            new_lang_files = self._step_translate_and_merge(
                project, translatable_entries, new_langs, processor
            )
            affected_files.extend(new_lang_files)
            new_lang_key_count = len(translatable_entries)

        if not diff.has_changes and not new_langs:
            logger.info("No new, modified, or removed strings found — nothing to do")
            record.status = SyncStatus.SUCCESS
            record.finished_at = datetime.now(timezone.utc).isoformat()
            self._db.update_sync_record(record)
            self._db.save_snapshot(project.id, current_dict)  # type: ignore[arg-type]
            return record

        record.new_keys = len(diff.new_entries) + new_lang_key_count
        record.modified_keys = len(diff.modified_entries)
        record.removed_keys = len(diff.removed_keys)

        entries_to_translate = diff.new_entries + diff.modified_entries

        # Step 4b: Translate + merge new/modified strings for existing languages
        if entries_to_translate and existing_langs:
            merge_files = self._step_translate_and_merge(
                project, entries_to_translate, existing_langs, processor
            )
            for f in merge_files:
                if f not in affected_files:
                    affected_files.append(f)

        # Step 4c: Remove deleted keys from all language files
        if diff.removed_keys:
            removed_files = self._step_remove_deleted_keys(
                project, diff.removed_keys, target_langs, processor
            )
            for f in removed_files:
                if f not in affected_files:
                    affected_files.append(f)

        record.languages_synced = len(target_langs)

        # Step 5: Commit and push
        if dry_run:
            logger.info("[DRY RUN] Would commit and push %d files", len(affected_files))
            record.status = SyncStatus.SUCCESS
        else:
            commit_sha = self._step_commit_and_push(git, affected_files, project.branch)
            record.commit_sha = commit_sha
            record.status = SyncStatus.SUCCESS

        # Step 6: Save snapshot
        self._db.save_snapshot(project.id, current_dict)  # type: ignore[arg-type]

        record.finished_at = datetime.now(timezone.utc).isoformat()
        self._db.update_sync_record(record)
        return record

    # ── Individual Steps ──────────────────────────────────────────

    @staticmethod
    def _detect_new_languages(project: Project, target_langs: list[str]) -> list[str]:
        """Return languages that don't have a strings file yet."""
        new_langs: list[str] = []
        for lang in target_langs:
            if not get_lang_file_path(project, lang).is_file():
                new_langs.append(lang)
        return new_langs

    @staticmethod
    def _step_parse_current(project: Project, processor) -> list[StringEntry]:
        logger.info("Parsing current strings file")
        strings_path = project.absolute_strings_path
        if not strings_path.is_file():
            raise SyncError(f"Strings file not found at {strings_path}")
        return processor.parse_strings(strings_path)

    def _step_get_previous(
        self, project: Project, git: GitService, processor
    ) -> dict[str, str]:
        logger.info("Loading previous snapshot")
        snapshot = self._db.get_latest_snapshot(project.id)  # type: ignore[arg-type]
        if snapshot:
            logger.info("Using DB snapshot (%d keys)", len(snapshot))
            return snapshot

        prev_content = git.get_file_content_at_commit(project.strings_path)
        if prev_content:
            entries = processor.parse_strings_from_content(prev_content)
            logger.info("Using git HEAD~1 snapshot (%d keys)", len(entries))
            return processor.entries_to_dict(entries)

        logger.info("No previous snapshot — treating all strings as new")
        return {}

    def _step_translate_and_merge(
        self,
        project: Project,
        entries: list[StringEntry],
        target_langs: list[str],
        processor,
    ) -> list[Path]:
        logger.info("Translating %d entries for %d languages", len(entries), len(target_langs))
        affected: list[Path] = []

        for lang in target_langs:
            translated = self._translation_svc.translate_entries(entries, lang)
            lang_file = get_lang_file_path(project, lang)

            added = processor.merge_into_file(
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
        processor,
    ) -> list[Path]:
        logger.info("Removing %d deleted keys from %d languages", len(removed_keys), len(target_langs))
        affected: list[Path] = []

        for lang in target_langs:
            lang_file = get_lang_file_path(project, lang)
            removed = processor.remove_keys_from_file(
                lang_file, removed_keys, sort_keys=self._config.sync.sort_keys
            )
            if removed:
                affected.append(lang_file)
                logger.info("  %s: removed %d keys", lang, len(removed))
            else:
                logger.info("  %s: no keys to remove", lang)

        return affected

    def _step_commit_and_push(
        self, git: GitService, files: list[Path], branch: str
    ) -> str:
        if not files:
            logger.info("No files to commit")
            return ""

        logger.info("Committing %d translation files", len(files))
        git.stage_files(files)
        result = git.commit(self._config.git.commit_message)

        logger.info("Pushing translations to remote")
        git.push(branch)

        return result.sha
