"""
Celery tasks for quizzes app: quiz generation and quality validation.
"""
import asyncio
import json
import math
from typing import Any, Dict, List, Tuple

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch

from documents.llm_utils import (
    GeminiRateLimiter,
    embed_batch_with_retry,
    get_chat_llm,
    get_embedding_model,
    _safe_json_loads,
)
from documents.models import Module, ModuleChunk
from .models import Question, Quiz


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def detect_inverse_pattern(question_data: Dict[str, Any]) -> bool:
    """Detect simple 'NOT X' inversions of the correct answer."""
    options = question_data.get("options", [])
    correct = (question_data.get("correct_answer") or "").strip().lower()
    for opt in options:
        text = opt.strip().lower()
        if text.startswith("not "):
            core = text[4:].strip()
            if core == correct:
                return True
    return False


def _validate_question_quality_sync(
    question_data: Dict[str, Any],
    embeddings_model,
    rate_limiter: GeminiRateLimiter,
) -> Tuple[bool, str | None, float]:
    """
    Validate a single question's distractor quality.

    Returns (is_valid, reason, distractor_quality_score).
    """
    options: List[str] = question_data.get("options") or []
    correct_answer = (question_data.get("correct_answer") or "").strip()
    if len(options) != 4 or correct_answer not in options:
        return False, "Invalid options or correct_answer", 0.0

    async def _embed():
        return await embed_batch_with_retry(
            options,
            embeddings_model,
            rate_limiter,
            estimated_tokens=200,
        )

    option_embeddings = asyncio.run(_embed())

    correct_idx = options.index(correct_answer)
    correct_emb = option_embeddings[correct_idx]
    similarities: List[float] = []
    for i, emb in enumerate(option_embeddings):
        if i == correct_idx:
            continue
        sim = _cosine_similarity(emb, correct_emb)
        similarities.append(sim)
        if sim > 0.9:
            return False, "Distractor too similar to correct answer", 0.0

    if detect_inverse_pattern(question_data):
        return False, "Contains inverse option", 0.0

    max_sim = max(similarities) if similarities else 0.0
    quality_score = 1.0 - max_sim
    return True, None, quality_score


def _build_quiz_prompt(module: Module, chunks_text: str) -> str:
    return f"""
You are an expert educator creating assessment questions.

Context: {module.summary or module.title}
Full content: {chunks_text}

Generate 5 multiple-choice questions that:
1. Test deep understanding (not memorization)
2. Cover key concepts from this module
3. Have 4 options each
4. Distractors (wrong answers) should be:
   - Plausible (students might reasonably choose them)
   - Based on common misconceptions
   - NOT just inversions of the correct answer
   - NOT obviously wrong

For each question, also identify:
- concept_covered: specific topic being tested
- difficulty_score: 0.0 (easy) to 1.0 (hard)
- explanation: why the correct answer is right

Return JSON:
[
  {{
    "question_text": "...",
    "options": ["A", "B", "C", "D"],
    "correct_answer": "B",
    "explanation": "...",
    "concept_covered": "...",
    "difficulty_score": 0.6
  }},
  ...
]
"""


def _validate_question_set(
    questions: List[Dict[str, Any]],
    embeddings_model,
    rate_limiter: GeminiRateLimiter,
) -> Tuple[bool, str | None, List[Dict[str, Any]]]:
    """Validate entire question set: quality and concept coverage."""
    if len(questions) != 5:
        return False, "Expected 5 questions", questions

    concepts = [q.get("concept_covered") for q in questions]
    if len(set(concepts)) != len(concepts):
        return False, "Duplicate concepts detected", questions

    validated: List[Dict[str, Any]] = []
    for q in questions:
        ok, reason, dq_score = _validate_question_quality_sync(q, embeddings_model, rate_limiter)
        if not ok:
            return False, reason, questions
        q["distractor_quality_score"] = dq_score
        validated.append(q)
    return True, None, validated


