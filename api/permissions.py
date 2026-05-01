from rest_framework.permissions import BasePermission

class IsAdminUser(BasePermission):
    """
    Allows access only to users with role 'admin'.
    """

    def has_permission(self, request, view):
        user = getattr(request.user, 'id', None)
        if not user:
            return False

        from .models import User
        try:
            user_obj = User.objects.select_related('role').get(id=request.user.id)
        except User.DoesNotExist:
            return False

        return user_obj.role and user_obj.role.role.lower() == 'admin'