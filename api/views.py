import random
from datetime import timedelta

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.views import APIView

from api.permissions import IsAdminUser
from .models import User, AuthLog, VerificationCode
from .serializers import (
    LoginSerializer,
    VerifyCodeSerializer,
    ChangePasswordSerializer,
)


def get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0]
    return request.META.get("REMOTE_ADDR")


def patch_authenticated(user):
    setattr(user, "is_authenticated", True)
    return user


def resolve_authenticated_db_user(token_user):
    user_id = getattr(token_user, "id", None) or getattr(token_user, "user_id", None)
    email = getattr(token_user, "email", None)

    db_user = None

    if user_id:
        db_user = User.objects.select_related("role").filter(id=user_id).first()

    if db_user is None and email:
        db_user = User.objects.select_related("role").filter(email=email).first()

    return db_user


@api_view(["POST"])
def login(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    try:
        user = User.objects.select_related("role").get(email=email)
    except User.DoesNotExist:
        AuthLog.objects.create(
            user=None,
            email=email,
            action="login_failed",
            ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            detail="Email not found",
        )
        return Response(
            {"error": "Invalid email or password"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not check_password(password, user.password):
        AuthLog.objects.create(
            user=user,
            email=email,
            action="login_failed",
            ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            detail="Wrong password",
        )
        return Response(
            {"error": "Invalid email or password"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    code = str(random.randint(100000, 999999))

    VerificationCode.objects.filter(user=user, is_used=False).update(is_used=True)

    VerificationCode.objects.create(
        user=user,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    try:
        send_mail(
            subject="Your verification code",
            message=f"Your verification code is: {code}",
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "no-reply@yourapp.com"
            ),
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        AuthLog.objects.create(
            user=user,
            email=email,
            action="verification_failed",
            ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            detail=f"Email sending failed: {str(e)}",
        )
        return Response(
            {"error": "Unable to send verification email. Check Mailtrap SMTP settings."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    AuthLog.objects.create(
        user=user,
        email=email,
        action="verification_code_sent",
        ip=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        detail="Verification code sent by email",
    )

    return Response(
        {
            "message": "Verification code sent to your email",
            "requires_verification": True,
            "email": user.email,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def verify_code(request):
    serializer = VerifyCodeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"]
    code = serializer.validated_data["code"]

    try:
        user = User.objects.select_related("role").get(email=email)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    verification = VerificationCode.objects.filter(
        user=user,
        code=code,
        is_used=False,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()

    if not verification:
        AuthLog.objects.create(
            user=user,
            email=email,
            action="verification_failed",
            ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            detail="Invalid or expired verification code",
        )
        return Response(
            {"error": "Invalid or expired verification code"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    verification.is_used = True
    verification.save()

    token = AccessToken()
    token["user_id"] = user.id
    token["email"] = user.email
    token["role"] = user.role.role if user.role else None
    token["permissions"] = user.role.permissions if user.role else []
    token["fullname"] = user.fullname

    AuthLog.objects.create(
        user=user,
        email=email,
        action="verification_success",
        ip=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        detail="Verification code validated successfully",
    )

    AuthLog.objects.create(
        user=user,
        email=email,
        action="login_success",
        ip=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        detail="User logged in successfully",
    )

    return Response(
        {
            "token": str(token),
            "user": {
                "id": user.id,
                "fullname": user.fullname,
                "email": user.email,
                "role": user.role.role if user.role else None,
                "permissions": user.role.permissions if user.role else [],
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    patch_authenticated(request.user)

    AuthLog.objects.create(
        user=None,
        email=getattr(request.user, "email", None),
        action="logout",
        ip=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        detail="User logged out",
    )

    return Response({"message": "Logout successful"})


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdminUser])
def get_all_users(request):
    patch_authenticated(request.user)

    users = User.objects.select_related("role").all()
    data = [
        {
            "id": u.id,
            "fullname": u.fullname,
            "email": u.email,
            "role": u.role.role if u.role else None,
            "permissions": u.role.permissions if u.role else [],
        }
        for u in users
    ]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user(request, user_id):
    patch_authenticated(request.user)

    try:
        user = User.objects.select_related("role").get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    AuthLog.objects.create(
        user=None,
        email=getattr(request.user, "email", None),
        action="get_user",
        ip=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        detail=f"Viewed user with id={user_id}",
    )

    return Response(
        {
            "id": user.id,
            "fullname": user.fullname,
            "email": user.email,
            "role": user.role.role if user.role else None,
            "permissions": user.role.permissions if user.role else [],
        }
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated, IsAdminUser])
def delete_user(request, user_id):
    patch_authenticated(request.user)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    deleted_email = user.email
    user.delete()

    AuthLog.objects.create(
        user=None,
        email=getattr(request.user, "email", None),
        action="delete_user",
        ip=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        detail=f"Deleted user {deleted_email} (id={user_id})",
    )

    return Response({"message": "User deleted"})


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdminUser])
def get_logs(request):
    patch_authenticated(request.user)

    logs = AuthLog.objects.select_related("user").all()[:100]

    data = [
        {
            "id": l.id,
            "user": l.user.email if l.user else l.email,
            "action": l.action,
            "ip": l.ip,
            "detail": l.detail,
            "created_at": l.created_at,
        }
        for l in logs
    ]
    return Response(data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        db_user = resolve_authenticated_db_user(request.user)

        if db_user is None:
            return Response(
                {"detail": "Authenticated user not found in database."},
                status=status.HTTP_404_NOT_FOUND,
            )

        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]

        if not check_password(current_password, db_user.password):
            AuthLog.objects.create(
                user=db_user,
                email=db_user.email,
                action="change_password_failed",
                ip=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                detail="Current password is incorrect",
            )
            return Response(
                {"detail": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        db_user.password = make_password(new_password)
        db_user.save(update_fields=["password"])

        AuthLog.objects.create(
            user=db_user,
            email=db_user.email,
            action="change_password_success",
            ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            detail="Password updated successfully",
        )

        return Response(
            {"message": "Password updated successfully."},
            status=status.HTTP_200_OK,
        )