from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Profile
from .serializers import (
    AvatarUploadSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
)


def get_or_create_profile_from_token_user(user):
    username = getattr(user, "username", "") or ""
    email = getattr(user, "email", "") or ""
    full_name = getattr(user, "full_name", "") or ""
    role = getattr(user, "role", "NOC Engineer") or "NOC Engineer"

    if not username:
        username = email.split("@")[0] if email and "@" in email else "unknown_user"

    profile, created = Profile.objects.get_or_create(
        username=username,
        defaults={
            "email": email or f"{username}@local.profile",
            "full_name": full_name,
            "role": role,
            "timezone": "Africa/Tunis",
        },
    )

    updated = False

    if email and profile.email != email:
        profile.email = email
        updated = True

    if full_name and profile.full_name != full_name:
        profile.full_name = full_name
        updated = True

    if role and profile.role != role:
        profile.role = role
        updated = True

    if updated:
        profile.save()

    return profile, created


class ProfileMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, created = get_or_create_profile_from_token_user(request.user)

        serializer = ProfileSerializer(profile, context={"request": request})

        return Response(
            {
                "created": created,
                "profile": serializer.data,
            }
        )

    def put(self, request):
        profile, _ = get_or_create_profile_from_token_user(request.user)

        serializer = ProfileUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = ProfileSerializer(
            profile,
            context={"request": request},
        )

        return Response(
            {
                "message": "Profile updated successfully.",
                "profile": response_serializer.data,
            }
        )


class ProfileAvatarUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile, _ = get_or_create_profile_from_token_user(request.user)

        serializer = AvatarUploadSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = ProfileSerializer(
            profile,
            context={"request": request},
        )

        return Response(
            {
                "message": "Avatar uploaded successfully.",
                "profile": response_serializer.data,
            }
        )

    def delete(self, request):
        profile, _ = get_or_create_profile_from_token_user(request.user)

        if profile.avatar:
            profile.avatar.delete(save=False)

        profile.avatar = None
        profile.save()

        response_serializer = ProfileSerializer(
            profile,
            context={"request": request},
        )

        return Response(
            {
                "message": "Avatar removed successfully.",
                "profile": response_serializer.data,
            }
        )