from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """
    Allows access only to users with role 'admin'.
    """

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'role', '').lower() == 'admin'


class HasPermissionClaim(BasePermission):
    """
    Check if a permission exists inside JWT claim list.
    Set required_permission on the view if needed.
    """

    required_permission = None

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, 'is_authenticated', False):
            return False

        required = getattr(view, 'required_permission', None)
        if not required:
            return True

        permissions = getattr(user, 'permissions', []) or []
        return required in permissions