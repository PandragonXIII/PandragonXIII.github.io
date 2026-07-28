"""Tests for the Obsidian-to-Hexo publishing boundary."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import publisher.obsidian_publish as publisher
from publisher.obsidian_publish import (
    PublishError,
    asset_lookup,
    load_notes,
    note_lookup,
    prepare_export,
    route_for,
    transform_body,
    validate_published,
    write_first_publish_date,
)


def write_note(vault: Path, relative: str, front_matter: str, body: str = "") -> Path:
    """Create a UTF-8 note fixture with explicit front matter."""

    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front_matter}\n---\n{body}", encoding="utf-8")
    return path


def transform_note(vault: Path, relative: str, output: Path) -> str:
    """Load and transform one fixture note into Markdown."""

    notes = load_notes(vault)
    published = validate_published(notes)
    note = next(item for item in published if item.relative.as_posix() == relative)
    body, _ = transform_body(note, vault, note_lookup(notes), asset_lookup(vault), output)
    return body


def test_public_link_and_image_are_exported(tmp_path: Path) -> None:
    """Published wikilinks become routes and image embeds become post assets."""

    vault = tmp_path / "vault"
    image = vault / "attachments" / "diagram.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"PNG fixture")
    write_note(vault, "Target.md", "publish: true\nslug: target\ncategories: [Research]", "Target")
    write_note(
        vault,
        "Source.md",
        "publish: true\nslug: source",
        "See [[Target|the target]].\n![[diagram.png]]\n",
    )

    output = tmp_path / "assets"
    body = transform_note(vault, "Source.md", output)

    assert "[the target](/Research/target/)" in body
    assert "![diagram](diagram.png)" in body
    assert (output / "diagram.png").read_bytes() == b"PNG fixture"


def test_private_link_stops_export(tmp_path: Path) -> None:
    """A public note cannot link to a note without publish: true."""

    vault = tmp_path / "vault"
    write_note(vault, "Private.md", "slug: private", "Secret")
    write_note(vault, "Public.md", "publish: true\nslug: public", "[[Private]]")

    with pytest.raises(PublishError, match="未公开笔记"):
        transform_note(vault, "Public.md", tmp_path / "assets")


def test_code_spans_and_fences_are_not_transformed(tmp_path: Path) -> None:
    """Obsidian-like syntax inside code remains byte-for-byte content."""

    vault = tmp_path / "vault"
    write_note(
        vault,
        "Code.md",
        "publish: true\nslug: code",
        "`[[Missing]]`\n```text\n[[Missing]]\n```\n",
    )

    body = transform_note(vault, "Code.md", tmp_path / "assets")

    assert body == "`[[Missing]]`\n```text\n[[Missing]]\n```\n"


def test_duplicate_slugs_ignore_case(tmp_path: Path) -> None:
    """Case-insensitive slug collisions fail before content conversion."""

    vault = tmp_path / "vault"
    write_note(vault, "One.md", "publish: true\nslug: duplicate")
    write_note(vault, "Two.md", "publish: true\nslug: DUPLICATE")

    with pytest.raises(PublishError, match="重复"):
        validate_published(load_notes(vault))


def test_note_paths_must_be_unique_on_windows(tmp_path: Path) -> None:
    """Vault paths differing only by case fail before links are resolved."""

    vault = tmp_path / "vault"
    write_note(vault, "Folder/Note.md", "publish: true\nslug: first")
    write_note(vault, "folder/note.md", "publish: true\nslug: second")

    with pytest.raises(PublishError, match="Windows 忽略大小写"):
        note_lookup(load_notes(vault))


def test_first_publish_date_is_inserted_without_rewriting_body(tmp_path: Path) -> None:
    """First deployment adds a stable date while preserving note content."""

    vault = tmp_path / "vault"
    path = write_note(vault, "Post.md", "publish: true\nslug: post", "Body\n")
    note = load_notes(vault)[0]
    timestamp = datetime(2026, 7, 28, 18, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    write_first_publish_date(note, timestamp)

    text = path.read_text(encoding="utf-8")
    assert "date: 2026-07-28 18:30:00\n---\nBody\n" in text
    assert load_notes(vault)[0].metadata["date"] == timestamp.replace(tzinfo=None)


def test_zero_published_notes_is_valid(tmp_path: Path) -> None:
    """A Vault with only private notes still permits legacy Hexo builds."""

    vault = tmp_path / "vault"
    write_note(vault, "Private.md", "tags: [private]", "Private")

    result = prepare_export(vault, create_stage=False)

    assert result.notes == ()
    assert result.missing_dates == ()


def test_route_uses_category_hierarchy(tmp_path: Path) -> None:
    """Published routes preserve the selected Hexo category hierarchy."""

    vault = tmp_path / "vault"
    write_note(vault, "Post.md", "publish: true\nslug: stable\ncategories: [Notes, AI]")
    note = validate_published(load_notes(vault))[0]

    assert route_for(note) == "/Notes/AI/stable/"


def test_prepare_export_stages_a_generated_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A public Vault note is added only to the temporary combined Hexo source."""

    project = tmp_path / "site"
    (project / "source" / "_posts").mkdir(parents=True)
    vault = tmp_path / "vault"
    source_note = write_note(
        vault,
        "Published.md",
        "publish: true\nslug: published\ncategories: [Notes]",
        "Public body\n",
    )
    monkeypatch.setattr(publisher, "ROOT", project)
    monkeypatch.setattr(publisher, "CACHE_ROOT", project / ".cache" / "obsidian-publish")

    result = prepare_export(vault)

    assert result.source_dir is not None
    generated = result.source_dir / "_posts" / "published.md"
    text = generated.read_text(encoding="utf-8")
    assert "title: Published" in text
    assert "date:" in text
    assert text.endswith("Public body\n")
    assert source_note.read_text(encoding="utf-8").count("date:") == 0
    assert result.config_path is not None and result.config_path.exists()
