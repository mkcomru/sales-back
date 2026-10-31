from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FaqQuestion:
    question: str
    answer: str
    keywords: list[str]


@dataclass
class FaqCategory:
    category: str
    questions: list[FaqQuestion]


@dataclass
class FaqData:
    categories: list[FaqCategory]


@dataclass
class FaqMatch:
    category: str
    question: str
    answer: str
    keywords: list[str]
    score: float
