#!/usr/bin/env python3
"""Validate and export publishable Obsidian notes into a temporary Hexo source."""

from __future__ import annotations

import argparse
from functools import partial
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

import yaml


ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / ".cache" / "obsidian-publish"
IGNORED_PARTS = {".obsidian", ".stversions", ".stfolder", ".trash"}
IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WIKI_RE = re.compile(r"(!?)\[\[([^\]\n]+)\]\]")
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
MARKDOWN_NOTE_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+\.md(?:#[^)]*)?)\)", re.I)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


class PublishError(RuntimeError):
    """Represent a user-correctable publishing validation error."""


@dataclass(frozen=True)
class Note:
    """Store one parsed Vault note and its normalized publishing metadata."""

    path: Path
    relative: Path
    metadata: dict[str, Any]
    body: str
    body_start_line: int

    @property
    def published(self) -> bool:
        """Return whether the note is explicitly marked for publishing."""

        return self.metadata.get("publish") is True

    @property
    def slug(self) -> str:
        """Return the configured stable slug, or an empty string."""

        value = self.metadata.get("slug")
        return str(value).strip() if value is not None else ""

    @property
    def title(self) -> str:
        """Return the configured title, falling back to the filename."""

        return str(self.metadata.get("title") or self.path.stem).strip()

    @property
    def categories(self) -> list[str]:
        """Return categories as a hierarchy-compatible string list."""

        value = self.metadata.get("categories", self.metadata.get("category", []))
        return normalize_list(value)

    @property
    def tags(self) -> list[str]:
        """Return tags as a normalized string list."""

        return normalize_list(self.metadata.get("tags", []))


@dataclass(frozen=True)
class ExportResult:
    """Describe a validated export and its temporary Hexo configuration."""

    notes: tuple[Note, ...]
    missing_dates: tuple[Note, ...]
    source_dir: Path | None = None
    config_path: Path | None = None


def normalize_list(value: Any) -> list[str]:
    """Normalize a scalar or YAML list into non-empty strings."""

    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def is_ignored(path: Path, vault: Path) -> bool:
    """Return whether a Vault path is metadata, history, or a conflict file."""

    relative = path.relative_to(vault)
    return bool(IGNORED_PARTS.intersection(relative.parts)) or ".sync-conflict-" in path.name


def split_front_matter(text: str, path: Path) -> tuple[dict[str, Any], str, int]:
    """Parse YAML front matter and return metadata, body, and its first line."""

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text, 1
    closing = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing is None:
        raise PublishError(f"{path}: front matter 缺少结束分隔符 ---")
    try:
        metadata = yaml.safe_load("".join(lines[1:closing])) or {}
    except yaml.YAMLError as error:
        raise PublishError(f"{path}: front matter YAML 无效: {error}") from error
    if not isinstance(metadata, dict):
        raise PublishError(f"{path}: front matter 必须是键值映射")
    return metadata, "".join(lines[closing + 1 :]), closing + 2


def load_notes(vault: Path) -> list[Note]:
    """Load all Markdown notes that participate in link resolution."""

    notes: list[Note] = []
    for path in sorted(vault.rglob("*.md"), key=lambda item: item.as_posix().casefold()):
        if is_ignored(path, vault):
            continue
        metadata, body, body_line = split_front_matter(path.read_text(encoding="utf-8-sig"), path)
        notes.append(Note(path, path.relative_to(vault), metadata, body, body_line))
    return notes


def validate_published(notes: Iterable[Note]) -> tuple[Note, ...]:
    """Validate public metadata and return notes in deterministic order."""

    published = tuple(note for note in notes if note.published)
    errors: list[str] = []
    slugs: dict[str, Note] = {}
    for note in published:
        if not note.slug:
            errors.append(f"{note.relative}: publish: true 时必须设置 slug")
            continue
        if not SLUG_RE.fullmatch(note.slug):
            errors.append(f"{note.relative}: slug '{note.slug}' 只能使用小写 ASCII 字母、数字和连字符")
        key = note.slug.casefold()
        if key in slugs:
            errors.append(f"{note.relative}: slug 与 {slugs[key].relative} 重复（忽略大小写）")
        else:
            slugs[key] = note
        if not note.title:
            errors.append(f"{note.relative}: title 不能为空")
    if errors:
        raise PublishError("\n".join(errors))
    return tuple(sorted(published, key=lambda note: note.slug.casefold()))


def note_lookup(notes: Iterable[Note]) -> tuple[dict[str, Note], dict[str, list[Note]]]:
    """Build case-insensitive indexes for Vault-relative paths and note stems."""

    by_path: dict[str, Note] = {}
    by_stem: dict[str, list[Note]] = {}
    for note in notes:
        relative = note.relative.with_suffix("").as_posix().casefold()
        if relative in by_path:
            raise PublishError(
                f"{note.relative}: 笔记路径与 {by_path[relative].relative} "
                "冲突（Windows 忽略大小写）"
            )
        by_path[relative] = note
        by_stem.setdefault(note.path.stem.casefold(), []).append(note)
    return by_path, by_stem


def resolve_note(reference: str, current: Note, indexes: tuple[dict[str, Note], dict[str, list[Note]]]) -> Note:
    """Resolve an Obsidian note reference using path-first, then unique-name rules."""

    by_path, by_stem = indexes
    clean = unquote(reference.strip()).replace("\\", "/")
    clean = clean[:-3] if clean.casefold().endswith(".md") else clean
    candidates = [clean, (current.relative.parent / clean).as_posix()]
    for candidate in candidates:
        found = by_path.get(candidate.strip("/").casefold())
        if found:
            return found
    matches = by_stem.get(Path(clean).name.casefold(), [])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(str(note.relative) for note in matches)
        raise PublishError(f"链接 '{reference}' 存在多个同名目标: {choices}")
    raise PublishError(f"找不到笔记链接目标 '{reference}'")


def route_for(note: Note) -> str:
    """Return the Hexo route implied by categories and the stable slug."""

    categories = note.categories or ["uncategorized"]
    encoded = [quote(part, safe="-._~") for part in (*categories, note.slug)]
    return "/" + "/".join(encoded) + "/"


def heading_fragment(heading: str) -> str:
    """Approximate Hexo's Markdown heading identifier for internal links."""

    value = heading.strip().casefold().replace(" ", "-")
    value = re.sub(r"[^\w\-\u3400-\u9fff]", "", value)
    return quote(value, safe="-._~")


def split_reference(value: str) -> tuple[str, str | None, str | None]:
    """Split an Obsidian reference into target, heading, and display alias."""

    target_and_heading, separator, alias = value.partition("|")
    target, heading_separator, heading = target_and_heading.partition("#")
    if "^" in target_and_heading:
        raise PublishError("暂不支持 Obsidian block 引用 (^block-id)")
    return target.strip(), heading.strip() if heading_separator else None, alias.strip() if separator else None


def resolve_asset(reference: str, current: Note, vault: Path, assets_by_name: dict[str, list[Path]]) -> Path:
    """Resolve an attachment without allowing paths outside the Vault."""

    clean = Path(unquote(reference.strip()).replace("\\", "/"))
    candidates = [current.path.parent / clean, vault / clean, vault / "attachments" / clean]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.is_relative_to(vault.resolve()):
            return resolved
    matches = assets_by_name.get(clean.name.casefold(), [])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(str(path.relative_to(vault)) for path in matches)
        raise PublishError(f"附件 '{reference}' 存在多个同名文件: {choices}")
    raise PublishError(f"找不到附件 '{reference}'")


def asset_lookup(vault: Path) -> dict[str, list[Path]]:
    """Index non-note Vault files by case-insensitive basename."""

    result: dict[str, list[Path]] = {}
    for path in vault.rglob("*"):
        if path.is_file() and path.suffix.casefold() != ".md" and not is_ignored(path, vault):
            result.setdefault(path.name.casefold(), []).append(path.resolve())
    return result


def copy_asset(source: Path, destination: Path, copied: dict[str, Path]) -> str:
    """Copy one image into a post asset folder and detect basename collisions."""

    if source.suffix.casefold() not in IMAGE_SUFFIXES:
        raise PublishError(f"暂不支持嵌入附件类型 '{source.suffix or '(无扩展名)'}': {source}")
    key = source.name.casefold()
    previous = copied.get(key)
    if previous and previous != source:
        raise PublishError(f"文章引用了两个同名附件 '{source.name}': {previous} 和 {source}")
    before_copy = fingerprint(source)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination / source.name)
    if fingerprint(source) != before_copy:
        raise PublishError(f"复制期间附件发生变化，请等待同步完成后重试: {source}")
    copied[key] = source
    return source.name


