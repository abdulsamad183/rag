"""Developer CLI.

    uv run rag health
    uv run rag ingest ./data/demo --collection "Aurora Demo"
    uv run rag reindex --collection "Aurora Demo"
    uv run rag evaluate ./evaluation/aurora-golden.jsonl --collection "Aurora Demo"
    uv run rag benchmark --collection "Aurora Demo" --dataset "Aurora Golden v1"
    uv run rag inspect-trace <trace-id>
    uv run rag seed
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from app.config import get_settings

cli = typer.Typer(name="rag", help="Adaptive Evidence-Driven RAG Engine CLI", no_args_is_help=True)
console = Console()


def _run(coro):
    return asyncio.run(coro)


@cli.command()
def health() -> None:
    """Check database, Redis, and provider configuration."""

    async def _health():
        from app.core.db import session_scope
        from app.services.health import readiness

        async with session_scope() as session:
            return await readiness(session)

    try:
        report = _run(_health())
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Database unreachable:[/red] {exc}")
        raise typer.Exit(1) from exc

    table = Table(title="Health")
    table.add_column("Check")
    table.add_column("Status")
    checks = report["checks"]
    table.add_row("database", "[green]ok[/green]" if checks["database"]["ok"] else "[red]down[/red]")
    redis_ok = checks["redis"]["ok"]
    table.add_row("redis", "[green]ok[/green]" if redis_ok else "[yellow]in-memory fallback[/yellow]")
    for provider, info in checks["providers"].items():
        state = "[green]configured[/green]" if info["configured"] else "[dim]not configured[/dim]"
        table.add_row(f"provider:{provider}", state)
    console.print(table)


@cli.command()
def seed() -> None:
    """Create the demo collection, documents, and golden dataset."""
    from app.seed import seed as run_seed

    _run(run_seed())
    console.print("[green]Seed complete.[/green]")


@cli.command()
def ingest(
    path: Path = typer.Argument(..., help="File or directory to ingest"),
    collection: str = typer.Option(..., "--collection", "-c", help="Target collection name"),
) -> None:
    """Ingest local files into a collection (creates it if missing)."""

    async def _ingest():
        from app.core.db import session_scope
        from app.embeddings.registry import default_embedding_model
        from app.models import Collection
        from app.repositories.users import get_or_create_default_user
        from app.services.documents import upload_document
        from app.services.ingestion import ingest_document

        settings = get_settings()
        files = sorted(p for p in ([path] if path.is_file() else path.rglob("*")) if p.is_file())
        if not files:
            console.print("[yellow]No files found.[/yellow]")
            return

        async with session_scope() as session:
            user = await get_or_create_default_user(session)
            existing = await session.execute(
                select(Collection).where(Collection.user_id == user.id, Collection.name == collection)
            )
            target = existing.scalars().first()
            if target is None:
                provider = settings.default_embedding_provider
                target = Collection(
                    user_id=user.id,
                    name=collection,
                    embedding_provider=provider,
                    embedding_model=default_embedding_model(provider),
                    chunking_config={"strategy": settings.chunking_strategy,
                                     "chunk_size": settings.chunk_size,
                                     "chunk_overlap": settings.chunk_overlap},
                )
                session.add(target)
                await session.commit()
                console.print(f"Created collection [bold]{collection}[/bold]")

            for file in files:
                try:
                    document, is_new = await upload_document(
                        session, target, file.name, file.read_bytes()
                    )
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]skip[/red] {file.name}: {exc}")
                    continue
                if not is_new:
                    console.print(f"[dim]unchanged[/dim] {file.name}")
                    continue
                console.print(f"[cyan]ingesting[/cyan] {file.name} …")
                await ingest_document(session, document.id)
                console.print(f"[green]done[/green] {file.name}")

    _run(_ingest())


@cli.command()
def reindex(
    collection: str = typer.Option(..., "--collection", "-c"),
) -> None:
    """Re-run ingestion for every document in a collection."""

    async def _reindex():
        from app.core.db import session_scope
        from app.models import Collection, Document
        from app.services.ingestion import ingest_document

        async with session_scope() as session:
            target = (
                await session.execute(select(Collection).where(Collection.name == collection))
            ).scalars().first()
            if target is None:
                console.print(f"[red]Collection '{collection}' not found[/red]")
                raise typer.Exit(1)
            documents = (
                (await session.execute(select(Document).where(Document.collection_id == target.id)))
                .scalars().all()
            )
            for document in documents:
                console.print(f"[cyan]reindexing[/cyan] {document.filename} …")
                await ingest_document(session, document.id)
            console.print(f"[green]Reindexed {len(documents)} documents.[/green]")

    _run(_reindex())


@cli.command()
def evaluate(
    dataset_file: Path = typer.Argument(..., help="JSONL dataset"),
    collection: str = typer.Option(..., "--collection", "-c"),
    mode: str = typer.Option("balanced", "--mode"),
    name: str = typer.Option("", "--name"),
) -> None:
    """Import a dataset (if new) and run an evaluation synchronously."""

    async def _evaluate():
        from app.core.db import session_scope
        from app.models import Collection, EvaluationDataset, EvaluationRun
        from app.services.evaluation import import_dataset_jsonl, run_evaluation

        async with session_scope() as session:
            target = (
                await session.execute(select(Collection).where(Collection.name == collection))
            ).scalars().first()
            if target is None:
                console.print(f"[red]Collection '{collection}' not found[/red]")
                raise typer.Exit(1)

            ds_name = name or dataset_file.stem
            dataset = (
                await session.execute(
                    select(EvaluationDataset).where(EvaluationDataset.name == ds_name)
                )
            ).scalars().first()
            if dataset is None:
                dataset = await import_dataset_jsonl(session, ds_name, "", dataset_file.read_text())
                console.print(f"Imported dataset [bold]{ds_name}[/bold]")

            run = EvaluationRun(
                dataset_id=dataset.id,
                name=f"{ds_name} · {mode} (CLI)",
                config={"collection_ids": [str(target.id)], "mode": mode, "k": 5},
            )
            session.add(run)
            await session.commit()
            console.print("Running evaluation…")
            await run_evaluation(session, run.id)
            await session.refresh(run)
            console.print_json(json.dumps(run.metrics, default=str))

    _run(_evaluate())


@cli.command()
def benchmark(
    collection: str = typer.Option(..., "--collection", "-c"),
    dataset: str = typer.Option("Aurora Golden v1", "--dataset", "-d"),
) -> None:
    """Run the baseline comparison matrix (vector / hybrid / hybrid+rerank /
    adaptive) against one dataset and print a comparison table."""

    async def _benchmark():
        from app.core.db import session_scope
        from app.models import Collection, EvaluationDataset, EvaluationRun
        from app.services.evaluation import run_evaluation

        configs = [
            ("Baseline: Vector RAG", {"mode": "fast", "strategy": "vector", "reranker": "none"}),
            ("Baseline: Hybrid RAG", {"mode": "fast", "strategy": "hybrid", "reranker": "none"}),
            ("Baseline: Hybrid + Rerank", {"mode": "balanced", "strategy": "hybrid"}),
            ("System: Adaptive Evidence-Driven", {"mode": "adaptive"}),
        ]

        async with session_scope() as session:
            target = (
                await session.execute(select(Collection).where(Collection.name == collection))
            ).scalars().first()
            ds = (
                await session.execute(
                    select(EvaluationDataset).where(EvaluationDataset.name == dataset)
                )
            ).scalars().first()
            if target is None or ds is None:
                console.print("[red]Collection or dataset not found (run `rag seed` first)[/red]")
                raise typer.Exit(1)

            rows = []
            for label, config in configs:
                run = EvaluationRun(
                    dataset_id=ds.id, name=label,
                    config={"collection_ids": [str(target.id)], "k": 5, **config},
                )
                session.add(run)
                await session.commit()
                console.print(f"[cyan]running[/cyan] {label} …")
                try:
                    await run_evaluation(session, run.id)
                    await session.refresh(run)
                    rows.append((label, run.metrics))
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]failed[/red] {label}: {exc}")

            table = Table(title=f"Benchmark — {dataset}")
            table.add_column("Configuration")
            for metric in ("recall@5", "mrr", "answer_f1", "citation_precision"):
                table.add_column(metric)
            table.add_column("abstention")
            table.add_column("cost $")
            for label, metrics in rows:
                ground = metrics.get("ground_truth", {})
                abstention = metrics.get("abstention_accuracy")
                table.add_row(
                    label,
                    *(f"{ground.get(m, 0):.3f}" for m in
                      ("recall@5", "mrr", "answer_f1", "citation_precision")),
                    "—" if abstention is None else f"{abstention:.2f}",
                    f"{metrics.get('estimated_cost_usd', 0):.4f}",
                )
            console.print(table)

    _run(_benchmark())


@cli.command(name="inspect-trace")
def inspect_trace(trace_id: str = typer.Argument(...)) -> None:
    """Print the full structured trace of one RAG execution."""

    async def _inspect():
        from app.core.db import session_scope
        from app.repositories.traces import get_trace

        async with session_scope() as session:
            trace = await get_trace(session, uuid.UUID(trace_id))
            console.print(f"[bold]{trace.query}[/bold]")
            console.print(
                f"mode={trace.mode} strategy={trace.strategy} provider={trace.provider} "
                f"model={trace.model} latency={trace.latency_ms}ms abstained={trace.abstained}"
            )
            for step in trace.steps:
                status = step.get("status", "ok")
                color = {"ok": "green", "error": "red"}.get(status, "yellow")
                console.print(
                    f"  [{color}]{status:7}[/{color}] {step['name']:24} "
                    f"{step.get('latency_ms', 0):>6}ms  "
                    f"{json.dumps(step.get('payload', {}), default=str)[:140]}"
                )
            console.print_json(json.dumps({"confidence": trace.confidence, "usage": trace.usage},
                                          default=str))

    _run(_inspect())


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