def generate_quiz_for_module(module_id: int, difficulty: str = "MEDIUM") -> int | None:
    """
    Generate quiz questions for a module (cached: only once).
    """
    try:
        module = Module.objects.prefetch_related(
            Prefetch("chunks", queryset=ModuleChunk.objects.order_by("chunk_order"))
        ).get(id=module_id)
    except Module.DoesNotExist:
        return None

    existing = module.quizzes.first()
    if existing:
        return existing.id

    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        return None

    # Use dummy embeddings (no real API call)
    embeddings_model = get_embedding_model(api_key=api_key)
    rate_limiter = GeminiRateLimiter()

    chunks_text = " ".join(module.chunks.values_list("content", flat=True))[:8000]
    if not chunks_text and module.summary:
        chunks_text = module.summary
    best_questions: List[Dict[str, Any]] | None = None

    try:
        llm_temps = [0.7, 0.8, 0.9]
        for temp in llm_temps:
            llm = get_chat_llm(api_key=api_key, temperature=temp, max_tokens=4096)
            prompt = _build_quiz_prompt(module, chunks_text)
            response = llm.invoke(prompt)
            raw = getattr(response, "content", "") or str(response)
            data = _safe_json_loads(raw)
            if not isinstance(data, list):
                continue

            ok, reason, validated = _validate_question_set(data, embeddings_model, rate_limiter)
            if ok:
                best_questions = validated
                break
            if best_questions is None:
                best_questions = validated
    except Exception as exc:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error("LLM quiz generation failed: %s", exc, exc_info=True)
        # Fallback: extract meaningful concepts from content and create basic questions
        import re
        title = module.title or "this module"
        content = chunks_text[:4000] if chunks_text else (module.summary or "")
        
        # Extract meaningful concepts:
        # 1. Headings (lines starting with # or all caps short lines)
        headings = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
        # 2. Important capitalized phrases (2-4 words, proper nouns)
        important_phrases = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', content)
        # 3. Quoted terms
        quoted = re.findall(r'"([^"]{5,50})"', content)
        # 4. Terms after colons (definitions)
        after_colons = re.findall(r':\s*([A-Z][a-z]+(?:\s+[a-z]+)*)', content)
        
        # Combine and filter meaningful terms (length 3-50 chars, not too common)
        all_terms = headings + important_phrases + quoted + after_colons
        common_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'}
        key_terms = []
        seen = set()
        for term in all_terms:
            term_clean = term.strip()
            if 5 <= len(term_clean) <= 50 and term_clean.lower() not in common_words and term_clean not in seen:
                key_terms.append(term_clean)
                seen.add(term_clean)
                if len(key_terms) >= 10:
                    break
        
        # If we still don't have good terms, extract sentences and use first noun phrases
        if len(key_terms) < 5:
            sentences = re.split(r'[.!?]\s+', content[:2000])
            for sent in sentences[:10]:
                # Find noun phrases (simplified: capitalized words followed by lowercase)
                np = re.findall(r'\b([A-Z][a-z]+(?:\s+[a-z]+){0,2})\b', sent)
                for phrase in np[:2]:
                    if 5 <= len(phrase) <= 40 and phrase not in seen and phrase.lower() not in common_words:
                        key_terms.append(phrase)
                        seen.add(phrase)
                        if len(key_terms) >= 10:
                            break
        
        best_questions = []
        concepts_used = set()
        
        # Create questions based on actual content
        for i in range(5):
            if not key_terms:
                # Last resort: use module title
                concept = title
                q_text = f"What is a key concept covered in {title}?"
                options = [
                    f"An important topic in {title}",
                    "An unrelated concept",
                    "A random fact",
                    "Not applicable"
                ]
            else:
                # Use actual key terms from content
                term_idx = i % len(key_terms)
                concept_term = key_terms[term_idx]
                if concept_term in concepts_used:
                    # Try next term
                    for j in range(len(key_terms)):
                        candidate = key_terms[(term_idx + j) % len(key_terms)]
                        if candidate not in concepts_used:
                            concept_term = candidate
                            break
                concepts_used.add(concept_term)
                concept = concept_term
                # Create question about this term
                q_text = f"What is {concept_term}?"
                
                # Create plausible distractors from other terms
                distractors = []
                for other_term in key_terms:
                    if other_term != concept_term and len(distractors) < 3:
                        distractors.append(other_term)
                while len(distractors) < 3:
                    distractors.append(f"Unrelated concept {len(distractors) + 1}")
                
                options = [f"The correct definition of {concept_term}"] + distractors[:3]
            
            best_questions.append(
                {
                    "question_text": q_text,
                    "options": options,
                    "correct_answer": options[0],
                    "explanation": f"This concept is discussed in {title}.",
                    "concept_covered": concept,
                    "difficulty_score": 0.5,
                    "distractor_quality_score": 0.5
                }
            )

    if not best_questions:
        return None

    with transaction.atomic():
        quiz = Quiz.objects.create(
            module=module,
            difficulty=difficulty,
            total_questions=len(best_questions),
            estimated_duration_minutes=10,
        )

        questions_to_create: List[Question] = []
        for idx, q in enumerate(best_questions, start=1):
            questions_to_create.append(
                Question(
                    quiz=quiz,
                    question_text=q["question_text"],
                    question_type="MCQ",
                    options=q["options"],
                    correct_answer=q["correct_answer"],
                    explanation=q.get("explanation") or "",
                    concept_covered=q.get("concept_covered") or "",
                    difficulty_score=float(q.get("difficulty_score") or 0.5),
                    distractor_quality_score=float(q.get("distractor_quality_score") or 0.5),
                    question_order=idx,
                )
            )
        Question.objects.bulk_create(questions_to_create)

        module.is_quiz_ready = True
        module.save(update_fields=["is_quiz_ready"])

    return quiz.id


