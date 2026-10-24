from softwiki.extraction.processor import _extraction_windows


def test_windows_spread_across_long_text(monkeypatch):
    monkeypatch.setenv("EXTRACTION_WINDOW_CHARS", "1000")
    monkeypatch.setenv("EXTRACTION_WINDOW_OVERLAP", "100")
    monkeypatch.setenv("EXTRACTION_MAX_WINDOWS", "4")
    text = "".join(str(i % 10) for i in range(10000))
    windows = _extraction_windows(text)
    assert len(windows) == 4
    assert all(len(window) <= 1000 for window in windows)
    assert windows[0].startswith("0")
    assert windows[-1].endswith(text[-1])


def test_small_text_single_window(monkeypatch):
    monkeypatch.setenv("EXTRACTION_WINDOW_CHARS", "1000")
    assert _extraction_windows("hello") == ["hello"]
