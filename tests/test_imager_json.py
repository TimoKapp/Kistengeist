import hashlib
import importlib.util
import lzma
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("mij", os.path.join(REPO, "tools", "make_imager_json.py"))
mij = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mij)


def test_hashes_use_extracted_image(tmp_path):
    raw = os.urandom(100_000)
    image = tmp_path / "x.img.xz"
    image.write_bytes(lzma.compress(raw))
    data = mij.build(str(image), "https://example.invalid/x.img.xz", "v1", "2026-10-16")
    entry = data["os_list"][0]
    assert entry["extract_size"] == len(raw)
    assert entry["extract_sha256"] == hashlib.sha256(raw).hexdigest()
    assert entry["image_download_size"] == image.stat().st_size
    assert entry["devices"] == ["pi4-64bit"]
    for key in ("name", "description", "icon", "url", "release_date"):
        assert entry[key]


def test_zip_image(tmp_path):
    import zipfile

    raw = os.urandom(50_000)
    archive = tmp_path / "kistengeist.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("kistengeist.img", raw)
    entry = mij.build(str(archive), "https://example.invalid/c.zip", "v1", "2026-10-16")["os_list"][0]
    assert entry["extract_size"] == len(raw)
    assert entry["extract_sha256"] == hashlib.sha256(raw).hexdigest()
