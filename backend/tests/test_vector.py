"""Real vector memory tests: TF-IDF correctness + agent memory persistence."""
import pytest

from app.storage.vector import TfidfMemory, hash_embedding, build_memory


@pytest.fixture
def memory():
    return TfidfMemory()


async def test_tfidf_ranks_relevant_first(memory):
    await memory.upsert("The user wants a modern hero section with a big heading", {"canvas_id": "c1"})
    await memory.upsert("Pricing should start at seven dollars per month", {"canvas_id": "c1"})
    await memory.upsert("Add a footer with the copyright text", {"canvas_id": "c1"})

    hits = await memory.search("add hero heading", top_k=3, meta={"canvas_id": "c1"})
    assert hits and hits[0]["text"].startswith("The user wants a modern hero")

    pricing = await memory.search("monthly price", top_k=3)
    assert "seven dollars" in pricing[0]["text"]


async def test_tfidf_scoped_by_canvas(memory):
    a = await memory.upsert("hero section for canvas A", {"canvas_id": "a"})
    b = await memory.upsert("hero section for canvas B", {"canvas_id": "b"})
    scoped = await memory.search("hero section", meta={"canvas_id": "a"})
    assert {s["id"] for s in scoped} == {a}
    all_hits = await memory.search("hero section")
    assert {s["id"] for s in all_hits} == {a, b}


async def test_list_items(memory):
    await memory.upsert("first note", {"kind": "note"})
    await memory.upsert("second note", {"kind": "note"})
    items = await memory.list_items(meta={"kind": "note"})
    assert len(items) == 2


def test_hash_embedding_is_deterministic():
    v1 = hash_embedding("modern hero section")
    v2 = hash_embedding("modern hero section")
    assert v1 == v2
    assert len(v1) == 256
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-6  # normalized


def test_build_memory_defaults_to_tfidf():
    mem = build_memory()
    assert isinstance(mem, TfidfMemory)
