from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes
from app.services.copilot import WorkflowCopilot
from app.services.evidence import EvidenceIngestionService
from app.services.store import WorkflowStore
from main import app


def _create_plan(client: TestClient) -> str:
    response = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a customer-facing API release with documented rollback evidence.",
            "requester_role": "release lead",
            "team_name": "Platform",
        },
    )
    assert response.status_code == 200
    return response.json()["workflow_id"]


def _minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 40 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode())
        output.write(body)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return output.getvalue()


def test_text_evidence_is_persisted_cited_and_audited(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    workflow_id = _create_plan(client)
    content = b"Rollback owner: Platform SRE. Verification window: 30 minutes."

    upload = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={"file": ("release-notes.txt", content, "text/plain")},
        data={"actor": "Jordan Lee"},
    )
    duplicate = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={"file": ("release-notes.txt", content, "text/plain")},
        data={"actor": "Jordan Lee"},
    )
    listed = client.get(f"/workflow/plans/{workflow_id}/evidence")
    audit = client.get(f"/workflow/plans/{workflow_id}/audit-events")

    assert upload.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["evidence_id"] == upload.json()["evidence_id"]
    assert upload.json()["citation_id"].startswith("SRC-")
    assert upload.json()["filename"] == "release-notes.txt"
    assert "Rollback owner" in upload.json()["excerpt"]
    assert len(upload.json()["source_sha256"]) == 64
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert [event["event_type"] for event in audit.json()] == [
        "plan_created",
        "evidence_attached",
    ]


def test_pdf_evidence_extracts_page_text() -> None:
    evidence = EvidenceIngestionService().extract(
        filename="release-brief.pdf",
        media_type="application/pdf",
        content=_minimal_pdf("Rollback evidence approved"),
    )

    assert evidence.media_type == "application/pdf"
    assert evidence.page_count == 1
    assert "Rollback evidence approved" in evidence.content_text


def test_unsupported_evidence_type_returns_415(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    workflow_id = _create_plan(client)

    response = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={"file": ("release.csv", b"owner,status", "text/csv")},
        data={"actor": "Jordan Lee"},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Only UTF-8 text and PDF evidence files are supported."


def test_evidence_for_unknown_plan_returns_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)

    response = client.post(
        "/workflow/plans/wf-missing/evidence",
        files={"file": ("notes.txt", b"Release notes", "text/plain")},
        data={"actor": "Jordan Lee"},
    )

    assert response.status_code == 404


def test_evidence_actor_rejects_whitespace_only_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    workflow_id = _create_plan(client)

    response = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={"file": ("notes.txt", b"Release notes", "text/plain")},
        data={"actor": "   "},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Evidence actor must contain at least two characters."


def test_evidence_upload_refreshes_and_prunes_the_runtime_hybrid_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    copilot = WorkflowCopilot(
        store=WorkflowStore(database_path=str(tmp_path / "workflow.db")),
        hybrid_index_path=tmp_path / "hybrid-index.db",
    )
    monkeypatch.setattr(routes, "copilot", copilot)
    client = TestClient(app)
    workflow_id = _create_plan(client)
    rollback_content = b"Release rollback owner is Platform SRE."

    first = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={"file": ("rollback.txt", rollback_content, "text/plain")},
        data={"actor": "Jordan Lee"},
    )
    second = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={
            "file": (
                "support.txt",
                b"Customer Support coverage is confirmed for Thursday.",
                "text/plain",
            )
        },
        data={"actor": "Jordan Lee"},
    )
    duplicate = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={"file": ("rollback.txt", rollback_content, "text/plain")},
        data={"actor": "Jordan Lee"},
    )
    search = client.post(
        f"/workflow/plans/{workflow_id}/evidence/search",
        json={
            "query": "customer release rollback readiness",
            "strategy": "hybrid",
        },
    )
    answer = client.post(
        f"/workflow/plans/{workflow_id}/evidence/answer",
        json={
            "query": "customer release rollback readiness",
            "strategy": "hybrid",
        },
    )
    status = client.get("/metrics/retrieval-index")
    audit = client.get(f"/workflow/plans/{workflow_id}/audit-events")

    assert first.status_code == 201
    assert second.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["evidence_id"] == first.json()["evidence_id"]
    assert search.status_code == 200
    assert search.json()["retriever"] == "deterministic_sqlite_persisted_hybrid_v1"
    assert search.json()["index_backend"] == "sqlite"
    assert answer.status_code == 200
    assert answer.json()["retriever"] == "deterministic_sqlite_persisted_hybrid_v1"
    assert answer.json()["index_backend"] == "sqlite"
    assert status.status_code == 200
    assert status.json() == {
        "enabled": True,
        "backend": "sqlite",
        "retriever": "deterministic_sqlite_persisted_hybrid_v1",
        "indexed_corpus_count": 1,
        "indexed_chunk_count": 2,
        "indexed_namespace_count": 1,
        "index_size_bytes": status.json()["index_size_bytes"],
        "memory_cache_hits": 5,
        "disk_cache_hits": 0,
        "cache_misses": 2,
        "compact_on_delete": False,
        "compaction_count": 0,
        "last_compaction_reclaimed_bytes": 0,
    }
    assert status.json()["index_size_bytes"] > 0
    assert [event["event_type"] for event in audit.json()] == [
        "plan_created",
        "evidence_attached",
        "evidence_index_refreshed",
        "evidence_attached",
        "evidence_index_refreshed",
    ]
    assert audit.json()[-1]["details"]["removed_corpus_count"] == "1"


