from rest_framework import serializers

from .models import Question


class QuizQuestionSerializer(serializers.ModelSerializer):
    """Serializer for quiz questions (without answers)."""

    options = serializers.ListField(child=serializers.CharField())

    class Meta:
        model = Question
        fields = ["id", "question_text", "options", "question_order"]



