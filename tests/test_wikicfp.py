from unittest.mock import patch, MagicMock
from tools.wikicfp import search_wikicfp

MOCK_HTML = """<html><body><table class="gglu">
  <tr><th>Acronym</th><th>Name</th><th>When</th><th>Where</th><th>Deadline</th></tr>
  <tr>
    <td><a href="/cfp/123">ICML 2026</a></td>
    <td>International Conference on Machine Learning</td>
    <td>Jul 13-19, 2026</td><td>Vienna, Austria</td><td>Jan 31, 2026</td>
  </tr>
</table></body></html>"""

def test_returns_list():
    with patch("tools.wikicfp.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.text = MOCK_HTML
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp
        with patch("tools.wikicfp.time.sleep"):
            results = search_wikicfp("machine learning")
    assert isinstance(results, list)
    assert len(results) == 1
    assert "ICML" in results[0]["acronym"]

def test_returns_empty_on_error():
    with patch("tools.wikicfp.httpx.get", side_effect=Exception("timeout")):
        results = search_wikicfp("machine learning")
    assert results == []
