import json
import pytest
from agent.models import Conference
from memory import store

@pytest.fixture(autouse=True)
def tmp_memory(tmp_path, monkeypatch):
    mem = str(tmp_path / "test_memory.json")
    monkeypatch.setattr(store, "MEMORY_FILE", mem)

def _make_conf(**kwargs) -> Conference:
    defaults = dict(
        name="Test Conference", acronym="TC", url="https://test.com",
        year=2026, relevance_score=8, relevance_reason="Good match"
    )
    return Conference(**{**defaults, **kwargs})

def test_empty_store_returns_empty_set():
    assert store.get_seen_acronyms() == set()

def test_mark_added_persists():
    conf = _make_conf(acronym="ICML")
    store.mark_added(conf, "event_abc")
    assert "ICML2026" in store.get_seen_acronyms()

def test_no_duplicate_acronyms():
    conf = _make_conf(acronym="NeurIPS")
    store.mark_added(conf, "ev1")
    store.mark_added(conf, "ev2")
    seen = store.get_seen_acronyms()
    assert len([s for s in seen if "NEURIPS" in s]) == 1

def test_record_run():
    store.record_run(conferences_added=5, cost_usd=0.03)
    history = store.get_run_history()
    assert len(history) == 1
    assert history[0]["conferences_added"] == 5
