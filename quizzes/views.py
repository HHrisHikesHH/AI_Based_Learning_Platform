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
                options = question.options or []
                
                # Normalize answers for comparison
                # Extract letter prefix from user_answer if it exists (e.g., "C. Text..." -> "C")
                user_answer_letter = None
                if user_answer and len(user_answer) >= 2 and user_answer[1] == '.':
                    user_answer_letter = user_answer[0].upper()
                
                # Extract letter prefix from correct_answer if it exists
                correct_answer_letter = None
                if correct_answer and len(correct_answer) >= 2 and correct_answer[1] == '.':
                    correct_answer_letter = correct_answer[0].upper()
                elif correct_answer and len(correct_answer) == 1:
                    # correct_answer is already just a letter
                    correct_answer_letter = correct_answer.upper()
                
                # Determine if answer is correct
                is_correct = False
                
                # Method 1: Compare letters if both have letter prefixes
                if user_answer_letter and correct_answer_letter:
                    if user_answer_letter == correct_answer_letter:
                        is_correct = True
                
                # Method 2: If correct_answer is just a letter, check if user_answer starts with it
                if not is_correct and correct_answer_letter and len(correct_answer) == 1:
                    if user_answer_letter == correct_answer_letter:
                        is_correct = True
                    # Also check if user_answer starts with the letter (case-insensitive)
                    elif user_answer and user_answer[0].upper() == correct_answer_letter:
                        is_correct = True
                
                # Method 3: Direct text comparison (case-insensitive, whitespace-normalized)
                if not is_correct:
                    if user_answer.lower().strip() == correct_answer.lower().strip():
                        is_correct = True
                
                # Method 4: Check if correct_answer matches an option and user_answer matches that option
                if not is_correct and options:
                    # Find which option index the correct_answer refers to
                    correct_option_text = None
                    if correct_answer_letter:
                        # correct_answer is a letter, find the option at that index
                        option_index = ord(correct_answer_letter) - ord('A')
                        if 0 <= option_index < len(options):
                            correct_option_text = options[option_index]
                    elif correct_answer in options:
                        correct_option_text = correct_answer
                    
                    if correct_option_text and user_answer.lower().strip() == correct_option_text.lower().strip():
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

