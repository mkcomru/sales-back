from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from bs4 import BeautifulSoup
from readability import Document as ReadabilityDocument


@dataclass
class RawBlock:
    text: str
    h_path: list[str]
    lang: str | None = None


def simple_merge_chunks(blocks: Sequence[RawBlock], *, max_tokens: int, overlap_tokens: int) -> list[RawBlock]:
    """Very basic token-budgeted merger using whitespace token approximation.

    Placeholder for initial version; can be replaced by smarter
    semantic strategy.
    """

    def ntoks(s: str) -> int:
        return max(1, len(s.split()))

    merged: list[RawBlock] = []
    buf: list[str] = []
    buf_h: list[str] = []
    cur = 0
    for b in blocks:
        t = ntoks(b.text)
        if cur + t > max_tokens and buf:
            merged.append(
                RawBlock(
                    text="\n\n".join(buf),
                    h_path=buf_h or b.h_path,
                    lang=b.lang,
                )
            )
            # create overlap by taking tail from buffer
            if overlap_tokens > 0:
                tail = []
                cnt = 0
                for segment in reversed(buf):
                    cnt += ntoks(segment)
                    tail.append(segment)
                    if cnt >= overlap_tokens:
                        break
                buf = list(reversed(tail))
                cur = ntoks(" ".join(buf))
            else:
                buf = []
                cur = 0
            buf_h = b.h_path

        buf.append(b.text)
        cur += t
        if not buf_h:
            buf_h = b.h_path

    if buf:
        merged.append(
            RawBlock(
                text="\n\n".join(buf),
                h_path=buf_h,
                lang=blocks[-1].lang if blocks else None,
            )
        )

    return merged


def _visible_text(node) -> str:
    # Skip very short fragments
    txt = node.get_text(" ", strip=True)
    return txt


def html_to_blocks(html: str) -> list[RawBlock]:
    """Extract structured blocks from HTML using headings hierarchy.

    We evaluate two candidates: readability-article and full DOM; return the
    one that yields more blocks/tokens. This helps на лендингах с мало заголовков.
    """

    def prepare_soup(raw_html: str) -> BeautifulSoup:
        s = BeautifulSoup(raw_html, "lxml")
        for tag in s(
            [
                "script",
                "style",
                "noscript",
                "iframe",
                "svg",
                "nav",
                "header",
                "footer",
                "aside",
            ]
        ):
            tag.decompose()
        return s

    def segment(soup: BeautifulSoup) -> list[RawBlock]:
        blocks_local: list[RawBlock] = []
        path: list[tuple[int, str]] = []
        buffer: list[str] = []

        def flush_local() -> None:
            if not buffer:
                return
            text = "\n\n".join(buffer).strip()
            if text:
                blocks_local.append(RawBlock(text=text, h_path=[t for _, t in path] or [""]))
            buffer.clear()

        for el in soup.find_all(True):
            name = el.name.lower()
            if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                flush_local()
                level = int(name[1])
                title = el.get_text(" ", strip=True)
                while path and path[-1][0] >= level:
                    path.pop()
                path.append((level, title))
                continue
            if name in {"p", "li", "blockquote", "pre", "code", "td"}:
                txt = _visible_text(el)
                if txt:
                    buffer.append(txt)
            elif name == "div":
                txt = _visible_text(el)
                if _ntoks(txt) >= 20:
                    buffer.append(txt)

        flush_local()
        return blocks_local

    # Build candidates
    cands: list[list[RawBlock]] = []
    try:
        article_html = ReadabilityDocument(html).summary(html_partial=True)
        cands.append(segment(prepare_soup(article_html)))
    except Exception:
        pass
    cands.append(segment(prepare_soup(html)))

    def score(blks: list[RawBlock]) -> tuple[int, int]:
        return (len(blks), sum(_ntoks(b.text) for b in blks))

    best = max(cands, key=score) if cands else []
    if not best:
        s = prepare_soup(html)
        text = s.get_text(" ", strip=True)
        if text:
            title = s.title.string if s.title else None
            h_path: list[str] = [title] if title else []
            return [RawBlock(text=text, h_path=h_path)]
        return []

    return best


def _ntoks(s: str) -> int:
    return max(1, len(s.split()))


def _split_text_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def fit_blocks_to_token_budget(blocks: Sequence[RawBlock], *, max_tokens: int, overlap_tokens: int) -> list[RawBlock]:
    """Ensure each block fits token budget; split long ones on sentence boundaries.

    - If block <= max: keep as is
    - If > max: split by sentences into windows with overlap
    """
    result: list[RawBlock] = []
    for b in blocks:
        if _ntoks(b.text) <= max_tokens:
            result.append(b)
            continue

        sentences = _split_text_sentences(b.text)
        window: list[str] = []
        cur = 0
        for sent in sentences:
            t = _ntoks(sent)
            if cur + t > max_tokens and window:
                result.append(RawBlock(text=" ".join(window), h_path=b.h_path, lang=b.lang))
                # overlap from tail
                if overlap_tokens > 0:
                    tail: list[str] = []
                    cnt = 0
                    for seg in reversed(window):
                        cnt += _ntoks(seg)
                        tail.append(seg)
                        if cnt >= overlap_tokens:
                            break
                    window = list(reversed(tail))
                    cur = _ntoks(" ".join(window))
                else:
                    window = []
                    cur = 0
            window.append(sent)
            cur += t

        if window:
            result.append(RawBlock(text=" ".join(window), h_path=b.h_path, lang=b.lang))

    return result
