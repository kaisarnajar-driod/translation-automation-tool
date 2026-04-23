"""Transync Web UI — Flask server for managing projects and running syncs."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from transync.config import AppConfig, load_config
from transync.database import Database
from transync.models.project import Project
from transync.services.sync_orchestrator import SyncError, SyncOrchestrator

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: AppConfig | None = None) -> Flask:
    cfg = config or load_config()
    db = Database(cfg.database.resolved_path)

    app = Flask(__name__, static_folder=str(STATIC_DIR))
    app.config["TRANSYNC"] = cfg

    # ── Serve the SPA ─────────────────────────────────────────────

    @app.route("/")
    def index():
        return send_from_directory(str(STATIC_DIR), "index.html")

    # ── API: Projects ─────────────────────────────────────────────

    @app.route("/api/projects", methods=["GET"])
    def list_projects():
        projects = db.list_projects()
        return jsonify([_project_to_dict(p) for p in projects])

    @app.route("/api/projects", methods=["POST"])
    def add_project():
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        local_path = data.get("local_path", "").strip()
        strings_path = data.get("strings_path", cfg.default_strings_path).strip()
        res_directory = data.get("res_directory", cfg.res_directory).strip()
        branch = data.get("branch", cfg.git.default_branch).strip()
        languages = data.get("languages", [])

        if not name:
            return jsonify({"error": "Project name is required"}), 400
        if not local_path:
            return jsonify({"error": "Local path is required"}), 400

        local = Path(local_path).expanduser().resolve()
        if not local.is_dir():
            return jsonify({"error": f"Directory does not exist: {local}"}), 400
        if not (local / ".git").is_dir():
            return jsonify({"error": f"Not a git repository: {local}"}), 400

        if db.get_project(name):
            return jsonify({"error": f"Project '{name}' already exists"}), 409

        if isinstance(languages, str):
            languages = [l.strip() for l in languages.split(",") if l.strip()]

        project = Project(
            id=None,
            name=name,
            repo_url=str(local),
            local_path=str(local),
            branch=branch,
            strings_path=strings_path,
            res_directory=res_directory,
            target_languages=languages,
        )
        saved = db.add_project(project)
        return jsonify(_project_to_dict(saved)), 201

    @app.route("/api/projects/<name>", methods=["DELETE"])
    def remove_project(name: str):
        if not db.remove_project(name):
            return jsonify({"error": f"Project '{name}' not found"}), 404
        return jsonify({"message": f"Project '{name}' removed"}), 200

    # ── API: Sync ─────────────────────────────────────────────────

    @app.route("/api/projects/<name>/sync", methods=["POST"])
    def sync_project(name: str):
        project = db.get_project(name)
        if not project:
            return jsonify({"error": f"Project '{name}' not found"}), 404

        body = request.get_json(silent=True) or {}
        dry_run = body.get("dry_run", False)

        orchestrator = SyncOrchestrator(cfg, db)
        try:
            record = orchestrator.sync_project(project, dry_run=dry_run)
            return jsonify({
                "status": record.status.value,
                "new_keys": record.new_keys,
                "modified_keys": record.modified_keys,
                "removed_keys": record.removed_keys,
                "languages_synced": record.languages_synced,
                "commit_sha": record.commit_sha,
                "error": record.error_message,
            })
        except SyncError as exc:
            return jsonify({"status": "failed", "error": str(exc)}), 500
        except Exception:
            logger.exception("Unexpected sync error")
            return jsonify({"status": "failed", "error": traceback.format_exc()}), 500

    # ── API: History ──────────────────────────────────────────────

    @app.route("/api/projects/<name>/history", methods=["GET"])
    def get_history(name: str):
        project = db.get_project(name)
        if not project:
            return jsonify({"error": f"Project '{name}' not found"}), 404
        records = db.get_sync_history(project.id, limit=20)  # type: ignore[arg-type]
        return jsonify([
            {
                "id": r.id,
                "status": r.status.value,
                "new_keys": r.new_keys,
                "modified_keys": r.modified_keys,
                "removed_keys": r.removed_keys,
                "languages_synced": r.languages_synced,
                "commit_sha": r.commit_sha,
                "error_message": r.error_message,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in records
        ])

    # ── API: Config ───────────────────────────────────────────────

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify({
            "target_languages": cfg.target_languages,
            "translation_provider": cfg.translation.provider,
            "default_strings_path": cfg.default_strings_path,
            "res_directory": cfg.res_directory,
        })

    return app


def _project_to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "repo_url": p.repo_url,
        "local_path": p.local_path,
        "branch": p.branch,
        "strings_path": p.strings_path,
        "res_directory": p.res_directory,
        "target_languages": p.target_languages,
        "created_at": p.created_at,
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    app = create_app(cfg)
    print("\n  Transync Web UI running at: http://localhost:8090\n")
    app.run(host="0.0.0.0", port=8090, debug=True)


if __name__ == "__main__":
    main()
