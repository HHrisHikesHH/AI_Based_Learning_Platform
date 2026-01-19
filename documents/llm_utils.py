"""
LangChain + Gemini helpers for semantic chunking and embeddings.

Note: We avoid LangChain prompt utilities to keep compatibility with newer versions.
"""
import asyncio
import json
import os
import time
from collections import deque
from typing import Any, Dict, List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# Use gemini-2.5-flash (latest fast model)
LLM_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL = "models/embedding-001"


class GeminiRateLimiter:
    """Async rate limiter for RPM/TPM control."""

    def __init__(self, rpm: int = 15, tpm: int = 1_000_000):
        self.rpm_limit = rpm
        self.tpm_limit = tpm
        self.call_timestamps = deque()
        self.tokens_used = deque()
        self.lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int = 1000):
        async with self.lock:
            now = time.monotonic()
            window = 60.0
            # Drop stale entries
            while self.call_timestamps and now - self.call_timestamps[0] > window:
                self.call_timestamps.popleft()
            while self.tokens_used and now - self.tokens_used[0][0] > window:
                self.tokens_used.popleft()

            calls_last_minute = len(self.call_timestamps)
            tokens_last_minute = sum(t for _, t in self.tokens_used)

            # Wait for RPM
            if calls_last_minute >= self.rpm_limit:
                sleep_time = window - (now - self.call_timestamps[0])
                await asyncio.sleep(max(sleep_time, 0))
                return await self.acquire(estimated_tokens)

            # Wait for TPM
            if tokens_last_minute + estimated_tokens > self.tpm_limit:
                sleep_time = window - (now - self.tokens_used[0][0])
                await asyncio.sleep(max(sleep_time, 0))
                return await self.acquire(estimated_tokens)

            # Record usage
            self.call_timestamps.append(now)
            self.tokens_used.append((now, estimated_tokens))


def get_chat_llm(api_key: Optional[str] = None, temperature: float = 0.3, max_tokens: int = 4096) -> ChatGoogleGenerativeAI:
    """Instantiate Gemini chat model."""
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        temperature=temperature,
        max_output_tokens=max_tokens,
        api_key=api_key,
    )


def get_embedding_model(api_key: Optional[str] = None) -> GoogleGenerativeAIEmbeddings:
    """Instantiate Gemini embedding model."""
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, api_key=api_key)


SEMANTIC_PROMPT = """
You are analyzing educational content. Divide this text into logical learning modules.

Rules:
- Each module = one complete concept/topic
- Modules should be 500-3000 words
- Provide clear module titles
- Maintain natural topic flow

Text:
{document_text}

Return JSON:
[
  {{
    "title": "Module title",
    "start_index": 0,
    "end_index": 1500,
    "summary": "Brief summary"
  }},
  ...
]
"""


def _word_count(text: str) -> int:
    return len(text.split())


def _safe_json_loads(data: str) -> Any:
    """Parse JSON, handling markdown code blocks."""
    if not data:
        return None
    # Strip markdown code blocks if present
    data = data.strip()
    if data.startswith("```"):
        # Remove opening ```json or ```
        lines = data.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove closing ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        data = "\n".join(lines)
    try:
        return json.loads(data)
    except Exception:
        return None


def _fallback_split(text: str, min_words: int = 500, max_words: int = 3000) -> List[Dict[str, Any]]:
    """Simple fallback splitting by word count."""
    words = text.split()
    modules = []
    start = 0
    idx = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk_words = words[start:end]
        if len(chunk_words) < min_words and modules:
            # Merge remainder into last module
            modules[-1]["end_index"] = len(" ".join(words[:end]))
            modules[-1]["summary"] = ""
            break
        chunk_text = " ".join(chunk_words)
        modules.append(
            {
                "title": f"Module {idx + 1}",
                "start_index": len(" ".join(words[:start])),
                "end_index": len(" ".join(words[:end])),
                "summary": "",
            }
        )
        start = end
        idx += 1
    return modules


async def semantic_module_boundaries(
    llm: ChatGoogleGenerativeAI, text: str, rate_limiter: GeminiRateLimiter
) -> List[Dict[str, Any]]:
    """Use LLM to find module boundaries with fallback."""
    # To control prompt size, cap text length
    max_chars = 15000
    truncated_text = text[:max_chars]
    await rate_limiter.acquire(estimated_tokens=min(len(truncated_text) // 4, 8000))
    prompt = SEMANTIC_PROMPT.format(document_text=truncated_text)
    response = await llm.ainvoke(prompt)
    data = _safe_json_loads(response.content) if hasattr(response, "content") else _safe_json_loads(str(response))
    if not isinstance(data, list) or not data:
        return _fallback_split(text)
    # Validate boundaries and sizes
    clean_modules = []
    for idx, item in enumerate(data):
        try:
            start_idx = int(item.get("start_index", 0))
            end_idx = int(item.get("end_index", 0))
            title = item.get("title") or f"Module {idx + 1}"
            summary = item.get("summary") or ""
            start_idx = max(start_idx, 0)
            end_idx = max(end_idx, start_idx + 1)
            segment = text[start_idx:end_idx]
            words = _word_count(segment)
            if words < 500 or words > 3000:
                continue
            clean_modules.append(
                {
                    "title": title.strip(),
                    "start_index": start_idx,
                    "end_index": end_idx,
                    "summary": summary.strip(),
                }
            )
        except Exception:
            continue
    if not clean_modules:
        return _fallback_split(text)
    return clean_modules


async def embed_batch_with_retry(
    texts: List[str],
    embeddings: GoogleGenerativeAIEmbeddings,
    rate_limiter: GeminiRateLimiter,
    max_retries: int = 3,
    estimated_tokens: int = 800,
) -> List[List[float]]:
    """
    Batch embed documents.

    NOTE: To keep the application working even when Gemini embedding quotas are
    exhausted, this implementation currently returns deterministic dummy vectors
    instead of calling the remote API. This still allows pgvector indexes and
    similarity queries to function syntactically, but without real semantic
    meaning. The dimension is fixed to 768 to match the pgvector field.
    """
    dim = 768
    results: List[List[float]] = []
    for i, _ in enumerate(texts):
        # Simple deterministic pattern based on index; enough for shape correctness.
        vec = [0.0] * dim
        if dim > 0:
            vec[i % dim] = 1.0
        results.append(vec)
    return results


