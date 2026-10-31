from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import structlog
from pydantic import BaseModel

from .models import FaqCategory, FaqData, FaqQuestion


class RawFaqData(BaseModel):
    model_config = {"extra": "allow"}


@dataclass
class _Cache:
    mtime_ns: int
    data: FaqData


class FaqLoader:
    def __init__(self, faq_path: Path) -> None:
        self.log = structlog.get_logger()
        self._path = faq_path
        self._cache: _Cache | None = None

    def _load_raw(self) -> RawFaqData:
        text = self._path.read_text(encoding="utf-8")
        data = json.loads(text)
        return RawFaqData(**data)

    def _parse(self, raw: RawFaqData) -> FaqData:
        items: list[FaqCategory] = []
        payload = raw.model_dump()
        for cat in payload.get("faq", []):
            if not isinstance(cat, dict):
                continue
            questions: list[FaqQuestion] = []
            for q in cat.get("questions", []):
                if not isinstance(q, dict):
                    continue
                questions.append(
                    FaqQuestion(
                        question=str(q.get("question", "")).strip(),
                        answer=str(q.get("answer", "")).strip(),
                        keywords=[str(k).strip() for k in (q.get("keywords") or [])],
                    )
                )
            items.append(FaqCategory(category=str(cat.get("category", "")).strip(), questions=questions))
        return FaqData(categories=items)

    def load(self) -> FaqData:
        if not self._path.exists():
            self.log.warning("faq.file_missing", path=str(self._path))
            return FaqData(categories=[])

        stat = self._path.stat()
        if self._cache and self._cache.mtime_ns == stat.st_mtime_ns:
            return self._cache.data

        try:
            raw = self._load_raw()
            data = self._parse(raw)
            self._cache = _Cache(mtime_ns=stat.st_mtime_ns, data=data)
            self.log.debug("faq.file_loaded", path=str(self._path), categories=len(data.categories))
            return data
        except Exception as e:
            self.log.error("faq.file_load_error", path=str(self._path), err=str(e))
            return FaqData(categories=[])