def transform_plain_text(
    text: str,
    note: Note,
    line_number: int,
    vault: Path,
    indexes: tuple[dict[str, Note], dict[str, list[Note]]],
    assets_by_name: dict[str, list[Path]],
    asset_dir: Path,
    copied: dict[str, Path],
) -> str:
    """Convert links and image embeds in text known not to be inline code."""

    def wiki_replace(match: re.Match[str]) -> str:
        """Convert one Obsidian wikilink or image embed."""

        embedded, raw = match.groups()
        target_text, heading, alias = split_reference(raw)
        if embedded:
            if heading or not Path(target_text).suffix:
                raise PublishError("暂不支持笔记或标题嵌入，只支持图片附件")
            source = resolve_asset(target_text, note, vault, assets_by_name)
            filename = copy_asset(source, asset_dir, copied)
            return f"![{alias or source.stem}]({filename})"
        if not target_text and heading:
            return f"[{alias or heading}](#{heading_fragment(heading)})"
        target = resolve_note(target_text, note, indexes)
        if not target.published:
            raise PublishError(f"公开笔记链接到了未公开笔记 '{target.relative}'")
        fragment = f"#{heading_fragment(heading)}" if heading else ""
        return f"[{alias or target.title}]({route_for(target)}{fragment})"

    def markdown_image_replace(match: re.Match[str]) -> str:
        """Copy and rewrite one local standard Markdown image."""

        alt, raw_target = match.groups()
        target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
        if re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I) or target.startswith("data:"):
            return match.group(0)
        source = resolve_asset(target, note, vault, assets_by_name)
        filename = copy_asset(source, asset_dir, copied)
        return f"![{alt}]({filename})"

    def markdown_note_replace(match: re.Match[str]) -> str:
        """Rewrite one local standard Markdown note link."""

        label, raw_target = match.groups()
        target_text, separator, heading = raw_target.partition("#")
        target = resolve_note(target_text, note, indexes)
        if not target.published:
            raise PublishError(f"公开笔记链接到了未公开笔记 '{target.relative}'")
        fragment = f"#{heading_fragment(heading)}" if separator else ""
        return f"[{label}]({route_for(target)}{fragment})"

    try:
        result = WIKI_RE.sub(wiki_replace, text)
        result = MARKDOWN_IMAGE_RE.sub(markdown_image_replace, result)
        return MARKDOWN_NOTE_RE.sub(markdown_note_replace, result)
    except PublishError as error:
        raise PublishError(f"{note.relative}:{line_number}: {error}") from error


