"""
services/llm_service.py
-----------------------
LLM abstraction layer for TruthGuard.

Supports multiple providers: openai, groq, ollama, mock.
The mock provider is used by default and requires no API keys.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterator, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MockLLM
# ---------------------------------------------------------------------------

_CONFLICT_KEYWORDS = {
    "supersede",
    "amend",
    "conflict",
    "contradict",
    "different",
    "vs",
    "versus",
}


class MockLLM(BaseChatModel):
    """A deterministic mock LLM for testing without API keys."""

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Join all message contents into one context string (lowercased)
        context = " ".join(
            m.content if isinstance(m.content, str) else str(m.content)
            for m in messages
        ).lower()

        # Extract numeric values from context
        numbers_found = list(set(re.findall(r"\b\d+\b", context)))

        # Detect any conflict keywords
        has_conflict_keyword = any(kw in context for kw in _CONFLICT_KEYWORDS)

        # Detect conflict: 2+ distinct numbers AND a conflict keyword
        conflict_detected = len(numbers_found) >= 2 and has_conflict_keyword

        if conflict_detected:
            # Extract doc_ids if mentioned (pattern: doc_id=<value> or doc:<value>)
            doc_ids = re.findall(r"doc(?:_id)?[=:\s]+([a-zA-Z0-9_\-]+)", context)
            doc_ref = ""
            if doc_ids:
                unique_docs = list(dict.fromkeys(doc_ids))  # preserve order, deduplicate
                doc_ref = f" (referenced source documents: {', '.join(unique_docs)})"
            response_text = (
                f"CONFLICT DETECTED: The provided documents contain conflicting numeric "
                f"values: {', '.join(numbers_found)}. These figures appear to contradict "
                f"or supersede one another{doc_ref}. Manual review or additional context "
                f"is required to resolve the discrepancy."
            )
        else:
            # Single / no conflict: form a direct answer from context
            # Find the most relevant passage (sentence containing the first number, if any)
            sentences = re.split(r"(?<=[.!?])\s+", context)
            relevant = None
            if numbers_found:
                target = numbers_found[0]
                for sentence in sentences:
                    if target in sentence:
                        relevant = sentence.strip()
                        break
            if relevant:
                response_text = (
                    f"Based on the provided context: {relevant.capitalize()}."
                )
            else:
                # No numbers — summarise first meaningful sentence
                clean_sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
                if clean_sentences:
                    response_text = (
                        f"Based on the provided context: {clean_sentences[0].capitalize()}."
                    )
                else:
                    response_text = (
                        "Based on the provided context, no specific numeric or factual "
                        "conflicts were detected."
                    )

        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    # BaseChatModel requires _stream to be defined when streaming is attempted;
    # provide a no-op pass-through that simply delegates to _generate.
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        for gen in result.generations:
            yield gen


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_llm(provider: Optional[str] = None) -> BaseChatModel:
    """Return an LLM instance for the given provider.

    Falls back to ``settings.llm_provider`` when *provider* is not specified.
    """
    resolved = (provider or settings.llm_provider or "mock").lower()

    if resolved == "openai":
        from langchain_openai import ChatOpenAI  # type: ignore

        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,  # never logged
        )

    if resolved == "groq":
        try:
            from langchain_groq import ChatGroq  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "langchain_groq is not installed. "
                "Install it with: pip install langchain-groq"
            ) from exc
        return ChatGroq(model=settings.groq_model)

    if resolved == "ollama":
        from langchain_community.chat_models import ChatOllama  # type: ignore

        return ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )

    if resolved == "mock":
        return MockLLM()

    raise ValueError(
        f"Unknown LLM provider '{resolved}'. "
        "Valid options: openai, groq, ollama, mock."
    )


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------


def call_llm(
    prompt: str,
    system_prompt: str = "",
    provider: Optional[str] = None,
) -> str:
    """Invoke an LLM with *prompt* (and optional *system_prompt*).

    Returns the content string.  On any error returns a string starting with
    ``"ERROR:"`` — API keys are NEVER logged.
    """
    try:
        llm = get_llm(provider)
        messages: List[BaseMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        result = llm.invoke(messages)

        # BaseChatModel.invoke() returns an AIMessage
        if hasattr(result, "content"):
            return result.content  # type: ignore[return-value]
        return str(result)

    except Exception as exc:  # noqa: BLE001
        # Log the exception type/message but never credentials
        logger.exception(
            "LLM call failed [provider=%s]: %s",
            provider or settings.llm_provider,
            type(exc).__name__,
        )
        return f"ERROR: LLM invocation failed — {type(exc).__name__}: {exc}"
