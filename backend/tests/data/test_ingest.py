import csv
import gzip
import io
import json
import sqlite3

import pytest
from PIL import Image

from brickwise.data import ingest, products


def _jpeg(size=(800, 600), color=(10, 20, 30), mode="RGB", fmt="JPEG"):
    b = io.BytesIO()
    Image.new(mode, size, color if mode == "RGB" else color + (128,)).save(b, fmt)
    return b.getvalue()


def _gz(rows, fields):
    b = io.StringIO()
    w = csv.DictWriter(b, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
    return gzip.compress(b.getvalue().encode())


def make_fixture(n_per_theme=12):
    themes = [
        {"id": 1, "name": "Star Wars", "parent_id": ""},
        {"id": 2, "name": "Episode I", "parent_id": "1"},
        {"id": 3, "name": "UCS", "parent_id": "2"},
        {"id": 10, "name": "City", "parent_id": ""},
        {"id": 20, "name": "Technic", "parent_id": ""},
        {"id": 30, "name": "Gear", "parent_id": ""},
    ]
    sets = []
    for tid, tag in [(3, "SW"), (10, "CT"), (20, "TC"), (30, "GR")]:
        for i in range(n_per_theme):
            sets.append(dict(set_num=f"{tag}{i}-1", name=f"{tag} set {i}", year=2005 + i,
                             theme_id=tid, num_parts=20 + i, img_url=f"http://x/{tag}{i}.jpg"))
    sets += [
        dict(set_num="BAD1-1", name="", year=2010, theme_id=10, num_parts=50, img_url="http://x/b1.jpg"),
        dict(set_num="BAD2-1", name="zero", year=2010, theme_id=10, num_parts=0, img_url="http://x/b2.jpg"),
        dict(set_num="BAD3-1", name="small", year=2010, theme_id=10, num_parts=3, img_url="http://x/b3.jpg"),
        dict(set_num="BAD4-1", name="noimg", year=2010, theme_id=10, num_parts=99, img_url=""),
        dict(set_num="BAD5-1", name="notheme", year=2010, theme_id=999, num_parts=99, img_url="http://x/b5.jpg"),
        dict(set_num="CT0-1", name="dup", year=2010, theme_id=10, num_parts=99, img_url="http://x/d.jpg"),
    ]
    return themes, sets


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BRICKWISE_DATA_DIR", str(tmp_path))
    themes, sets = make_fixture()
    calls = []
    fail = set()

    def fake_fetch(url, *a, **k):
        calls.append(url)
        if url.endswith("sets.csv.gz"):
            return _gz(sets, ["set_num", "name", "year", "theme_id", "num_parts", "img_url"])
        if url.endswith("themes.csv.gz"):
            return _gz(themes, ["id", "name", "parent_id"])
        if any(f in url for f in fail):
            raise RuntimeError("boom")
        if "SW3" in url:
            return b"not an image"
        return _jpeg()

    monkeypatch.setattr(ingest, "fetch_bytes", fake_fetch)
    return tmp_path, calls, fail


def test_root_theme_walks_parents():
    idx = ingest.build_theme_index([{"id": "1", "name": "A", "parent_id": ""},
                                    {"id": "2", "name": "B", "parent_id": "1"},
                                    {"id": "3", "name": "C", "parent_id": "2"}])
    assert ingest.root_theme(idx, 3) == "A"
    assert ingest.root_theme(idx, 1) == "A"


def test_root_theme_cycle_safe():
    idx = {1: {"name": "A", "parent": 2}, 2: {"name": "B", "parent": 1}}
    assert ingest.root_theme(idx, 1) in ("A", "B", None)


def test_clean_sets_reasons():
    themes, sets = make_fixture()
    idx = ingest.build_theme_index([{k: str(v) for k, v in t.items()} for t in themes])
    clean, drops = ingest.clean_sets([{k: str(v) for k, v in s.items()} for s in sets], idx)
    assert drops["empty name"] == 1
    assert drops["zero/invalid parts"] == 1
    assert drops["num_parts < 10"] == 1
    assert drops["missing img_url"] == 1
    assert drops["unknown theme"] == 1
    assert drops["duplicate set_num"] == 1
    assert drops["excluded theme (Gear)"] == 12
    assert {c["root_theme"] for c in clean} == {"Star Wars", "City", "Technic"}
    assert next(c for c in clean if c["set_num"] == "SW0-1")["theme"] == "UCS"


def _cands(themes, n):
    return [dict(set_num=f"{t}{i}", root_theme=t, year=2010, name="x") for t, k in zip(themes, n) for i in range(k)]


def test_select_deterministic_capped_and_diverse():
    cands = _cands(list("abcdefghijklmnopqrstuvwxyz"), [500] * 20 + [40, 20, 10, 8, 6, 5])
    s1 = ingest.select_sets(cands, 100)
    s2 = ingest.select_sets(list(reversed(cands)), 100)
    assert s1 == s2 and len(s1) == 100
    from collections import Counter
    c = Counter(x["root_theme"] for x in s1)
    assert len(c) == ingest.MAX_THEMES and max(c.values()) <= 8 and min(c.values()) >= 5


def test_select_excludes_and_prefers_modern():
    cands = [dict(set_num=f"o{i}", root_theme="a", year=1990, name="x") for i in range(10)] + \
            [dict(set_num=f"n{i}", root_theme="a", year=2015, name="x") for i in range(10)]
    sel = ingest.select_sets(cands, 5)
    assert all(s["set_num"].startswith("n") for s in sel)
    sel2 = ingest.select_sets(cands, 5, exclude={s["set_num"] for s in sel})
    assert not ({s["set_num"] for s in sel} & {s["set_num"] for s in sel2})


def test_process_image_resizes_and_rgb(tmp_path):
    out = tmp_path / "a.jpg"
    size = ingest.process_image(_jpeg((1200, 600)), out)
    assert max(size) == 512
    with Image.open(out) as im:
        assert im.mode == "RGB" and im.format == "JPEG" and max(im.size) == 512


def test_process_image_png_alpha_and_corrupt(tmp_path):
    out = tmp_path / "p.jpg"
    ingest.process_image(_jpeg((50, 50), mode="RGBA", fmt="PNG"), out)
    with Image.open(out) as im:
        assert im.mode == "RGB"
    with pytest.raises(Exception):
        ingest.process_image(b"garbage", tmp_path / "g.jpg")
    assert not (tmp_path / "g.jpg").exists()


def test_full_run_with_topup_and_idempotence(env):
    tmp, calls, fail = env
    rep = ingest.run(limit=20, seed=1)
    assert rep["products"] == 20 and rep["images"] == 20
    assert "SW3-1" in rep["image_failures"]          # corrupt image dropped
    rows = products.load_products()
    assert len(rows) == 20 and "SW3-1" not in {r["set_num"] for r in rows}
    assert all((tmp / "images" / r["image_file"]).exists() for r in rows)
    assert {"set_num", "name", "year", "theme_id", "theme", "root_theme", "num_parts",
            "img_url", "image_file"} == set(rows[0])
    assert json.loads((tmp / "ingest_report.json").read_text())["products"] == 20
    n_calls = len(calls)
    rep2 = ingest.run(limit=20, seed=1)              # idempotent: no re-download of ok files
    assert [r["set_num"] for r in products.load_products()] == [r["set_num"] for r in rows]
    new = calls[n_calls:]
    assert all("SW3" in u for u in new)              # only the previously-failed one retried
    con = sqlite3.connect(tmp / "brickwise.db")
    assert con.execute("select count(*) from products").fetchone()[0] == 20
    assert rep2["products"] == 20


def test_offline_sample(tmp_path, monkeypatch):
    monkeypatch.setenv("BRICKWISE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ingest, "fetch_bytes", lambda *a, **k: pytest.fail("network used"))
    rep = ingest.main(["--offline-sample"])
    assert rep == 0
    rows = products.load_products()
    assert len(rows) == 24 and len({r["root_theme"] for r in rows}) == 4
    assert all((tmp_path / "images" / r["image_file"]).exists() for r in rows)
    assert (tmp_path / "ingest_report.json").exists()


def test_stale_products_removed_but_rated_kept(env):
    tmp, _, _ = env
    ingest.run(limit=20, seed=1)
    con = sqlite3.connect(tmp / "brickwise.db")
    keep = products.load_products()[0]["set_num"]
    con.execute("insert into feedback(set_num, rating) values (?,1)", (keep,))
    con.commit(); con.close()
    ingest.run(limit=10, seed=2)
    ids = {r["set_num"] for r in products.load_products()}
    assert keep in ids


def test_load_products_missing_db(tmp_path):
    assert products.load_products(tmp_path / "nope.db") == []
