from scraper.stamp import stamp


def test_stamp_versions_local_assets_by_content(tmp_path):
    (tmp_path / "app.js").write_text("one")
    (tmp_path / "styles.css").write_text("css")
    page = tmp_path / "index.html"
    page.write_text('<link href="styles.css"><script src="app.js"></script>'
                    '<link href="https://fonts.googleapis.com/x.css">')

    stamp(tmp_path)
    first = page.read_text()
    (tmp_path / "app.js").write_text("two")
    stamp(tmp_path)
    second = page.read_text()

    assert 'src="app.js?v=' in first and 'href="styles.css?v=' in first
    assert first.count("?v=") == 2  # the external stylesheet is left alone
    css = first.split('href="styles.css')[1].split('"')[0]
    assert css in second  # unchanged file keeps its URL, so it stays cached
    assert first.split('src="app.js')[1].split('"')[0] != second.split('src="app.js')[1].split('"')[0]
    assert second.count("?v=") == 2  # re-stamping replaces the version instead of appending
