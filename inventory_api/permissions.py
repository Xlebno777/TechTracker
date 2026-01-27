from rest_framework.permissions import BasePermission, SAFE_METHODS


def _is_admin(user):
    return user.is_staff or user.groups.filter(name='Admins').exists()


class PrintJobPermission(BasePermission):
    """
    Read: any authenticated user.
    Create: staff or users in Agent group.
    Update/Delete: staff only.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if request.method in SAFE_METHODS:
            return True

        if request.method == 'POST':
            return _is_admin(user) or user.groups.filter(name='Agent').exists()

        return _is_admin(user)


class PrinterAgentPermission(BasePermission):
    """
    Allow printer sync actions for staff or users in Agent group.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return _is_admin(user) or user.groups.filter(name='Agent').exists()
