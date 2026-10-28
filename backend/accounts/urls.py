

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView,
    VerifyRegistrationView,
    ProfileView,
    EmailOrUsernameLoginView,
    ForgotPasswordView,
    ResetPasswordView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", EmailOrUsernameLoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path(
        "forgot-password/",
        ForgotPasswordView.as_view(),
        name="forgot-password",
    ),
    path(
        "reset-password/",
        ResetPasswordView.as_view(),
        name="reset-password",
    ),
    path(
    "verify-registration/",
    VerifyRegistrationView.as_view(),
    name="verify-registration",
),
    
]
