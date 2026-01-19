"""
Celery tasks for users app
"""
from celery import shared_task


@shared_task
def send_welcome_email(user_id):
    """
    Send welcome email to new user
    """
    # TODO: Implement email sending logic
    pass

