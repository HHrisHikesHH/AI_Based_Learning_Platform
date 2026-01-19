from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model extending AbstractUser"""
    email = models.EmailField(unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email'], name='idx_users_email'),
        ]

    def __str__(self):
        return self.email
