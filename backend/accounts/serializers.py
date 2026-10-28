

from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
    )
    password2 = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )
    phone_number = serializers.CharField(
        write_only=True,
        max_length=20,
        trim_whitespace=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "phone_number",
            "password",
            "password2",
            "first_name",
            "last_name",
        ]

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email

    def validate_phone_number(self, value):
        phone = value.strip()
        if not phone:
            raise serializers.ValidationError(
                "Please enter your phone number."
            )
        if len(phone) < 10:
            raise serializers.ValidationError(
                "Please enter a valid phone number."
            )
        return phone

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({
                "password2": "Passwords do not match."
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        validated_data.pop("phone_number")
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        user.is_active = False
        user.save()
        return user


class EmailOrUsernameTokenObtainPairSerializer(
    TokenObtainPairSerializer
):
    def validate(self, attrs):
        login_value = attrs.get("username", "").strip()

        if "@" in login_value:
            user = User.objects.filter(
                email__iexact=login_value
            ).first()

            if user:
                attrs["username"] = user.username

        return super().validate(attrs)
