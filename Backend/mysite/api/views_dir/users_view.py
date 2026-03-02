from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import User
from ..serializer_dir.users_serializer import UsersSerializers


class HasUserManagementPermission(permissions.BasePermission):
    """Check if user can manage users based on hierarchy"""

    def has_permission(self, request, view):
        return request.user.is_superuser or getattr(request.user, "user_type", "") in [
            "ADMIN",
            "BRANCH_MANAGER",
        ]


class UserViewClass(APIView):
    permission_classes = [HasUserManagementPermission]

    ROLE_HIERARCHY = {
        "SUPER_ADMIN": 1000,  # Django superuser
        "ADMIN": 100,  # Business admin
        "BRANCH_MANAGER": 50,  # Branch admin
        "COUNTER": 30,  # Counter staff
        "KITCHEN": 30,  # Kitchen staff
        "WAITER": 20,  # Waiter staff
    }

    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    def can_manage_role(self, manager_role, target_role):
        """Check if manager can manage target role based on hierarchy"""
        manager_level = self.ROLE_HIERARCHY.get(manager_role, 0)
        target_level = self.ROLE_HIERARCHY.get(target_role, 0)
        return manager_level > target_level

    def get_queryset(self, request):
        """Get users based on requester's role"""
        role = self.get_user_role(request.user)

        if role == "SUPER_ADMIN":
            return User.objects.all()
        elif role == "ADMIN":
            return User.objects.exclude(is_superuser=True)
        elif role == "BRANCH_MANAGER":
            if branch := getattr(request.user, "branch", None):
                return User.objects.filter(branch=branch)
        return User.objects.none()

    # --- GET (List or Retrieve) ---
    def get(self, request, id=None):
        """Get all users or single user by ID"""
        if id:
            # Get single user
            try:
                user = User.objects.get(id=id)
            except User.DoesNotExist:
                return Response(
                    {"success": False, "message": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Check permission for this specific user
            role = self.get_user_role(request.user)
            if role == "BRANCH_MANAGER":
                if getattr(request.user, "branch") != getattr(user, "branch"):
                    return Response(
                        {"success": False, "message": "Permission denied"},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            serializer = UsersSerializers(user)
            return Response({"success": True, "user": serializer.data})
        else:
            # Get all users
            users = self.get_queryset(request)
            serializer = UsersSerializers(users, many=True)
            return Response(
                {"success": True, "count": users.count(), "users": serializer.data}
            )

    # --- POST (Create) ---
    @transaction.atomic
    def post(self, request):
        """Create new user"""
        creator = request.user
        creator_role = self.get_user_role(creator)

        # Get requested role
        user_type = request.data.get("user_type", "WAITER").upper()

        # Validate role
        if user_type not in self.ROLE_HIERARCHY:
            return Response(
                {"success": False, "message": "Invalid role"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check permission to create this role
        if not self.can_manage_role(creator_role, user_type):
            return Response(
                {"success": False, "message": "Cannot create this role"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Handle branch assignment
        data = request.data.copy()
        if creator_role == "BRANCH_MANAGER":
            if branch := getattr(creator, "branch", None):
                data["branch"] = branch.id
            else:
                return Response(
                    {"success": False, "message": "Branch not assigned"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Validate and save
        serializer = UsersSerializers(data=data, context={"request": request})
        if serializer.is_valid():
            user = serializer.save()

            # Set Django flags
            user.is_staff = user_type in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]
            user.is_superuser = user_type == "SUPER_ADMIN"
            user.created_by = creator
            user.save()

            return Response(
                {
                    "success": True,
                    "message": f"User created as {user_type}",
                    "user": UsersSerializers(user).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- PUT (Update) ---
    @transaction.atomic
    def put(self, request, id=None):
        """Update user information"""
        if not id:
            return Response(
                {"success": False, "message": "User ID required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response(
                {"success": False, "message": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        updater = request.user
        updater_role = self.get_user_role(updater)
        target_role = self.get_user_role(user)

        # Check permissions
        if target_role == "SUPER_ADMIN" and updater_role != "SUPER_ADMIN":
            return Response(
                {"success": False, "message": "Cannot update SUPER_ADMIN"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not self.can_manage_role(updater_role, target_role):
            return Response(
                {"success": False, "message": "Cannot update this user"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Branch check for BRANCH_MANAGER
        if updater_role == "BRANCH_MANAGER":
            if getattr(updater, "branch") != getattr(user, "branch"):
                return Response(
                    {"success": False, "message": "User not in your branch"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Update user
        serializer = UsersSerializers(user, data=request.data, partial=False)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "User updated successfully",
                    "user": serializer.data,
                }
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- DELETE ---
    @transaction.atomic
    def delete(self, request, id=None):
        """Delete user"""
        if not id:
            return Response(
                {"success": False, "message": "User ID required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleter = request.user
        deleter_role = self.get_user_role(deleter)

        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response(
                {"success": False, "message": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Prevent self-deletion
        if deleter.id == user.id:
            return Response(
                {"success": False, "message": "Cannot delete yourself"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check permissions
        target_role = self.get_user_role(user)

        # SUPER_ADMIN can only be deleted by SUPER_ADMIN
        if target_role == "SUPER_ADMIN" and deleter_role != "SUPER_ADMIN":
            return Response(
                {"success": False, "message": "Cannot delete SUPER_ADMIN"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check hierarchy
        if not self.can_manage_role(deleter_role, target_role):
            return Response(
                {"success": False, "message": "Cannot delete this user"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Branch check for BRANCH_MANAGER
        if deleter_role == "BRANCH_MANAGER":
            deleter_branch = getattr(deleter, "branch", None)
            user_branch = getattr(user, "branch", None)

            if deleter_branch != user_branch:
                return Response(
                    {"success": False, "message": "User not in your branch"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Delete user
        username = user.username
        try:
            user.delete()
        except Exception:
            return Response(
                {"success": False, "message": "Cannot delete user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"success": True, "message": f"User '{username}' deleted"})
