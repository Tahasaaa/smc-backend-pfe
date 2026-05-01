from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import User

class CustomJWTAuthentication(JWTAuthentication):
    """
    Custom JWTAuthentication that works with the existing User model.
    Patches `is_authenticated` so DRF permissions can work.
    """
    def get_user(self, validated_token):
        user_id = validated_token.get('user_id')
        if not user_id:
            return None
        try:
            user = User.objects.select_related('role').get(id=user_id)
            setattr(user, 'is_authenticated', True)
            return user
        except User.DoesNotExist:
            return None