from django.db.models import Avg, Count, Max, Q, FloatField
from django.db.models.functions import Cast

from documents.models import Module
from quizzes.models import UserAnswer, QuizAttempt
from feedback.models import UserModuleProgress, UserDocumentStats


def get_user_weak_concepts(user_id: int, document_id: int):
    """
    Analyze which concepts user struggles with.
    """
    return (
        UserAnswer.objects.filter(
            attempt__user_id=user_id,
            attempt__quiz__module__document_id=document_id,
            is_correct=False,
        )
        .values("question__concept_covered")
        .annotate(
            error_count=Count("id"),
            avg_time_spent=Avg("time_spent_seconds"),
        )
        .filter(error_count__gte=2)
        .order_by("-error_count")
    )


def get_document_analytics(user_id: int, document_id: int):
    """
    Aggregate analytics for a document for a given user.
    """
    total_modules = Module.objects.filter(document_id=document_id).count()
    completed_modules = UserModuleProgress.objects.filter(
        user_id=user_id,
        module__document_id=document_id,
        completion_status="COMPLETED",
    ).count()

    avg_score = (
        QuizAttempt.objects.filter(
            user_id=user_id, quiz__module__document_id=document_id
        ).aggregate(avg=Avg("score"))["avg"]
        or 0.0
    )

    all_answers = UserAnswer.objects.filter(
        attempt__user_id=user_id,
        attempt__quiz__module__document_id=document_id,
    )

    concept_perf = (
        all_answers.values("question__concept_covered")
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
            accuracy=Cast(
                Count("id", filter=Q(is_correct=True)), FloatField()
            )
            / Cast(Count("id"), FloatField())
            * 100.0,
        )
        .order_by("-accuracy")
    )

    strong_concepts = list(concept_perf.filter(accuracy__gte=80)[:5])
    weak_concepts = list(concept_perf.filter(accuracy__lt=70)[:5])

    progress_percentage = (completed_modules / total_modules * 100.0) if total_modules else 0.0

    # Adaptive recommendation
    if avg_score < 60:
        recommendation = "Review fundamentals and retake quizzes on weak topics."
    elif avg_score < 80:
        recommendation = "Good progress. Focus on weak concepts to improve your mastery."
    else:
        recommendation = "Excellent performance! You can explore advanced materials."

    return {
        "progress": {
            "completed_modules": completed_modules,
            "total_modules": total_modules,
            "percentage": progress_percentage,
        },
        "performance": {
            "average_score": avg_score,
            "strong_concepts": strong_concepts,
            "weak_concepts": weak_concepts,
            "recommendation": recommendation,
        },
    }