def transform_inline_code_safe(text: str, transform: Any) -> str:
    """Apply a transformation outside matching Markdown inline-code spans."""

    output: list[str] = []
    cursor = 0
    plain_start = 0
    while cursor < len(text):
        if text[cursor] != "`":
            cursor += 1
            continue
        run_end = cursor
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        marker = text[cursor:run_end]
        closing = text.find(marker, run_end)
        if closing < 0:
            cursor = run_end
            continue
        output.append(transform(text[plain_start:cursor]))
        output.append(text[cursor : closing + len(marker)])
        cursor = closing + len(marker)
        plain_start = cursor
    output.append(transform(text[plain_start:]))
    return "".join(output)


def transform_body(
    note: Note,
    vault: Path,
    indexes: tuple[dict[str, Note], dict[str, list[Note]]],
    assets_by_name: dict[str, list[Path]],
    asset_dir: Path,
) -> tuple[str, tuple[Path, ...]]:
    """Transform one note body while preserving fenced and inline code."""

    output: list[str] = []
    fence_marker: str | None = None
    copied: dict[str, Path] = {}
    for offset, line in enumerate(note.body.splitlines(keepends=True)):
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)[0]
            if fence_marker is None:
                fence_marker = marker
            elif fence_marker == marker:
                fence_marker = None
            output.append(line)
            continue
        if fence_marker is not None:
            output.append(line)
            continue
        line_number = note.body_start_line + offset
        transform = partial(
            transform_plain_text,
            note=note,
            line_number=line_number,
            vault=vault,
            indexes=indexes,
            assets_by_name=assets_by_name,
            asset_dir=asset_dir,
            copied=copied,
        )
        output.append(transform_inline_code_safe(line, transform))
    return "".join(output), tuple(copied.values())


