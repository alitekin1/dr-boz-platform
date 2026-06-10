from __future__ import annotations

from pathlib import Path
import re


FileSnapshot = dict[str, tuple[int, int]]

TRACKED_TEMP_EXTENSIONS = {
    ".csv",
    ".docx",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".webp",
    ".xls",
    ".xlsx",
}


def snapshot_tool_files(cwd: str | Path, extra_dirs: list[str | Path] | None = None) -> FileSnapshot:
    paths = _iter_candidate_files(cwd, extra_dirs)
    return {str(path): _file_signature(path) for path in paths}


def changed_tool_files(
    before: FileSnapshot,
    cwd: str | Path,
    *,
    extra_dirs: list[str | Path] | None = None,
    exclude_paths: set[str] | None = None,
) -> list[str]:
    excluded = {str(Path(path).resolve()) for path in (exclude_paths or set())}
    changed: list[str] = []

    for path in _iter_candidate_files(cwd, extra_dirs):
        resolved = str(path)
        if resolved in excluded:
            continue
        if before.get(resolved) != _file_signature(path):
            changed.append(resolved)

    return sorted(changed)


def existing_tool_files_from_output(output: str, cwd: str | Path, start_time: float | None = None) -> list[str]:
    if not output:
        return []

    cwd_path = Path(cwd).resolve()
    found: dict[str, str] = {}
    for raw_match in re.findall(r"(?P<path>(?:/|\.{1,2}/)?[^\s'\"<>|]+?\.[A-Za-z0-9]{1,8})", output):
        cleaned = raw_match.rstrip(".,;:)]}")
        candidate = Path(cleaned)
        if not candidate.is_absolute():
            candidate = cwd_path / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and resolved.suffix.lower() in TRACKED_TEMP_EXTENSIONS:
            if start_time is not None:
                try:
                    if resolved.stat().st_mtime < start_time - 2:
                        continue
                except OSError:
                    continue
            found[str(resolved)] = str(resolved)

    return sorted(found)


def _iter_candidate_files(cwd: str | Path, extra_dirs: list[str | Path] | None) -> list[Path]:
    candidates: dict[str, Path] = {}
    cwd_path = Path(cwd).resolve()

    if cwd_path.is_dir():
        for path in cwd_path.glob("*.*"):
            if path.is_file():
                resolved = path.resolve()
                candidates[str(resolved)] = resolved

    for directory in extra_dirs or []:
        dir_path = Path(directory).resolve()
        if not dir_path.is_dir():
            continue
        for path in dir_path.glob("*.*"):
            if path.is_file() and path.suffix.lower() in TRACKED_TEMP_EXTENSIONS:
                resolved = path.resolve()
                candidates[str(resolved)] = resolved

    return list(candidates.values())


def _file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size
