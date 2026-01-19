from django.urls import path

from .views import QuizStartView, QuizSubmitView, QuizFeedbackView

urlpatterns = [
    path("<int:quiz_id>/start/", QuizStartView.as_view(), name="quiz-start"),
    path("attempts/<int:attempt_id>/submit/", QuizSubmitView.as_view(), name="quiz-submit"),
    path("attempts/<int:attempt_id>/feedback/", QuizFeedbackView.as_view(), name="quiz-feedback"),
]


