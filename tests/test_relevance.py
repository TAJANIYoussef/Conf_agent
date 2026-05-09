import json
from unittest.mock import patch, MagicMock
from tools.relevance import batch_score_conferences

MOCK_RESPONSE = [
    {
        "name": "ICML 2026", "acronym": "ICML", "url": "https://icml.cc",
        "abstract_deadline": "2026-08-31", "full_paper_deadline": "2026-09-07",
        "venue": "Vienna, Austria",
        "year": 2026, "relevance_score": 9, "relevance_reason": "Top ML venue"
    }
]

def test_batch_score_returns_conferences():
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=json.dumps(MOCK_RESPONSE))]
    mock_resp.usage.input_tokens = 500
    mock_resp.usage.output_tokens = 200

    with patch("tools.relevance.client.messages.create", return_value=mock_resp):
        result = batch_score_conferences(
            raw_candidates=[{"acronym": "ICML", "name": "ICML 2026",
                             "url": "https://icml.cc", "deadline": "Feb 2026",
                             "when": "Jul 2026", "where": "Vienna"}],
            thesis_keywords=["imbalanced learning"],
            thesis_summary="PhD thesis on imbalanced tabular data.",
            seen_acronyms=set(),
        )
    assert len(result) == 1
    assert result[0].acronym == "ICML"
    assert result[0].relevance_score == 9

def test_skips_seen_acronyms():
    result = batch_score_conferences(
        raw_candidates=[{"acronym": "ICML", "when": "", "deadline": "2026"}],
        thesis_keywords=["imbalanced"],
        thesis_summary="Summary.",
        seen_acronyms={"ICML2026"},
    )
    assert result == []