def format_date(value: Any, fallback: datetime) -> str:
    """Format supported YAML date values for Hexo front matter."""

    if value is None:
        value = fallback
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d 00:00:00")
    return str(value).strip()


def generated_front_matter(note: Note, now: datetime) -> str:
    """Render the public subset of note properties as Hexo front matter."""

    metadata: dict[str, Any] = {
        "title": note.title,
        "date": format_date(note.metadata.get("date"), now),
    }
    if note.metadata.get("updated") is not None:
        metadata["updated"] = format_date(note.metadata["updated"], now)
    if note.tags:
        metadata["tags"] = note.tags
    if note.categories:
        metadata["categories"] = note.categories
    return "---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + "---\n\n"


def fingerprint(path: Path) -> str:
    """Return a content digest used to detect concurrent Syncthing edits."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_first_publish_date(note: Note, timestamp: datetime) -> None:
    """Atomically insert the first publication date into Vault front matter."""

    text = note.path.read_text(encoding="utf-8-sig")
    lines = text.splitlines(keepends=True)
    closing = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if not lines or lines[0].strip() != "---" or closing is None:
        raise PublishError(f"{note.relative}: 无法回写 date，笔记必须有完整 front matter")
    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    lines.insert(closing, f"date: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}{newline}")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=note.path.parent, delete=False) as handle:
        handle.write("".join(lines))
        temporary = Path(handle.name)
    os.replace(temporary, note.path)


def prepare_export(vault: Path, create_stage: bool = True) -> ExportResult:
    """Validate the Vault and optionally create a combined temporary Hexo source."""

    notes = load_notes(vault)
    published = validate_published(notes)
    missing_dates = tuple(note for note in published if note.metadata.get("date") is None)
    indexes = note_lookup(notes)
    assets_by_name = asset_lookup(vault)
    initial_hashes = {note.path: fingerprint(note.path) for note in notes}
    if not create_stage:
        temporary = CACHE_ROOT / "validation-assets"
        shutil.rmtree(temporary, ignore_errors=True)
        try:
            for note in published:
                transform_body(note, vault, indexes, assets_by_name, temporary / note.slug)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
        verify_fingerprints(initial_hashes)
        return ExportResult(published, missing_dates)

    shutil.rmtree(CACHE_ROOT, ignore_errors=True)
    source_dir = CACHE_ROOT / "source"
    shutil.copytree(ROOT / "source", source_dir)
    posts_dir = source_dir / "_posts"
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    referenced_assets: set[Path] = set()
    for note in published:
        output_path = posts_dir / f"{note.slug}.md"
        asset_dir = posts_dir / note.slug
        if output_path.exists() or asset_dir.exists():
            raise PublishError(f"{note.relative}: slug '{note.slug}' 与现有 Hexo 文章或资源目录冲突")
        body, assets = transform_body(note, vault, indexes, assets_by_name, asset_dir)
        referenced_assets.update(assets)
        output_path.write_text(generated_front_matter(note, now) + body, encoding="utf-8")
    verify_fingerprints(initial_hashes)
    verify_fingerprints({path: fingerprint(path) for path in referenced_assets})
    config_path = CACHE_ROOT / "hexo-override.yml"
    config_path.write_text(
        yaml.safe_dump({"source_dir": str(source_dir), "public_dir": str(ROOT / "public")}, sort_keys=False),
        encoding="utf-8",
    )
    return ExportResult(published, missing_dates, source_dir, config_path)


def verify_fingerprints(expected: dict[Path, str]) -> None:
    """Fail if Syncthing or an editor changed an input during export."""

    changed = [path for path, digest in expected.items() if not path.exists() or fingerprint(path) != digest]
    if changed:
        names = ", ".join(str(path) for path in changed)
        raise PublishError(f"导出期间文件发生变化，请等待同步完成后重试: {names}")


def print_summary(result: ExportResult) -> None:
    """Print the exact public notes and routes for review."""

    print(f"将发布 {len(result.notes)} 篇 Obsidian 笔记:")
    for note in result.notes:
        suffix = " [首次发布时写入 date]" if note in result.missing_dates else ""
        print(f"  - {note.relative} -> {route_for(note)}{suffix}")


def hexo_config_args(config_path: Path) -> list[str]:
    """Return Hexo's merged configuration command arguments."""

    return ["--config", f"{ROOT / '_config.yml'},{config_path}"]


