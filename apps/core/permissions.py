from rest_framework.permissions import BasePermission


class IsOwnerOrStaff(BasePermission):
    """
    Allows access when the `user_id` URL kwarg matches the authenticated user,
    or when the caller is staff.
    """

    message = "You may only access your own resources."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        target = view.kwargs.get("user_id")
        return target is not None and str(target) == str(user.pk)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_staff:
            return True
        owner_id = getattr(obj, "user_id", None) or getattr(obj, "pk", None)
        return str(owner_id) == str(user.pk)
