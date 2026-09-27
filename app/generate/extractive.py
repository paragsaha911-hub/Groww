from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.generate.prompts import (
    MAX_SENTENCES,
    NOT_FOUND,
    ParsedPrompt,
    is_not_found,
    parse_user_prompt,
    split_sentences,
    tokenise,
)


@runtime_checkable
class Answerer(Protocol):
    name: str

    def generate(self, system: str, user: str) -> str: ...


def _sentence_score(sentence: str, query_tokens: set[str]) -> float:
    tokens = tokenise(sentence)
    if not tokens:
        return 0.0
    if not query_tokens:
        return 0.0
    hits = len(tokens & query_tokens)
    return hits / (len(tokens) ** 0.5)


def select_sentences(
    text: str, query: str, max_sentences: int = MAX_SENTENCES
) -> list[str]:
    sentences = split_sentences(text)
    if len(sentences) <= max_sentences:
        return sentences
    query_tokens = tokenise(query)
    scored = [
        (_sentence_score(sentence, query_tokens), -position, position, sentence)
        for position, sentence in enumerate(sentences)
    ]
    ranked = sorted(scored, key=lambda item: (-item[0], -item[1]))
    chosen = sorted(ranked[:max_sentences], key=lambda item: item[2])
    return [item[3] for item in chosen]


class ExtractiveAnswerer:
    name = "extractive"

    def __init__(self, max_sentences: int = MAX_SENTENCES) -> None:
        self.max_sentences = max_sentences

    def generate(self, system: str, user: str) -> str:
        parsed: ParsedPrompt = parse_user_prompt(user)
        if not parsed.blocks:
            return NOT_FOUND
        best_text = parsed.blocks[0]["text"]
        chosen = select_sentences(best_text, parsed.query, self.max_sentences)
        if not chosen:
            return NOT_FOUND
        source_id = parsed.blocks[0].get("source_id", "")
        body = " ".join(chosen)
        if is_not_found(body):
            return NOT_FOUND
        return f"{body}\nSOURCE_ID: {source_id}" if source_id else body

    def answer_from(self, text: str, query: str, source_id: str = "") -> str:
        chosen = select_sentences(text, query, self.max_sentences)
        if not chosen:
            return NOT_FOUND
        body = " ".join(chosen)
        return f"{body}\nSOURCE_ID: {source_id}" if source_id else body


def build_offline_answerer(blocks: Sequence[dict[str, str]]) -> ExtractiveAnswerer:
    return ExtractiveAnswerer()
