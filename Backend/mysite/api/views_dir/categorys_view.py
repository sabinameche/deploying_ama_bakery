from rest_framework import status
from rest_framework.views import APIView, Response
from django.shortcuts import get_object_or_404
from ..models import ProductCategory
from ..serializer_dir.category_serializer import ProductCategorySerializer


class CategoryViewClass(APIView):
    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    def get(self, request, id=None):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        if not role:
            return Response(
                {"success": False, "message": "Unauthorized"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        if id:
            try:
                if role in ["SUPER_ADMIN", "ADMIN"]:
                    category = ProductCategory.objects.get(id=id)
                else:
                    category = ProductCategory.objects.get(
                        id=id, branch=my_branch
                    )

            except ProductCategory.DoesNotExist:
                return Response(
                    {"success": False, "message": "Category not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = ProductCategorySerializer(category)
            return Response(
                {"success": True, "data": serializer.data},
                status=status.HTTP_200_OK,
            )

        if role in [
            "SUPER_ADMIN",
            "ADMIN",
            "BRANCH_MANAGER",
            "WAITER",
            "COUNTER",
            "KITCHEN",
        ]:
            if role in ["SUPER_ADMIN", "ADMIN"]:
                categories = ProductCategory.objects.all()
            else:
                categories = ProductCategory.objects.filter(branch=my_branch)

            serializer = ProductCategorySerializer(categories, many=True)
            return Response(
                {"success": True, "data": serializer.data},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"success": False, "message": "Insufficient permissions"},
            status=status.HTTP_403_FORBIDDEN,
        )
    def post(self, request):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        # Permission check - who can create categories?
        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {
                    "success": False,
                    "message": "You don't have permission to create categories.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get and validate category name
        new_name = request.data.get("name", "").strip()

        if not new_name:
            return Response(
                {
                    "success": False,
                    "message": "Category name is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for duplicate category name in the same branch
        # Case-insensitive check
        if ProductCategory.objects.filter(
            branch=my_branch, name__iexact=new_name
        ).exists():
            return Response(
                {
                    "success": False,
                    "message": f"A category named '{new_name}' already exists in {my_branch.name}.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Prepare data
        data = request.data.copy()

        # SUPER_ADMIN can create categories in any branch
        if role in ["SUPER_ADMIN", "ADMIN"]:
            # If branch is specified in request, use it
            # Otherwise, default to user's branch
            if "branch" not in data:
                data["branch"] = my_branch.id
        else:
            # Non-SUPER_ADMIN users can only create in their own branch
            data["branch"] = my_branch.id

            # If they're trying to specify a different branch, reject it
            if (
                "branch" in request.data
                and int(request.data.get("branch")) != my_branch.id
            ):
                return Response(
                    {
                        "success": False,
                        "message": "You can only create categories in your own branch.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Create the category
        serializer = ProductCategorySerializer(data=data, context={"request": request})

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Category created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                    "message": "Validation failed",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    def patch(self, request, id=None):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        # Permission check
        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {"success": False, "message": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not id:
            return Response(
                {"success": False, "message": "Category ID required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get category - SUPER_ADMIN can access any, others only their branch
            if role in ["SUPER_ADMIN", "ADMIN"]:
                category = ProductCategory.objects.get_object_(id=id)
            else:
                category = ProductCategory.objects.get(id=id, branch=my_branch)
        except ProductCategory.DoesNotExist:
            return Response(
                {"success": False, "message": "Category not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for duplicate name in the same branch
        new_name = request.data.get("name", "").strip()
        if new_name and new_name.lower() != category.name.lower():
            if (
                ProductCategory.objects.filter(
                    branch=category.branch, name__iexact=new_name
                )
                .exclude(id=category.id)
                .exists()
            ):
                return Response(
                    {
                        "success": False,
                        "message": f"Category '{new_name}' already exists.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        # Prepare data - always include current branch for non-SUPER_ADMIN
        data = request.data.copy()
        if role not in ["SUPER_ADMIN", "ADMIN"]:
            data["branch"] = my_branch.id

        # Update
        serializer = ProductCategorySerializer(
            category, data=data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Category updated",
                    "data": serializer.data,
                }
            )

        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, id=None):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        if id:
            if role in ["ADMIN", "SUPER_ADMIN"]:
                category = ProductCategory.objects.get_object_or_404(id=id)
                category.delete()
                return Response(
                    {
                        "success": True,
                        "message": "Category deleted Sucessfully!",
                    }
                )
            if role == "BRANCH_MANAGER":
                category = ProductCategory.objects.get_object_or_404(id=id)
                category.delete()
                return Response(
                    {
                        "success": True,
                        "message": "Category deleted Sucessfully!",
                    }
                )