def run_command(command: list[str]) -> None:
    """Run a subprocess from the repository and propagate failures."""

    subprocess.run(command, cwd=ROOT, check=True)


def build_site(result: ExportResult) -> None:
    """Clean and generate Hexo output from the combined temporary source."""

    if result.config_path is None:
        raise PublishError("内部错误：导出结果缺少临时 Hexo 配置")
    run_command(["npx", "--no-install", "hexo", "clean"])
    run_command(["npx", "--no-install", "hexo", "generate", *hexo_config_args(result.config_path)])


def confirm_deploy(assume_yes: bool) -> None:
    """Require an explicit interactive confirmation before external deployment."""

    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise PublishError("非交互环境必须显式传入 --yes 才能部署")
    answer = input("确认公开以上笔记并部署到 GitHub Pages？[y/N] ").strip().casefold()
    if answer not in {"y", "yes"}:
        raise PublishError("已取消部署")


def execute(args: argparse.Namespace) -> None:
    """Execute the selected validation, build, preview, or deployment workflow."""

    vault = args.vault.expanduser().resolve()
    if not vault.is_dir():
        raise PublishError(f"Vault 不存在或不是目录: {vault}")
    if args.command == "check":
        result = prepare_export(vault, create_stage=False)
        print_summary(result)
        print("检查通过，未修改 Vault 或博客输出。")
        return

    if args.command == "deploy":
        preview = prepare_export(vault, create_stage=False)
        print_summary(preview)
        confirm_deploy(args.yes)
        timestamp = datetime.now(ZoneInfo("Asia/Shanghai"))
        for note in preview.missing_dates:
            write_first_publish_date(note, timestamp)

    result = prepare_export(vault)
    print_summary(result)
    if args.command == "serve":
        if result.config_path is None:
            raise PublishError("内部错误：预览缺少临时 Hexo 配置")
        run_command(
            ["npx", "--no-install", "hexo", "server", "--port", str(args.port), *hexo_config_args(result.config_path)]
        )
        return
    build_site(result)
    if args.command == "deploy":
        if result.config_path is None:
            raise PublishError("内部错误：部署缺少临时 Hexo 配置")
        run_command(["npx", "--no-install", "hexo", "deploy", *hexo_config_args(result.config_path)])


def parse_args() -> argparse.Namespace:
    """Parse the stable command-line interface used by npm scripts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("check", "build", "serve", "deploy"), help="publishing workflow to execute"
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path(os.environ.get("OBSIDIAN_VAULT", Path.home() / "Knowledge")),
        help="Obsidian Vault path (default: OBSIDIAN_VAULT or ~/Knowledge)",
    )
    parser.add_argument("--port", type=int, default=4000, help="preview server port")
    parser.add_argument("--yes", action="store_true", help="deploy without an interactive confirmation")
    return parser.parse_args()


def main() -> int:
    """Run the publisher and render expected failures without a traceback."""

    try:
        try:
            execute(parse_args())
        except (PublishError, subprocess.CalledProcessError) as error:
            print(f"发布失败: {error}", file=sys.stderr)
            return 1
        return 0
    finally:
        shutil.rmtree(CACHE_ROOT, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
