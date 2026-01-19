from django.urls import path
from .views import DocumentUploadView, DocumentStatusSSEView, DocumentAnalyticsView

urlpatterns = [
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("<int:pk>/status/", DocumentStatusSSEView.as_view(), name="document-status"),
    path("<int:pk>/analytics/", DocumentAnalyticsView.as_view(), name="document-analytics"),
]

