from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["Expected an object."]})
        unknown = set(data) - {name for name, field in self.fields.items() if not field.read_only}
        if unknown:
            raise serializers.ValidationError(
                {"non_field_errors": ["Unexpected or read-only fields."]}
            )
        return super().to_internal_value(data)


class ProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)


class CredentialsSerializer(StrictSerializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)


class RegistrationSerializer(CredentialsSerializer):
    username = serializers.RegexField(r"^[A-Za-z0-9_.-]+$", max_length=150, min_length=3)

    def validate(self, data):
        user = get_user_model()(username=data["username"])
        try:
            validate_password(data["password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages}) from error
        return data


class CsrfSerializer(serializers.Serializer):
    csrfToken = serializers.CharField(read_only=True)


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)


class PasswordChangeSerializer(StrictSerializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)


class RecoverySerializer(StrictSerializer):
    token = serializers.CharField(write_only=True, trim_whitespace=False, max_length=100)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)
