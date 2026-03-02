from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Customer
from ..serializer_dir.customer_serializer import CustomerSerializer


class CustomerViewClass(APIView):
    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    # --- GET (List/Retrieve) ---
    def get(self, request, id=None):
        role = self.get_user_role(request.user)
        my_branch = getattr(request.user, "branch", None)

        # 1. Handle KITCHEN role - no access
        if role == "KITCHEN":
            return Response(
                {"success": False, "message": "Insufficient permissions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. Handle GET single customer (with ID)
        if id:
            try:
                customer = Customer.objects.get(id=id)
            except Customer.DoesNotExist:
                return Response(
                    {"success": False, "message": "Customer not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Check permissions for single customer
            if role in ["SUPER_ADMIN", "ADMIN"]:
                # ADMIN and SUPER_ADMIN can view any customer
                pass
            elif role in ["BRANCH_MANAGER", "WAITER", "COUNTER"]:
                # Check if customer belongs to user's branch
                if my_branch and customer.branch != my_branch:
                    return Response(
                        {"success": False, "message": "Customer not in your branch"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                return Response(
                    {"success": False, "message": "Insufficient permissions"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = CustomerSerializer(customer)
            return Response({"success": True, "data": serializer.data})

        # 3. Handle GET all customers (no ID)
        else:
            if role in ["SUPER_ADMIN", "ADMIN"]:
                # SUPER_ADMIN and ADMIN see all customers
                customers = Customer.objects.all()

            elif role in ["BRANCH_MANAGER", "WAITER", "COUNTER"]:
                if not my_branch:
                    return Response(
                        {"success": False, "message": "User not assigned to a branch"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Filter by user's branch
                customers = Customer.objects.filter(branch=my_branch)

            else:
                # Other roles (if any) get no customers
                customers = Customer.objects.none()

            # Apply query filters if provided
            search = request.query_params.get("search")
            if search:
                customers = (
                    customers.filter(name__icontains=search)
                    | customers.filter(phone__icontains=search)
                    | customers.filter(email__icontains=search)
                )

            # Order by date (newest first)
            customers = customers.order_by("-created_at")

            serializer = CustomerSerializer(customers, many=True)

            return Response(
                {"success": True, "count": customers.count(), "data": serializer.data}
            )

    # --- POST (Create) ---
    @transaction.atomic
    def post(self, request):
        role = self.get_user_role(request.user)
        my_branch = getattr(request.user, "branch", None)

        # Check permissions
        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER", "WAITER", "COUNTER"]:
            return Response(
                {"success": False, "message": "Insufficient permissions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Prepare data
        data = request.data.copy()

        # Auto-assign branch for branch-based roles
        if role in ["BRANCH_MANAGER", "WAITER", "COUNTER"]:
            if not my_branch:
                return Response(
                    {"success": False, "message": "User not assigned to a branch"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            data["branch"] = my_branch.id

        # For ADMIN/SUPER_ADMIN, branch must be provided
        elif role in ["ADMIN", "SUPER_ADMIN"]:
            if "branch" not in data:
                return Response(
                    {"success": False, "message": "Branch is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Validate and save
        serializer = CustomerSerializer(data=data)
        if serializer.is_valid():
            customer = serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Customer created successfully",
                    "data": CustomerSerializer(customer).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- PATCH (Partial Update) ---
    @transaction.atomic
    def patch(self, request, id):
        if not id:
            return Response(
                {"success": False, "message": "Customer ID required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        role = self.get_user_role(request.user)
        my_branch = getattr(request.user, "branch", None)

        # Get customer
        try:
            customer = Customer.objects.get(id=id)
        except Customer.DoesNotExist:
            return Response(
                {"success": False, "message": "Customer not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check permissions
        if role in ["SUPER_ADMIN", "ADMIN"]:
            # Can update any customer
            pass
        elif role in ["BRANCH_MANAGER", "WAITER", "COUNTER"]:
            # Can only update customers in their branch
            if not my_branch or customer.branch != my_branch:
                return Response(
                    {
                        "success": False,
                        "message": "Cannot update customer from another branch",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            return Response(
                {"success": False, "message": "Insufficient permissions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Prevent branch change for non-admin users
        data = request.data.copy()
        if role in ["BRANCH_MANAGER", "WAITER", "COUNTER"]:
            if "branch" in data and int(data["branch"]) != my_branch.id:
                return Response(
                    {"success": False, "message": "Cannot change customer branch"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Update customer
        serializer = CustomerSerializer(customer, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Customer updated successfully",
                    "data": serializer.data,
                }
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- DELETE ---
    @transaction.atomic
    def delete(self, request, id):
        if not id:
            return Response(
                {"success": False, "message": "Customer ID required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        role = self.get_user_role(request.user)
        my_branch = getattr(request.user, "branch", None)

        # Get customer
        try:
            customer = Customer.objects.get(id=id)
        except Customer.DoesNotExist:
            return Response(
                {"success": False, "message": "Customer not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check permissions
        if role in ["SUPER_ADMIN", "ADMIN"]:
            # Can delete any customer
            pass
        elif role in ["BRANCH_MANAGER"]:
            # Branch Manager can delete customers in their branch
            if not my_branch or customer.branch != my_branch:
                return Response(
                    {
                        "success": False,
                        "message": "Cannot delete customer from another branch",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            # WAITER, COUNTER, KITCHEN cannot delete
            return Response(
                {"success": False, "message": "Insufficient permissions to delete"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Delete customer
        customer_name = customer.name
        customer.delete()

        return Response(
            {
                "success": True,
                "message": f"Customer '{customer_name}' deleted successfully",
            }
        )
