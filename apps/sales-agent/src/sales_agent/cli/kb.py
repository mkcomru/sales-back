from __future__ import annotations

import asyncio
import json
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import NAMESPACE_URL, uuid5

import click
import fitz  # PyMuPDF
import httpx
from bs4 import BeautifulSoup
from docx import Document as DocxDocument

from common import SalesAgentSettings

from src.sales_agent.faq import get_faq_service
from src.sales_agent.rag.chunking import (
    RawBlock,
    fit_blocks_to_token_budget,
    html_to_blocks,
    simple_merge_chunks,
)
from src.sales_agent.rag.embeddings import EmbeddingsClient
from src.sales_agent.rag.store import QdrantStore


def _stable_uuid(seed: str) -> str:
    """Deterministic UUID for Qdrant point ids based on seed."""
    return str(uuid5(NAMESPACE_URL, seed))


def extract_text_from_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        doc = fitz.open(path)  # type: ignore[arg-type]
        parts: list[str] = []
        for page in doc:
            text = page.get_text("text")
            parts.append(str(text))
        return "\n\n".join(parts)
    if ext == ".docx":
        doc = DocxDocument(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    if ext in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")
    if ext in {".html", ".htm"}:
        html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        return soup.get_text(" ")
    raise click.ClickException(f"Unsupported file type: {ext}")


def build_blocks_from_file(path: Path) -> list[RawBlock]:
    ext = path.suffix.lower()
    if ext in {".html", ".htm"}:
        html = path.read_text(encoding="utf-8")
        blocks = html_to_blocks(html)
    else:
        text = extract_text_from_path(path)
        blocks = [RawBlock(text=text, h_path=[path.name])]

    # Ensure token budget and overlap
    settings = SalesAgentSettings()
    blocks = simple_merge_chunks(
        blocks,
        max_tokens=settings.rag.chunk_max_tokens,
        overlap_tokens=settings.rag.chunk_overlap_tokens,
    )
    blocks = fit_blocks_to_token_budget(
        blocks,
        max_tokens=settings.rag.chunk_max_tokens,
        overlap_tokens=settings.rag.chunk_overlap_tokens,
    )
    return blocks


@click.group()
def kb() -> None:  # pragma: no cover - CLI entry
    pass


@kb.command("ingest-jsonl")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--collection-name", help="Qdrant collection name (overrides default)")
def ingest_jsonl(file: Path, collection_name: str | None) -> None:
    """Ingest a .jsonl file with {title, content, url?, h_path?, keywords?}."""

    async def _run() -> None:
        settings = SalesAgentSettings()
        emb = EmbeddingsClient(settings)
        store = QdrantStore(settings)
        kb_final = collection_name or settings.rag.default_kb
        await store.ensure_collection(kb_final, vector_size=settings.rag.embedding.dimension)

        ids: list[str] = []
        texts: list[str] = []
        payloads: list[dict[str, Any]] = []

        with file.open("r", encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                content = rec.get("content") or ""
                if not content.strip():
                    continue
                rid = rec.get("id") or _stable_uuid((rec.get("url") or "") + "|" + content)
                ids.append(rid)
                texts.append(content)
                payloads.append(
                    {
                        "id": rid,
                        "kb": kb_final,
                        "doc_url": rec.get("url"),
                        "chunk_title": rec.get("title"),
                        "h_path": rec.get("h_path"),
                        "keywords": rec.get("keywords"),
                        "content": content,
                    }
                )

        vectors = await emb.aembed_documents(texts)
        await store.upsert(kb_final, ids, vectors, payloads)
        click.echo(f"ingested: {len(ids)} records into {kb_final}")

    asyncio.run(_run())


@kb.command("ingest-file")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--collection-name", help="Qdrant collection name (overrides default)")
def ingest_file(file: Path, collection_name: str | None) -> None:
    """Ingest a file: .pdf | .docx | .md | .txt | .html.

    Uses generic chunking for HTML, sentence-based split for long text.
    """

    async def _run() -> None:
        settings = SalesAgentSettings()
        emb = EmbeddingsClient(settings)
        store = QdrantStore(settings)
        kb_final = collection_name or settings.rag.default_kb
        await store.ensure_collection(kb_final, vector_size=settings.rag.embedding.dimension)

        blocks = build_blocks_from_file(file)
        ids = [_stable_uuid(f"{file}#chunk-{i}") for i in range(len(blocks))]
        texts = [b.text for b in blocks]
        vectors = await emb.aembed_documents(texts)
        payloads = []
        for i, b in enumerate(blocks):
            payloads.append(
                {
                    "id": ids[i],
                    "kb": kb_final,
                    "doc_url": str(file),
                    "chunk_title": file.name,
                    "h_path": b.h_path,
                    "keywords": None,
                    "content": b.text,
                    "chunk_idx": i,
                }
            )
        await store.upsert(kb_final, ids, vectors, payloads)
        click.echo(f"ingested: {file} -> {kb_final} ({len(ids)} chunks)")

    asyncio.run(_run())


@kb.command("ingest-dir")
@click.argument("dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--collection-name", help="Qdrant collection name (overrides default)")
@click.option(
    "--glob",
    "glob_pattern",
    default="**/*.{md,txt,html,htm,pdf,docx}",
    show_default=True,
    help="File pattern to include",
)
def ingest_dir(dir: Path, collection_name: str | None, glob_pattern: str) -> None:
    """Ingest all supported documents in a directory recursively."""

    async def _run() -> None:
        settings = SalesAgentSettings()
        emb = EmbeddingsClient(settings)
        store = QdrantStore(settings)
        kb_final = collection_name or settings.rag.default_kb
        await store.ensure_collection(kb_final, vector_size=settings.rag.embedding.dimension)

        paths: list[Path] = []
        # naive glob expansion across known extensions if shell style is unsupported
        for ext in ["md", "txt", "html", "htm", "pdf", "docx"]:
            paths.extend(dir.rglob(f"*.{ext}"))

        total_chunks = 0
        for path in sorted(paths):
            blocks = build_blocks_from_file(path)
            if not blocks:
                continue
            ids = [_stable_uuid(f"{path}#chunk-{i}") for i in range(len(blocks))]
            texts = [b.text for b in blocks]
            vectors = await emb.aembed_documents(texts)
            payloads = []
            for i, b in enumerate(blocks):
                payloads.append(
                    {
                        "id": ids[i],
                        "kb": kb_final,
                        "doc_url": str(path),
                        "chunk_title": path.name,
                        "h_path": b.h_path,
                        "keywords": None,
                        "content": b.text,
                        "chunk_idx": i,
                    }
                )
            await store.upsert(kb_final, ids, vectors, payloads)
            total_chunks += len(ids)

        click.echo(f"ingested dir: {dir} -> {kb_final} ({total_chunks} chunks)")

    asyncio.run(_run())


@kb.command("ingest-url")
@click.argument("url", type=str)
@click.option("--collection-name", help="Qdrant collection name (overrides default)")
def ingest_url(url: str, collection_name: str | None) -> None:
    """Fetch single URL, extract text, upsert as one chunk."""

    async def _run() -> None:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            blocks = html_to_blocks(r.text)
            # First coalesce small DOM blocks, then hard split long ones by sentences
            merged = simple_merge_chunks(
                blocks,
                max_tokens=SalesAgentSettings().rag.chunk_max_tokens,
                overlap_tokens=SalesAgentSettings().rag.chunk_overlap_tokens,
            )
            blocks = fit_blocks_to_token_budget(
                merged,
                max_tokens=SalesAgentSettings().rag.chunk_max_tokens,
                overlap_tokens=SalesAgentSettings().rag.chunk_overlap_tokens,
            )

        settings = SalesAgentSettings()
        emb = EmbeddingsClient(settings)
        store = QdrantStore(settings)
        kb_final = collection_name or settings.rag.default_kb
        await store.ensure_collection(kb_final, vector_size=settings.rag.embedding.dimension)

        ids = [_stable_uuid(f"{url}#chunk-{i}") for i in range(len(blocks))]
        texts = [b.text for b in blocks]
        vecs = await emb.aembed_documents(texts)
        payloads = []
        title = soup.title.string if soup.title else url
        for i, b in enumerate(blocks):
            payloads.append(
                {
                    "id": ids[i],
                    "kb": kb_final,
                    "doc_url": url,
                    "chunk_title": title,
                    "h_path": b.h_path,
                    "keywords": None,
                    "content": b.text,
                    "chunk_idx": i,
                }
            )
        await store.upsert(kb_final, ids, vecs, payloads)
        click.echo(f"ingested url: {url}")

    asyncio.run(_run())


@kb.command("crawl-site")
@click.argument("root", type=str)
@click.option("--collection-name", help="Qdrant collection name (overrides default)")
@click.option("--max-depth", default=2, show_default=True, type=int)
@click.option("--allow", multiple=True, help="Only URLs containing any of these substrings")
@click.option("--deny", multiple=True, help="Skip URLs containing any of these substrings")
def crawl_site(
    root: str,
    collection_name: str | None,
    max_depth: int,
    allow: list[str],
    deny: list[str],
) -> None:
    """Simple BFS crawler with allow/deny filters."""

    async def _run() -> None:
        parsed = urlparse(root)
        base = f"{parsed.scheme}://{parsed.netloc}"
        seen: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(root, 0)])

        settings = SalesAgentSettings()
        emb = EmbeddingsClient(settings)
        store = QdrantStore(settings)
        kb_final = collection_name or settings.rag.default_kb
        await store.ensure_collection(kb_final, vector_size=settings.rag.embedding.dimension)

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            while queue:
                url, depth = queue.popleft()
                if url in seen or depth > max_depth:
                    continue
                seen.add(url)
                if parsed.netloc != urlparse(url).netloc:
                    continue
                if allow and not any(a in url for a in allow):
                    continue
                if any(d in url for d in deny):
                    continue
                try:
                    r = await client.get(url)
                    if r.status_code >= 400:
                        continue
                    soup = BeautifulSoup(r.text, "lxml")
                    title = soup.title.string if soup.title else url
                    blocks = html_to_blocks(r.text)
                    merged = simple_merge_chunks(
                        blocks,
                        max_tokens=SalesAgentSettings().rag.chunk_max_tokens,
                        overlap_tokens=SalesAgentSettings().rag.chunk_overlap_tokens,
                    )
                    from src.sales_agent.rag.chunking import fit_blocks_to_token_budget

                    blocks = fit_blocks_to_token_budget(
                        merged,
                        max_tokens=SalesAgentSettings().rag.chunk_max_tokens,
                        overlap_tokens=SalesAgentSettings().rag.chunk_overlap_tokens,
                    )
                    ids = [_stable_uuid(f"{url}#chunk-{i}") for i in range(len(blocks))]
                    texts = [b.text for b in blocks]
                    vecs = await emb.aembed_documents(texts)
                    payloads = []
                    for i, b in enumerate(blocks):
                        payloads.append(
                            {
                                "id": ids[i],
                                "kb": kb_final,
                                "doc_url": url,
                                "chunk_title": title,
                                "h_path": b.h_path,
                                "keywords": None,
                                "content": b.text,
                                "chunk_idx": i,
                            }
                        )
                    await store.upsert(kb_final, ids, vecs, payloads)
                    # discover links
                    for a in soup.select("a[href]"):
                        href = a.get("href")
                        if not href:
                            continue
                        nxt = urljoin(url, str(href))
                        if nxt.startswith(base):
                            queue.append((nxt, depth + 1))
                    click.echo(f"ingested page: {url}")
                except Exception:
                    continue

    asyncio.run(_run())


@kb.command("faq-match")
@click.argument("question", type=str)
def faq_match(question: str) -> None:
    """Test FAQ matching for a given question."""

    async def _run() -> None:
        faq = get_faq_service()
        await faq.ensure_ready()
        match = await faq.find_best(question)
        if not match:
            click.echo(json.dumps({"match": None}, ensure_ascii=False))
            return
        click.echo(
            json.dumps(
                {
                    "category": match.category,
                    "question": match.question,
                    "score": round(match.score, 4),
                    "keywords": match.keywords,
                },
                ensure_ascii=False,
            )
        )

    asyncio.run(_run())
