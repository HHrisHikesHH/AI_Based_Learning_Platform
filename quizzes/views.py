from django.db import transaction
from django.utils import timezone
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from feedback.tasks import generate_personalized_feedback, update_user_progress, update_document_stats
from .models import Quiz, QuizAttempt, Question, UserAnswer
from .serializers import QuizQuestionSerializer


class QuizStartView(APIView):
    """Start a quiz attempt and return questions."""

    permission_classes = [IsAuthenticated]

    def post(self, request, quiz_id: int, *args, **kwargs):
        try:
            quiz = (
                Quiz.objects.with_questions()
                .select_related("module")
                .get(id=quiz_id)
            )
        except Quiz.DoesNotExist as exc:
            raise Http404 from exc

        user = request.user
        attempt_number = (
            QuizAttempt.objects.filter(user=user, quiz=quiz).count() + 1
        )

        attempt = QuizAttempt.objects.create(
            user=user,
            quiz=quiz,
            attempt_number=attempt_number,
        )

        questions = quiz.questions.all().order_by("question_order")
        serialized = QuizQuestionSerializer(questions, many=True).data

        return Response(
            {
                "attempt_id": attempt.id,
                "questions": serialized,
                "estimated_duration_minutes": quiz.estimated_duration_minutes or 10,
            },
            status=status.HTTP_201_CREATED,
        )


class QuizSubmitView(APIView):
    """Submit answers for a quiz attempt atomically."""

    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_id: int, *args, **kwargs):
        user = request.user
        answers_data = request.data.get("answers") or []
        if not isinstance(answers_data, list) or not answers_data:
            return Response(
                {"detail": "answers must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            try:
                attempt = (
                    QuizAttempt.objects.select_for_update()
                    .select_related("quiz__module__document")
                    .get(id=attempt_id, user_id=user.id)
                )
            except QuizAttempt.DoesNotExist as exc:
                raise Http404 from exc

            if attempt.completed_at:
                return Response(
                    {"detail": "Quiz already submitted"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            questions = Question.objects.filter(quiz_id=attempt.quiz_id).in_bulk()
            user_answers: list[UserAnswer] = []
            correct_count = 0

            for ad in answers_data:
                qid = ad.get("question_id")
                if qid not in questions:
                    return Response(
                        {"detail": f"Invalid question_id: {qid}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                question = questions[qid]
                user_answer = (ad.get("user_answer") or "").strip()
                correct_answer = (question.correct_answer or "").strip()
                
                # Normalize answers for comparison
                # If user_answer starts with a letter followed by ". ", extract just the letter
                # e.g., "C. Some text..." -> "C"
                user_answer_normalized = user_answer.lower()
                if user_answer_normalized and len(user_answer_normalized) > 2 and user_answer_normalized[1] == '.':
                    user_answer_normalized = user_answer_normalized[0]
                
                correct_answer_normalized = correct_answer.lower()
                if correct_answer_normalized and len(correct_answer_normalized) > 2 and correct_answer_normalized[1] == '.':
                    correct_answer_normalized = correct_answer_normalized[0]
                
                # Also check if correct_answer matches any of the full option texts
                options = question.options or []
                is_correct = False
                
                # First, try direct comparison (normalized)
                if user_answer_normalized == correct_answer_normalized:
                    is_correct = True
                else:
                    # Check if correct_answer is a letter and user_answer starts with that letter
                    if len(correct_answer_normalized) == 1 and user_answer_normalized.startswith(correct_answer_normalized):
                        is_correct = True
                    # Check if user_answer matches the full correct option text
                    elif user_answer.lower() == correct_answer.lower():
                        is_correct = True
                    # Check if correct_answer matches any option in the list
                    elif correct_answer in options:
                        correct_option_text = options[options.index(correct_answer)]
                        if user_answer.lower() == correct_option_text.lower():
                            is_correct = True
                
                if is_correct:
                    correct_count += 1

                user_answers.append(
                    UserAnswer(
                        attempt=attempt,
                        question=question,
                        user_answer=user_answer,
                        is_correct=is_correct,
                        time_spent_seconds=ad.get("time_spent_seconds") or 0,
                        confidence_level=ad.get("confidence_level"),
                    )
                )

            UserAnswer.objects.bulk_create(user_answers)

            total_questions = len(answers_data)
            score = (correct_count / total_questions) * 100.0 if total_questions else 0.0
            total_time = sum(ad.get("time_spent_seconds") or 0 for ad in answers_data)

            attempt.score = score
            attempt.completed_at = timezone.now()
            attempt.time_spent_seconds = total_time
            attempt.save(update_fields=["score", "completed_at", "time_spent_seconds"])

        # Update progress and stats asynchronously (or synchronously if Celery not available)
        module = attempt.quiz.module
        try:
            # Try Celery first, fall back to synchronous execution
            try:
                update_user_progress.delay(user.id, module.id)
                update_document_stats.delay(user.id, module.document_id)
                generate_personalized_feedback.delay(attempt.id)
            except Exception:
                # Celery not available, run synchronously
                update_user_progress(user.id, module.id)
                update_document_stats(user.id, module.document_id)
                generate_personalized_feedback(attempt.id)
        except Exception as exc:
            # Best-effort; don't block response
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Failed to update progress/feedback: %s", exc)

        # Prepare detailed results
        answers_qs = (
            UserAnswer.objects.filter(attempt=attempt)
            .select_related("question")
            .order_by("question__question_order")
        )
        results = []
        for ua in answers_qs:
            q = ua.question
            results.append(
                {
                    "question_id": q.id,
                    "your_answer": ua.user_answer,
                    "correct_answer": q.correct_answer,
                    "is_correct": ua.is_correct,
                    "explanation": q.explanation,
                }
            )

        return Response(
            {
                "score": score,
                "correct_answers": correct_count,
                "total_questions": total_questions,
                "time_spent_seconds": total_time,
                "feedback_status": "GENERATING",
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


class QuizFeedbackView(APIView):
    """Retrieve feedback status and content for an attempt."""

    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id: int, *args, **kwargs):
        from feedback.models import FeedbackReport

        try:
            attempt = QuizAttempt.objects.select_related("user").get(
                id=attempt_id, user_id=request.user.id
            )
        except QuizAttempt.DoesNotExist as exc:
            raise Http404 from exc

        report = FeedbackReport.objects.filter(attempt=attempt).first()
        if not report:
            return Response(
                {"status": "GENERATING", "feedback": None},
                status=status.HTTP_200_OK,
            )

        feedback = {
            "overall_feedback": report.overall_feedback,
            "strengths": report.strengths,
            "weaknesses": report.weaknesses,
            "recommended_topics": report.recommended_topics,
            "personalized_message": report.personalized_message,
        }

        return Response(
            {
                "status": "COMPLETED",
                "feedback": feedback,
            },
            status=status.HTTP_200_OK,
        )

