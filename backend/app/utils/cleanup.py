"""Production janitor: python -m app.utils.cleanup [--root PRIVATE_DIRECTORY]."""

import argparse
import logging
import os
import shutil
import time
import uuid
from threading import Thread
from app.config import FILES_GENERATED_DIR
from app.utils.artifacts import ArtifactStore

logger = logging.getLogger(__name__)


def empty_folders(folder_paths, max_age_in_hours):
    """Remove legacy completed UUID exports during transition, never active staging.

    Capabilities use immutable metadata, rather than directory modification time.
    This compatibility helper is restricted to legacy UUID directories.
    """
    cutoff = time.time() - max_age_in_hours * 3600
    for folder_path in folder_paths:
        if not os.path.isdir(folder_path):
            continue
        ArtifactStore(folder_path).cleanup()
        for name in os.listdir(folder_path):
            try:
                uuid.UUID(name)
            except ValueError:
                continue
            path = os.path.join(folder_path, name)
            try:
                if (
                    not os.path.islink(path)
                    and os.path.isdir(path)
                    and os.stat(path).st_mtime < cutoff
                ):
                    shutil.rmtree(path)
            except FileNotFoundError:
                pass


def cleanup_files(root=None):
    return ArtifactStore(root or FILES_GENERATED_DIR).cleanup()


def start_cleanup_schedule():
    """Development helper; hosted deployments run the separate hourly janitor."""

    def run_schedule():
        while True:
            try:
                cleanup_files()
            except Exception:
                logger.exception("Artifact cleanup failed")
            time.sleep(3600)

    thread = Thread(target=run_schedule, daemon=True)
    thread.start()
    return thread


def main():
    parser = argparse.ArgumentParser(
        description="Remove expired private GC-AI document handles"
    )
    parser.add_argument("--root", default=FILES_GENERATED_DIR)
    parser.add_argument(
        "--hourly", action="store_true", help="Run on startup and once per hour"
    )
    args = parser.parse_args()
    while True:
        removed = cleanup_files(args.root)
        logger.info("Removed %d expired artifacts", removed)
        if not args.hourly:
            return
        time.sleep(3600)


if __name__ == "__main__":
    main()
