

import uuid

from django.conf import settings
from django.db import models


class RegistrationVerification(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registration_verification",
    )

    phone_number = models.CharField(max_length=20)

    email_otp_hash = models.CharField(max_length=128, blank=True)
    phone_otp_hash = models.CharField(max_length=128, blank=True)

    email_otp_expires_at = models.DateTimeField(null=True, blank=True)
    phone_otp_expires_at = models.DateTimeField(null=True, blank=True)

    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    email_attempts = models.PositiveSmallIntegerField(default=0)
    phone_attempts = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Verification for user {self.user_id}"
