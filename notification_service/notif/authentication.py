from types import SimpleNamespace

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class TokenUser(SimpleNamespace):
    @property
    def is_authenticated(self):
        return True


class ServiceJWTAuthentication(JWTAuthentication):
    """
    Validate JWT issued by auth service using the shared SECRET_KEY.
    Build a lightweight authenticated user object from token claims.
    """

    def get_user(self, validated_token):
        user_id = validated_token.get("user_id")
        email = validated_token.get("email")
        role = validated_token.get("role")
        permissions = validated_token.get("permissions", [])

        if not user_id:
            raise InvalidToken("Token missing user_id")

        return TokenUser(
            id=user_id,
            email=email or "",
            role=role,
            permissions=permissions,
        )