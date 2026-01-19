from rest_framework import serializers


class DocumentUploadSerializer(serializers.Serializer):
    """Serializer for validating document uploads."""

    file = serializers.FileField(write_only=True)

    def validate_file(self, file_obj):
        max_size = 50 * 1024 * 1024  # 50MB
        if file_obj.size > max_size:
            raise serializers.ValidationError("File exceeds 50MB limit.")

        filename = (file_obj.name or "").lower()
        content_type = (getattr(file_obj, "content_type", "") or "").lower()
        if not filename.endswith(".pdf"):
            raise serializers.ValidationError("Only PDF uploads are allowed.")
        if content_type and "pdf" not in content_type:
            raise serializers.ValidationError("Only PDF uploads are allowed.")

        return file_obj

