from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Invoice, User


class StaffReportViewClass(APIView):
    """
    Returns staff performance data for a branch.

    Endpoints:
      GET /api/calculate/staff-report/<branch_id>/   → ADMIN / SUPER_ADMIN
      GET /api/calculate/staff-report/               → BRANCH_MANAGER (uses own branch)

    Response fields per staff member:
      - id            : user id
      - name          : full_name (falls back to username)
      - role          : user_type (WAITER / COUNTER / etc.)
      - total_orders  : number of invoices served / created by this staff
      - total_sales   : sum of total_amount on those invoices
      - current_month_orders : orders in current calendar month
      - current_month_sales  : sales in current calendar month
    """

    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    def get(self, request, branch_id=None):
        role = self.get_user_role(request.user)
        my_branch = getattr(request.user, "branch", None)

        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {"success": False, "message": "Insufficient permissions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if role in ["SUPER_ADMIN", "ADMIN"]:
            if not branch_id:
                return Response(
                    {
                        "success": False,
                        "message": "branch_id is required for admin/superadmin",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            my_branch = branch_id

        if not my_branch:
            return Response(
                {"success": False, "message": "No branch associated with this user"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_month = timezone.localdate().month
        current_year = timezone.localdate().year

        # Fetch staff belonging to this branch (exclude super_admin, pure admins)
        staff_qs = User.objects.filter(
            branch=my_branch,
            is_active=True,
        ).exclude(is_superuser=True)

        staff_data = []

        for staff in staff_qs:
            # Invoices where this staff member was the waiter OR counter OR creator
            invoices_all = (
                Invoice.objects.filter(branch=my_branch)
                .filter(
                    Q(received_by_waiter=staff)
                    | Q(received_by_counter=staff)
                    | Q(created_by=staff)
                )
                .distinct()
            )

            total_orders = invoices_all.count()
            total_sales = (
                invoices_all.aggregate(total=Sum("total_amount"))["total"] or 0
            )

            # Current month breakdown
            invoices_month = invoices_all.filter(
                created_at__year=current_year,
                created_at__month=current_month,
            )
            current_month_orders = invoices_month.count()
            current_month_sales = (
                invoices_month.aggregate(total=Sum("total_amount"))["total"] or 0
            )

            staff_data.append(
                {
                    "id": staff.id,
                    "name": staff.full_name or staff.username,
                    "username": staff.username,
                    "role": staff.user_type,
                    "total_orders": total_orders,
                    "total_sales": float(total_sales),
                    "current_month_orders": current_month_orders,
                    "current_month_sales": float(current_month_sales),
                }
            )

        # Sort by total_orders descending
        staff_data.sort(key=lambda x: x["total_orders"], reverse=True)

        return Response(
            {
                "success": True,
                "staff_performance": staff_data,
            },
            status=status.HTTP_200_OK,
        )
