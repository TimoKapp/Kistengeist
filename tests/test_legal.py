import os

import kistengeist_legal as legal
from conftest import REPO


def data():
    return legal.load()


def test_structure_complete():
    d = data()
    ids = {s["id"] for s in d["sections"]}
    assert {"projekt", "ki", "lokal", "dritte", "verantwortung", "sicherheit", "lizenzen", "haftung",
            "loeschen"} <= ids
    assert legal.confirmation_ids(d) == ["read", "age", "thirdparty", "nowarranty"]
    text = " ".join(" ".join(s["body"]) for s in d["sections"])
    for must in ("KI", "Anthropic Ireland", "18 Jahren", "DSGVO", "ohne Gewähr", "keine Daten",
                 "Konto ist persönlich", "§§ 521, 599 BGB", "Leben, Körper oder Gesundheit", "credentials.json"):
        assert must in text, must


def test_accepted_requires_all_checks_and_version():
    d = data()
    good = {"version": legal.version(d), "checks": {cid: True for cid in legal.confirmation_ids(d)}}
    assert legal.accepted(d, good)
    assert not legal.accepted(d, {**good, "version": "alt"})
    assert not legal.accepted(d, {**good, "checks": {**good["checks"], "age": False}})
    assert not legal.accepted(d, {**good, "checks": {**good["checks"], "age": "true"}})
    assert not legal.accepted(d, None)
    assert not legal.accepted(d, {"version": legal.version(d)})


def test_inline_html_is_safe():
    raw = '<script>x</script> **fett** [Link](https://example.org/a?b=1&c=2) [böse](javascript:alert(1))'
    out = legal.inline_html(raw)
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<strong>fett</strong>" in out
    assert 'href="https://example.org/a?b=1&amp;c=2"' in out
    assert "javascript:" not in out.split("böse")[0] and "href=\"javascript" not in out


def test_record_has_no_personal_data():
    rec = legal.record(data(), "2026-10-17T10:00:00+0200")
    assert rec.startswith("VERSION=") and "BESTAETIGT=read,age,thirdparty,nowarranty" in rec


def test_repo_markdown_in_sync():
    with open(os.path.join(REPO, "RECHTLICHES.md"), encoding="utf-8") as fh:
        assert fh.read() == legal.to_markdown(data()), "tools/make_legal_md.py ausführen"


def test_html_renders():
    html = legal.to_html(data())
    assert html.startswith("<!doctype html>") and "Datenschutz" in html


def test_empty_confirmations_never_accepted():
    d = {**data(), "confirmations": []}
    assert not legal.accepted(d, {"version": legal.version(d), "checks": {}})
