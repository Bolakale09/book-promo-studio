"""Shared fixtures. Every test works in its own temporary data folder - never the real library - and never calls
a paid API or the network."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def data(tmp_path, monkeypatch):
    from promo import config, jobs
    paths = {"DATA": tmp_path, "BOOKS_DIR": tmp_path / "books", "REFS_DIR": tmp_path / "references",
             "BLUEPRINTS_DIR": tmp_path / "blueprints", "PROJECTS_DIR": tmp_path / "projects",
             "BROLL_DIR": tmp_path / "broll", "MUSIC_DIR": tmp_path / "music",
             "BUDGET_LOG": tmp_path / "budget.jsonl", "BUDGET_FILE": tmp_path / "budget.json"}
    for name, p in paths.items():
        monkeypatch.setattr(config, name, p)
        if name.endswith("_DIR"):
            p.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    return tmp_path


@pytest.fixture
def book(data):
    from promo import book as bk
    b = bk.new_book("The Salt Garden")
    b.update(author="Jane Author", blurb="A love story.", genre="fiction")
    bk.save(b)
    return b


@pytest.fixture
def make_render(data):
    """Create a fake finished video (render.json only) for a book."""
    from promo import config

    def make(book_id: str, n: int, **fields) -> Path:
        d = config.PROJECTS_DIR / book_id / f"2026010{n}-000000-v{n}"
        d.mkdir(parents=True, exist_ok=True)
        meta = {"created": f"2026-01-0{n}T10:00:00", "book": book_id, "seconds": 20.0, "cost": 0.1,
                "file": "final.mp4", "draft": False,
                "variant": {"name": f"Video {n}", "hook_type": "POV", "angle": "trope",
                            "scenes": [{"overlay": "hook", "visual": "stock"}]}, **fields}
        (d / "render.json").write_text(json.dumps(meta), encoding="utf-8")
        return d
    return make