def test_evidence_deletion_refreshes_clears_and_compacts_the_hybrid_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    copilot = WorkflowCopilot(
        store=WorkflowStore(database_path=str(tmp_path / "workflow.db")),
        hybrid_index_path=tmp_path / "hybrid-index.db",
        compact_hybrid_index_on_delete=True,
    )
    monkeypatch.setattr(routes, "copilot", copilot)
    client = TestClient(app)
    workflow_id = _create_plan(client)

    first = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={
            "file": (
                "rollback.txt",
                b"Release rollback owner is Platform SRE.",
                "text/plain",
            )
        },
        data={"actor": "Jordan Lee"},
    )
    second = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={
            "file": (
                "support.txt",
                b"Customer Support coverage is confirmed for Thursday.",
                "text/plain",
            )
        },
        data={"actor": "Jordan Lee"},
    )

    first_delete = client.request(
        "DELETE",
        f"/workflow/plans/{workflow_id}/evidence/{first.json()['evidence_id']}",
        json={"actor": "Jordan Lee"},
    )
    remaining = client.get(f"/workflow/plans/{workflow_id}/evidence")
    first_status = client.get("/metrics/retrieval-index")
    missing_delete = client.request(
        "DELETE",
        f"/workflow/plans/{workflow_id}/evidence/evi-missing",
        json={"actor": "Jordan Lee"},
    )
    last_delete = client.request(
        "DELETE",
        f"/workflow/plans/{workflow_id}/evidence/{second.json()['evidence_id']}",
        json={"actor": "Jordan Lee"},
    )
    final_status = client.get("/metrics/retrieval-index")
    audit = client.get(f"/workflow/plans/{workflow_id}/audit-events")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first_delete.status_code == 200
    assert first_delete.json()["filename"] == "rollback.txt"
    assert remaining.status_code == 200
    assert [item["filename"] for item in remaining.json()] == ["support.txt"]
    assert first_status.json()["indexed_corpus_count"] == 1
    assert first_status.json()["indexed_chunk_count"] == 1
    assert first_status.json()["indexed_namespace_count"] == 1
    assert first_status.json()["compact_on_delete"] is True
    assert first_status.json()["compaction_count"] == 1
    assert missing_delete.status_code == 404
    assert missing_delete.json()["detail"] == "Workflow evidence not found."
    assert last_delete.status_code == 200
    assert final_status.json()["indexed_corpus_count"] == 0
    assert final_status.json()["indexed_chunk_count"] == 0
    assert final_status.json()["indexed_namespace_count"] == 0
    assert final_status.json()["compaction_count"] == 2
    assert final_status.json()["last_compaction_reclaimed_bytes"] >= 0
    assert [event["event_type"] for event in audit.json()] == [
        "plan_created",
        "evidence_attached",
        "evidence_index_refreshed",
        "evidence_attached",
        "evidence_index_refreshed",
        "evidence_deleted",
        "evidence_index_refreshed",
        "evidence_deleted",
        "evidence_index_refreshed",
    ]
    assert audit.json()[-1]["details"]["cache_status"] == "cleared"
    assert audit.json()[-1]["details"]["compacted"] == "true"
    assert audit.json()[-1]["details"]["removed_namespace_count"] == "1"


def test_evidence_deletion_rejects_whitespace_only_actor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    workflow_id = _create_plan(client)

    response = client.request(
        "DELETE",
        f"/workflow/plans/{workflow_id}/evidence/evi-missing",
        json={"actor": "   "},
    )

    assert response.status_code == 422
