import hashlib
import secrets
from datetime import timedelta
from twilio.rest import Client
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.hashers import make_password, check_password
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from twilio.base.exceptions import TwilioRestException
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import RegistrationVerification
from .serializers import (
    RegisterSerializer,
    EmailOrUsernameTokenObtainPairSerializer,
)

User = get_user_model()




class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_number = serializer.validated_data["phone_number"]

        # Generate separate six-digit OTPs.
        email_otp = f"{secrets.randbelow(1_000_000):06d}"
        

        now = timezone.now()

        try:
            with transaction.atomic():
                user = serializer.save()


                RegistrationVerification.objects.create(
                        user=user,
                        phone_number=phone_number,
                        email_otp_hash=make_password(email_otp),
                        phone_otp_hash="",
                        email_otp_expires_at=now + timedelta(minutes=10),
                        phone_otp_expires_at=None,
)

        except Exception:
            return Response(
                {"message": "Registration could not be completed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            sent = send_mail(
                subject="Smart Study AI - Email Verification OTP",
                message=(
                    f"Hello {user.username},\n\n"
                    f"Your email verification OTP is: {email_otp}\n\n"
                    "This code expires in 10 minutes.\n"
                    "Do not share this code with anyone."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

            if not sent:
                raise RuntimeError("Email was not sent.")

        except Exception:
            # Remove the incomplete account so the user can register again.
            user.delete()
            return Response(
                {
                    "message": (
                        "Verification email could not be sent. "
                        "Please check the email configuration and try again."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


        try:
             client = Client(
             settings.TWILIO_ACCOUNT_SID,
             settings.TWILIO_AUTH_TOKEN,
    )

             client.verify.v2.services(
             settings.TWILIO_VERIFY_SERVICE_SID
    ).       verifications.create(
        to=phone_number,
        channel="sms",
    )


        except Exception as e:
            print("TWILIO SMS ERROR:", repr(e))
            user.delete()
            return Response(
        {
            "message": (
                "Phone OTP could not be sent. "
                "Check Twilio settings and verified phone number."
            )
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )

        

        return Response(
            {
                "message": (
                    "Registration started. Enter the email OTP and "
                    "development phone OTP to verify your account."
                ),
                "user_id": user.id,
                "email": user.email,
                "verification_required": True,
            },
            status=status.HTTP_201_CREATED,
        )





class VerifyRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = str(request.data.get("email") or "").strip().lower()
        email_otp = str(request.data.get("email_otp") or "").strip()
        phone_otp = str(request.data.get("phone_otp") or "").strip()

        if not email or not email_otp or not phone_otp:
            return Response(
                {
                    "message": (
                        "Email, email OTP and phone OTP are required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email__iexact=email).first()

        if not user:
            return Response(
                {"message": "Registration could not be verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            verification = user.registration_verification
        except RegistrationVerification.DoesNotExist:
            return Response(
                {"message": "Registration could not be verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.is_active:
            return Response(
                {
                    "message": "This account is already verified.",
                    "verified": True,
                },
                status=status.HTTP_200_OK,
            )

        now = timezone.now()
        errors = {}

        # 1. Verify email OTP using the existing email OTP logic.
        if not verification.email_verified:
            if verification.email_attempts >= 5:
                errors["email_otp"] = (
                    "Too many attempts. Please register again."
                )
            elif (
                not verification.email_otp_expires_at
                or now > verification.email_otp_expires_at
            ):
                errors["email_otp"] = (
                    "Email OTP expired. Please register again."
                )
            elif not check_password(
                email_otp,
                verification.email_otp_hash,
            ):
                verification.email_attempts += 1
                errors["email_otp"] = "Invalid email OTP."
            else:
                verification.email_verified = True
                verification.email_otp_hash = ""
                verification.email_otp_expires_at = None

        # 2. Verify phone OTP through Twilio Verify.
        if not verification.phone_verified:
            if verification.phone_attempts >= 5:
                errors["phone_otp"] = (
                    "Too many attempts. Please register again."
                )
            else:
                try:
                    client = Client(
                        settings.TWILIO_ACCOUNT_SID,
                        settings.TWILIO_AUTH_TOKEN,
                    )

                    result = client.verify.v2.services(
                        settings.TWILIO_VERIFY_SERVICE_SID
                    ).verification_checks.create(
                        to=verification.phone_number,
                        code=phone_otp,
                    )

                    if result.status == "approved":
                        verification.phone_verified = True
                        verification.phone_otp_hash = ""
                        verification.phone_otp_expires_at = None
                    else:
                        verification.phone_attempts += 1
                        errors["phone_otp"] = (
                            "Invalid or expired phone OTP."
                        )

                except TwilioRestException:
                    verification.phone_attempts += 1
                    errors["phone_otp"] = (
                        "Invalid or expired phone OTP."
                    )

                except Exception:
                    errors["phone_otp"] = (
                        "Unable to verify phone OTP. "
                        "Please check Twilio settings and try again."
                    )

        # 3. Save verification status and attempt counters.
        verification.save()

        if errors:
            return Response(
                {
                    "message": "Please check the OTP entered.",
                    "errors": errors,
                    "email_verified": verification.email_verified,
                    "phone_verified": verification.phone_verified,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Activate account only after both verifications succeed.
        if (
            verification.email_verified
            and verification.phone_verified
        ):
            user.is_active = True
            user.save(update_fields=["is_active"])

            return Response(
                {
                    "message": (
                        "Email and phone verification successful. "
                        "You can now log in."
                    ),
                    "verified": True,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "message": "Both verifications are not complete yet.",
                "email_verified": verification.email_verified,
                "phone_verified": verification.phone_verified,
            },
            status=status.HTTP_200_OK,
        )


class EmailOrUsernameLoginView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenObtainPairSerializer


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        })


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip()

        if not email:
            return Response(
                {"email": "Please enter your email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email__iexact=email).first()

        # Keep the response identical whether the account exists or not.
        if user and user.is_active:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            frontend_url = getattr(
                settings,
                "FRONTEND_BASE_URL",
                "http://127.0.0.1:8000",
            ).rstrip("/")

            reset_link = (
                f"{frontend_url}/reset-password.html"
                f"?uid={uid}&token={token}"
            )

            subject = "Smart Study AI - Reset your password"
            message = (
                f"Hello {user.username},\n\n"
                "We received a request to reset your Smart Study AI password.\n\n"
                f"Open this link to choose a new password:\n{reset_link}\n\n"
                "If you did not request this, you can ignore this email."
            )

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception:
                # Do not expose email/account details to the requester.
                return Response(
                    {
                        "message": (
                            "If an account exists for that email, "
                            "a password reset link will be sent."
                        )
                    },
                    status=status.HTTP_200_OK,
                )

        return Response(
            {
                "message": (
                    "If an account exists for that email, "
                    "a password reset link will be sent."
                )
            },
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        uid = request.data.get("uid", "")
        token = request.data.get("token", "")
        password = request.data.get("password", "")
        password2 = request.data.get("password2", "")

        if not all([uid, token, password, password2]):
            return Response(
                {"message": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if password != password2:
            return Response(
                {"password2": "Passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(password) < 8:
            return Response(
                {"password": "Password must contain at least 8 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {"message": "This reset link is invalid or expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"message": "This reset link is invalid or expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(password)
        user.save(update_fields=["password"])

        return Response(
            {"message": "Password reset successful. Please log in."},
            status=status.HTTP_200_OK,
        )
