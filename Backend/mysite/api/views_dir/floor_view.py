from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView, Response

from ..models import Floor
from ..serializer_dir.floor_serilizer import FloorSerializer


class FloorViewClass(APIView):
    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    def get(self, request, floor_id=None):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        if role not in [
            "SUPER_ADMIN",
            "ADMIN",
            "BRANCH_MANAGER",
            "COUNTER",
            "WAITER",
            "KITCHEN",
        ]:
            return Response(
                {"success": False, "message": "User Type not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if floor_id:
            # Get single floor
            floor = get_object_or_404(Floor, id=floor_id)
            print(f"floor-> {floor}")

            if role in ["BRANCH_MANAGER", "COUNTER", "WAITER", "KITCHEN"]:
                if not my_branch or floor.branch != my_branch:
                    return Response(
                        {
                            "success": False,
                            "message": "Cannot access floor from other branch",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

            serializer = FloorSerializer(floor)
            return Response({"success": True, "data": serializer.data})

        else:
            # Get all floors with branch filtering
            if role in ["BRANCH_MANAGER", "COUNTER", "WAITER", "KITCHEN"]:
                if not my_branch:
                    return Response(
                        {"success": False, "message": "No branch assigned"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                floors = Floor.objects.filter(branch=my_branch)
            else:
                # SUPER_ADMIN and ADMIN can see all floors
                floors = Floor.objects.all()

            serializer = FloorSerializer(floors, many=True)
            return Response({"success": True, "data": serializer.data})

    def post(self, request):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch
        comming_branch = request.data.get("branch")

        # 1. Permission check - who can create floors?
        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {
                    "success": False,
                    "error": "Permission denied",
                    "message": "You don't have permission to create floors!",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. Prepare data for creation
        data = request.data.copy()

        # 3. Handle branch assignment based on role
        if role == "BRANCH_MANAGER":
            # Branch managers can only create floors for their own branch
            if not my_branch:
                return Response(
                    {"success": False, "message": "No branch assigned"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Force the branch to manager's branch, ignore any provided branch
            data["branch"] = my_branch.id

        else:  # ADMIN or SUPER_ADMIN
            # For admin/super_admin, branch is required
            if not comming_branch:
                return Response(
                    {
                        "success": False,
                        "message": "Branch is required",
                        "error": "Please specify a branch for the floor",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 4. Check if floor number already exists in the same branch
        floor_number = data.get("floor_number")
        branch_id = data.get("branch")

        if floor_number and branch_id:
            existing_floor = Floor.objects.filter(
                floor_number=floor_number, branch_id=branch_id
            ).first()

            if existing_floor:
                return Response(
                    {
                        "success": False,
                        "message": "Floor number already exists",
                        "error": f"Floor #{floor_number} already exists in this branch",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 5. Create the floor using serializer
        serializer = FloorSerializer(data=data)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Floor created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        # 6. Handle validation errors
        return Response(
            {
                "success": False,
                "message": "Validation error",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def patch(self, request, floor_id):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch
        comming_branch = request.data.get("branch")

        # 1. Permission check
        if role not in ["ADMIN", "SUPER_ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {
                    "success": False,
                    "error": "Permission denied",
                    "message": "You don't have permission to update floor!",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. Get the floor object
        try:
            floor = Floor.objects.get(id=floor_id)
        except Floor.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": "Not found",
                    "message": f"Floor with id {floor_id} does not exist",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. BRANCH_MANAGER can only update their own branch floors
        if role == "BRANCH_MANAGER":
            if not my_branch:
                return Response(
                    {"success": False, "message": "No branch assigned"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if floor.branch != my_branch:
                return Response(
                    {
                        "success": False,
                        "error": "Permission denied",
                        "message": "You can only update floors in your own branch",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Prevent BRANCH_MANAGER from changing branch
            if comming_branch and int(comming_branch) != my_branch.id:
                return Response(
                    {
                        "success": False,
                        "error": "Permission denied",
                        "message": "You cannot change the branch of a floor",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Force branch to manager's branch
            data = request.data.copy()
            data["branch"] = my_branch.id

        # 4. ADMIN/SUPER_ADMIN can update any floor
        else:  # role in ["ADMIN", "SUPER_ADMIN"]
            data = request.data.copy()
            # If branch not specified, keep existing branch
            if "branch" not in data:
                data["branch"] = floor.branch.id

        serializer = FloorSerializer(floor, data=data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Floor updated successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,  # Changed from 201 to 200 for updates
            )

        # 6. Validation errors
        return Response(
            {
                "success": False,
                "message": "Validation error",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,  # Changed from 403 to 400
        )

    def delete(self, request, floor_id):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        # 1. Permission check - who can delete?
        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {
                    "success": False,
                    "error": "Permission denied",
                    "message": "You don't have permission to delete floors!",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. Get the floor object
        try:
            floor = Floor.objects.get(id=floor_id)
        except Floor.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": "Not found",
                    "message": f"Floor with id {floor_id} does not exist",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. Check if floor has active orders (optional - business logic)
        # Uncomment if you want to prevent deletion of floors with active orders

        if floor.active_orders.exists():
            return Response(
                {
                    "success": False,
                    "error": "Cannot delete",
                    "message": "Floor has active orders. Complete orders first.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Branch permission check
        if role == "BRANCH_MANAGER":
            if not my_branch:
                return Response(
                    {"success": False, "message": "No branch assigned"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if floor.branch != my_branch:
                return Response(
                    {
                        "success": False,
                        "error": "Permission denied",
                        "message": "You can only delete floors from your own branch",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # 5. Perform deletion
        try:
            floor.delete()
            return Response(
                {
                    "success": True,
                    "message": f"Floor #{floor_id} deleted successfully",
                    "deleted_id": floor_id,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "error": "Deletion failed",
                    "message": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
