from django.urls import path
from .views import ProfileAvatarUploadView, ProfileMeView

urlpatterns = [
    path("profile/me/", ProfileMeView.as_view(), name="profile_me"),
    path("profile/avatar/", ProfileAvatarUploadView.as_view(), name="profile_avatar"),
]