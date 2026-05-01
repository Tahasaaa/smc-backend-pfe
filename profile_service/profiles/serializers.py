from rest_framework import serializers
from .models import Profile


class ProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            "id",
            "username",
            "email",
            "full_name",
            "role",
            "timezone",
            "avatar",
            "avatar_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "username",
            "email",
            "role",
            "created_at",
            "updated_at",
            "avatar_url",
        ]

    def get_avatar_url(self, obj):
        request = self.context.get("request")
        if obj.avatar and request:
            return request.build_absolute_uri(obj.avatar.url)
        if obj.avatar:
            return obj.avatar.url
        return None


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            "full_name",
            "timezone",
        ]


class AvatarUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["avatar"]

    def validate_avatar(self, value):
        if not value:
            raise serializers.ValidationError("No avatar file provided.")

        max_size_mb = 3
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"Avatar must be smaller than {max_size_mb} MB."
            )

        valid_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
        if value.content_type not in valid_types:
            raise serializers.ValidationError(
                "Only JPG, PNG, WEBP, or GIF images are allowed."
            )

        return value