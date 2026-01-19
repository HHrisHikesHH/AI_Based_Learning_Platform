"""
Celery tasks for feedback app: progress tracking and personalized feedback.
"""
import asyncio

from celery import shared_task
from django.conf import settings
from django.db.models import Avg, Count, Max
from django.utils import timezone

from documents.llm_utils import GeminiRateLimiter, get_chat_llm, _safe_json_loads
from feedback.models import FeedbackReport, UserModuleProgress, UserDocumentStats
from feedback.views import get_user_weak_concepts
from quizzes.models import QuizAttempt, UserAnswer


def _gather_feedback_context(attempt_id: int):
    attempt = (
        QuizAttempt.objects.select_related("user", "quiz__module__document")
        .prefetch_related("user_answers__question")
        .get(id=attempt_id)
    )

    current_performance = {
        "score": attempt.score or 0.0,
        "answers": list(attempt.user_answers.all()),
        "time_spent": attempt.time_spent_seconds or 0,
    }

    module_history = QuizAttempt.objects.filter(
        user=attempt.user, quiz__module=attempt.quiz.module
    ).aggregate(
        avg_score=Avg("score"),
        attempt_count=Count("id"),
        best_score=Max("score"),
    )

    document_history = QuizAttempt.objects.filter(
        user=attempt.user, quiz__module__document=attempt.quiz.module.document
    ).aggregate(avg_score=Avg("score"), total_attempts=Count("id"))

    weak_concepts = get_user_weak_concepts(
        attempt.user_id, attempt.quiz.module.document_id
    )

    return {
        "attempt": attempt,
        "current": current_performance,
        "module_history": module_history,
        "document_history": document_history,
        "weak_concepts": list(weak_concepts),
    }


@shared_task
def generate_personalized_feedback(attempt_id: int):
    """
    Generate personalized feedback report for a quiz attempt.
    Can be called directly (synchronously) or via Celery (.delay()).
    """
    if FeedbackReport.objects.filter(attempt_id=attempt_id).exists():
        return

    try:
        ctx = _gather_feedback_context(attempt_id)
    except QuizAttempt.DoesNotExist:
        return

    attempt = ctx["attempt"]
    answers = ctx["current"]["answers"]
    incorrect = [a for a in answers if not a.is_correct]
    incorrect_concepts = list(
        {
            a.question.concept_covered
            for a in incorrect
            if a.question.concept_covered
        }
    )

    answer_breakdown = []
    for a in answers:
        answer_breakdown.append(
            {
                "question": a.question.question_text,
                "your_answer": a.user_answer,
                "correct_answer": a.question.correct_answer,
                "is_correct": a.is_correct,
                "concept": a.question.concept_covered,
            }
        )

    prompt = f"""
You are an empathetic tutor providing personalized feedback to a student.

CURRENT QUIZ PERFORMANCE:
- Score: {ctx['current']['score']}%
- Questions attempted: {len(answers)}
- Correct: {len(answers) - len(incorrect)}
- Time spent: {ctx['current']['time_spent']} seconds
- Mistakes on: {incorrect_concepts}

STUDENT'S LEARNING HISTORY:
- This is attempt #{attempt.attempt_number} on this module
- Previous best score on this module: {ctx['module_history'].get('best_score') or 0}%
- Average score across all modules in this course: {ctx['document_history'].get('avg_score') or 0}%
- Recurring weak areas: {ctx['weak_concepts']}

INDIVIDUAL ANSWER ANALYSIS:
{answer_breakdown}

TASK:
Generate encouraging, personalized feedback that:
1. Acknowledges their progress (compare to previous attempts)
2. Identifies patterns in mistakes
3. Provides specific recommendations
4. Maintains encouraging tone
5. Suggests next steps

Return JSON:
{{
  "overall_feedback": "Personalized message (2-3 sentences)",
  "strengths": ["Strength 1", "Strength 2"],
  "weaknesses": ["Weakness 1 with explanation", "Weakness 2"],
  "recommended_topics": ["Topic to review 1", "Topic 2"],
  "personalized_message": "Motivational closing message",
  "next_steps": ["Actionable step 1", "Step 2"]
}}
"""

    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        # Create a basic feedback report without LLM
        FeedbackReport.objects.create(
            attempt_id=attempt_id,
            overall_feedback=f"Your score was {ctx['current']['score']}%. Keep practicing!",
            strengths=["Completed the quiz", "Showed engagement"],
            weaknesses=incorrect_concepts[:3] if incorrect_concepts else ["Review the material"],
            recommended_topics=incorrect_concepts[:3] if incorrect_concepts else [],
            personalized_message="Continue learning and try again to improve your score!",
        )
        return

    try:
        llm = get_chat_llm(api_key=api_key, temperature=0.5)
        rate_limiter = GeminiRateLimiter()

        asyncio.run(rate_limiter.acquire(estimated_tokens=1500))
        response = llm.invoke(prompt)
        data = _safe_json_loads(getattr(response, "content", "") or str(response)) or {}

        # If LLM failed, create basic feedback
        if not data or not data.get("overall_feedback"):
            FeedbackReport.objects.create(
                attempt_id=attempt_id,
                overall_feedback=f"Your score was {ctx['current']['score']}%. Keep practicing!",
                strengths=["Completed the quiz", "Showed engagement"],
                weaknesses=incorrect_concepts[:3] if incorrect_concepts else ["Review the material"],
                recommended_topics=incorrect_concepts[:3] if incorrect_concepts else [],
                personalized_message="Continue learning and try again to improve your score!",
            )
            return

        FeedbackReport.objects.create(
            attempt_id=attempt_id,
            overall_feedback=data.get("overall_feedback", ""),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            recommended_topics=data.get("recommended_topics", []),
            personalized_message=data.get("personalized_message", ""),
        )
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to generate feedback with LLM: %s", exc)
        # Create basic feedback on error
        FeedbackReport.objects.create(
            attempt_id=attempt_id,
            overall_feedback=f"Your score was {ctx['current']['score']}%. Keep practicing!",
            strengths=["Completed the quiz", "Showed engagement"],
            weaknesses=incorrect_concepts[:3] if incorrect_concepts else ["Review the material"],
            recommended_topics=incorrect_concepts[:3] if incorrect_concepts else [],
            personalized_message="Continue learning and try again to improve your score!",
        )


