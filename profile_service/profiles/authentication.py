import jwt
from django.conf import settings
from rest_framework import authentication, exceptions


class ServiceUser:
    def __init__(self, payload: dict):
        self.payload = payload or {}

        self.id = self.payload.get("user_id") or self.payload.get("id")
        self.user_id = self.payload.get("user_id") or self.payload.get("id")
        self.username = self.payload.get("username", "")
        self.email = self.payload.get("email", "")
        self.role = self.payload.get("role", "NOC Engineer")
        self.full_name = (
            self.payload.get("full_name")
            or self.payload.get("fullname")
            or self.payload.get("name")
            or ""
        )

    @property
    def is_authenticated(self):
        return True

    def __str__(self):
        return self.username or self.email or "service-user"


class ServiceJWTAuthentication(authentication.BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")

        if not auth_header:
            return None

        parts = auth_header.split()

        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise exceptions.AuthenticationFailed("Invalid authorization header format.")

        token = parts[1]

        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"],
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token.")

        user = ServiceUser(payload)
        return (user, token)