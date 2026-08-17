"""End-to-end API flow against the real app: embedded postgres + mock
providers. Covers the golden path a user takes in the UI."""

import asyncio
import json

BENCHMARK_DOC = """# Aurora Benchmark Report 2024

Published 2024-03-15.

## Results

In 2024, Aurora achieved 87 percent recall at 10 with a median latency of
18 milliseconds on the SIFT-1B dataset.

## Retention Policy

The 2024 retention policy keeps snapshots for 30 days and write-ahead logs
for 7 days. Backups are deleted weekly on Sundays.
"""

FAQ_DOC = """# Aurora FAQ

Error code AUR-1002 means dimension mismatch: the query vector dimension
does not match the collection.

The default replication factor is 3, so one node loss causes no data loss.
"""


async def create_collection(client, name: str = "Test KB") -> dict:
    response = await client.post(
        "/api/v1/collections",
        json={"name": name, "embedding_provider": "mock", "chunking_strategy": "markdown"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def upload_and_wait(client, collection_id: str, filename: str, content: str) -> dict:
    response = await client.post(
        f"/api/v1/collections/{collection_id}/documents",
        files={"file": (filename, content.encode(), "text/markdown")},
    )
    assert response.status_code == 201, response.text
    document = response.json()["document"]

    for _ in range(200):
        check = await client.get(f"/api/v1/documents/{document['id']}")
        body = check.json()
        if body["status"] in ("completed", "failed"):
            assert body["status"] == "completed", f"ingestion failed: {body.get('error')}"
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("ingestion did not finish in time")


async def test_health_and_ready(client):
    health = await client.get("/api/v1/health")
    assert health.status_code == 200
    ready = await client.get("/api/v1/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["checks"]["database"]["ok"] is True


async def test_providers_include_mock(client):
    response = await client.get("/api/v1/providers")
    assert response.status_code == 200
    providers = {p["name"]: p for p in response.json()}
    assert providers["mock"]["configured"] is True
    config = await client.get("/api/v1/config")
    assert config.status_code == 200


async def test_collection_crud(client):
    created = await create_collection(client, "CRUD KB")
    collection_id = created["id"]
    assert created["embedding_provider"] == "mock"

    listing = await client.get("/api/v1/collections")
    assert any(c["id"] == collection_id for c in listing.json())

    updated = await client.patch(
        f"/api/v1/collections/{collection_id}",
        json={"description": "updated description"},
    )
    assert updated.json()["description"] == "updated description"

    duplicate = await client.post(
        "/api/v1/collections", json={"name": "CRUD KB", "embedding_provider": "mock"}
    )
    assert duplicate.status_code == 409

    deleted = await client.delete(f"/api/v1/collections/{collection_id}")
    assert deleted.status_code == 200
    missing = await client.get(f"/api/v1/collections/{collection_id}")
    assert missing.status_code == 404


async def test_upload_ingest_and_chunks(client):
    collection = await create_collection(client, "Ingest KB")
    document = await upload_and_wait(client, collection["id"], "benchmark.md", BENCHMARK_DOC)
    assert document["chunk_count"] > 0

    chunks = await client.get(f"/api/v1/documents/{document['id']}/chunks")
    assert chunks.status_code == 200
    contents = " ".join(c["content"] for c in chunks.json())
    assert "87 percent recall" in contents

    # identical re-upload is deduplicated, not re-ingested
    again = await client.post(
        f"/api/v1/collections/{collection['id']}/documents",
        files={"file": ("benchmark.md", BENCHMARK_DOC.encode(), "text/markdown")},
    )
    assert again.status_code == 201
    assert again.json()["is_new_content"] is False


async def test_upload_rejects_unsupported_type(client):
    collection = await create_collection(client, "Reject KB")
    response = await client.post(
        f"/api/v1/collections/{collection['id']}/documents",
        files={"file": ("virus.exe", b"MZbinary", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"


async def test_chat_returns_cited_answer(client):
    collection = await create_collection(client, "Chat KB")
    await upload_and_wait(client, collection["id"], "benchmark.md", BENCHMARK_DOC)
    await upload_and_wait(client, collection["id"], "faq.md", FAQ_DOC)

    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "What recall did Aurora achieve in 2024?",
            "collection_ids": [collection["id"]],
            "mode": "balanced",
            "provider": "mock",
            "debug": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["abstained"] is False
    assert "[1]" in body["answer"]
    assert body["citations"], "expected at least one citation"
    assert body["evidence"]
    assert body["confidence"]["score"] > 0
    assert body["strategy"]
    assert body["debug_steps"], "debug mode should include pipeline steps"

    # trace persisted and inspectable
    trace = await client.get(f"/api/v1/retrieval/{body['trace_id']}")
    assert trace.status_code == 200
    step_names = [s["name"] for s in trace.json()["steps"]]
    assert "query_analysis" in step_names

    # conversation persisted with messages and citations
    conversation = await client.get(f"/api/v1/conversations/{body['conversation_id']}")
    detail = conversation.json()
    assert len(detail["messages"]) == 2
    assistant = detail["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["citations"]

    # follow-up in the same conversation
    follow = await client.post(
        "/api/v1/chat",
        json={
            "message": "And what about the retention policy?",
            "collection_ids": [collection["id"]],
            "conversation_id": body["conversation_id"],
            "mode": "balanced",
            "provider": "mock",
        },
    )
    assert follow.status_code == 200
    assert follow.json()["conversation_id"] == body["conversation_id"]

    # export
    export = await client.get(
        f"/api/v1/conversations/{body['conversation_id']}/export",
        params={"format": "markdown"},
    )
    assert export.status_code == 200
    assert "What recall did Aurora achieve" in export.text


async def test_chat_abstains_on_empty_collection(client):
    collection = await create_collection(client, "Empty KB")
    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "What is the meaning of life?",
            "collection_ids": [collection["id"]],
            "mode": "fast",
            "provider": "mock",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["abstained"] is True
    assert body["citations"] == []


async def test_chat_stream_sse(client):
    collection = await create_collection(client, "Stream KB")
    await upload_and_wait(client, collection["id"], "benchmark.md", BENCHMARK_DOC)

    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={
            "message": "What was the median latency in 2024?",
            "collection_ids": [collection["id"]],
            "mode": "fast",
            "provider": "mock",
        },
    ) as response:
        assert response.status_code == 200
        current_event = ""
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                payload = json.loads(line.split(":", 1)[1].strip())
                events.append((current_event, payload))

    kinds = [k for k, _ in events]
    assert "token" in kinds
    assert "status" in kinds
    assert "step" in kinds
    assert "final" in kinds
    step_names = [p["name"] for k, p in events if k == "step"]
    assert "query_analysis" in step_names
    final = next(p for k, p in events if k == "final")
    assert final["answer"]
    assert final["debug_steps"]
    streamed_text = "".join(p.get("text", "") for k, p in events if k == "token")
    assert streamed_text.strip()


async def test_traces_listing(client):
    collection = await create_collection(client, "Trace KB")
    await upload_and_wait(client, collection["id"], "faq.md", FAQ_DOC)
    await client.post(
        "/api/v1/chat",
        json={
            "message": "What does AUR-1002 mean?",
            "collection_ids": [collection["id"]],
            "mode": "fast",
            "provider": "mock",
        },
    )
    traces = await client.get("/api/v1/retrieval/traces")
    assert traces.status_code == 200
    assert len(traces.json()) >= 1