@shared_task
def update_user_progress(user_id: int, module_id: int):
    """
    Update user progress for a module.
    Can be called directly (synchronously) or via Celery (.delay()).
    """
    """
    Update user progress for a module.
    """
    from quizzes.models import QuizAttempt
    from documents.models import Module

    module = Module.objects.get(id=module_id)
    attempts = QuizAttempt.objects.filter(user_id=user_id, quiz__module=module)
    stats = attempts.aggregate(
        best_score=Max("score"), attempts_count=Count("id"), avg_score=Avg("score")
    )

    progress, _ = UserModuleProgress.objects.get_or_create(
        user_id=user_id, module=module
    )
    best_score = stats["best_score"] or 0.0
    progress.best_score = best_score
    progress.attempts_count = stats["attempts_count"] or 0
    progress.mastery_level = (best_score / 100.0) if best_score else 0.0
    progress.last_accessed_at = timezone.now()
    progress.completion_status = (
        "COMPLETED" if best_score >= 70.0 else "IN_PROGRESS"
    )
    progress.save()


@shared_task
def update_document_stats(user_id: int, document_id: int):
    """
    Update aggregate statistics for user-document combination.
    Can be called directly (synchronously) or via Celery (.delay()).
    """
    """
    Update aggregate statistics for user-document combination.
    """
    from documents.models import Document, Module

    document = Document.objects.get(id=document_id)
    total_modules = Module.objects.filter(document=document).count()

    attempts = QuizAttempt.objects.filter(
        user_id=user_id, quiz__module__document=document
    )
    stats = attempts.aggregate(
        avg_score=Avg("score"),
        total_time=Avg("time_spent_seconds"),
    )

    all_answers = UserAnswer.objects.filter(
        attempt__user_id=user_id, attempt__quiz__module__document=document
    )

    weak_concepts = list(
        all_answers.filter(is_correct=False)
        .values("question__concept_covered")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    strong_concepts = list(
        all_answers.filter(is_correct=True)
        .values("question__concept_covered")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    stats_obj, _ = UserDocumentStats.objects.get_or_create(
        user_id=user_id, document=document
    )
    stats_obj.total_modules = total_modules
    stats_obj.completed_modules = UserModuleProgress.objects.filter(
        user_id=user_id, module__document=document, completion_status="COMPLETED"
    ).count()
    stats_obj.average_score = stats["avg_score"] or 0.0
    stats_obj.total_time_spent_seconds = int(stats_obj.total_time_spent_seconds or 0) + int(
        stats["total_time"] or 0
    )
    stats_obj.weak_concepts = weak_concepts
    stats_obj.strong_concepts = strong_concepts
    stats_obj.last_updated_at = timezone.now()
    stats_obj.save()


