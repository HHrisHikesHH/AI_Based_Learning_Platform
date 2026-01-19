from django.urls import path
from .views import (
    DocumentAnalyticsView,
    DocumentQuizzesView,
    DocumentStatusSSEView,
    DocumentUploadView,
)

urlpatterns = [
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("<int:pk>/status/", DocumentStatusSSEView.as_view(), name="document-status"),
    path("<int:pk>/analytics/", DocumentAnalyticsView.as_view(), name="document-analytics"),
    path("<int:pk>/quizzes/", DocumentQuizzesView.as_view(), name="document-quizzes"),
]

