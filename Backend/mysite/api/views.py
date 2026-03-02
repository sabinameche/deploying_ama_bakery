from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes  # ADD THIS IMPORT
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import AllowAny
from django.utils import timezone

from .serializer_dir.users_serializer import (
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
)
from .views_dir import floor_view, item_activity_view, auth_view
from .views_dir.auth_view import CookieTokenObtainPairView, CookieTokenRefreshView, LogoutView

from .views_dir.branch_view import BranchViewClass
from .views_dir.categorys_view import CategoryViewClass
from .views_dir.customer_view import CustomerViewClass
from .views_dir.invoice_view import InvoiceViewClass
from .views_dir.dashboard_view import DashboardViewClass, ReportDashboardViewClass
from .views_dir.staff_view import StaffReportViewClass
from .views_dir.payment_view import PaymentClassView

# custom
from .views_dir.product_view import ProductViewClass
from .views_dir.users_view import UserViewClass


@api_view(['GET','HEAD'])
@permission_classes([AllowAny])  # Allow anyone to test
def test_rate_limit(request):
    return Response({
        'message': 'Rate limit test',
        'timestamp': timezone.now().isoformat(),
        'user': str(request.user),
        'authenticated': request.user.is_authenticated
    })




@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def change_own_password(request):
    """User can change their own password"""
    serializer = ChangePasswordSerializer(
        data=request.data, context={"request": request}
    )

    if serializer.is_valid():
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"success": True, "message": "Password updated successfully"})

    return Response(
        {"success": False, "errors": serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def admin_reset_password(request, user_id):
    """
    Allow admins and branch managers to reset passwords of users below them.
    - ADMIN can reset anyone (except maybe other admins, but let's keep it simple).
    - BRANCH_MANAGER can reset WAITER, COUNTER, KITCHEN in their own branch.
    """
    from .models import User

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {"success": False, "message": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    requester = request.user
    new_password = request.data.get("new_password")

    if not new_password:
        return Response(
            {"success": False, "message": "New password is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Permission Logic
    can_reset = False

    if requester.user_type == "ADMIN":
        # Admin can reset anyone below them (Branch Manager and Employees)
        if target_user.user_type != "ADMIN" or requester.is_superuser:
            can_reset = True
    elif requester.user_type == "BRANCH_MANAGER":
        # Branch Manager can only reset staff in their own branch
        is_same_branch = target_user.branch_id == requester.branch_id
        is_staff = target_user.user_type in ["WAITER", "COUNTER", "KITCHEN"]
        if is_same_branch and is_staff:
            can_reset = True

    if not can_reset:
        return Response(
            {"success": False, "message": "You do not have permission to reset this user's password"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Perform reset
    target_user.set_password(new_password)
    target_user.save()

    return Response({
        "success": True, 
        "message": f"Password for {target_user.username} has been reset successfully"
    })



class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


UserView = UserViewClass
ProductView = ProductViewClass
CategoryView = CategoryViewClass
BranchView = BranchViewClass
CustomerView = CustomerViewClass
InvoiceView = InvoiceViewClass
PaymentView = PaymentClassView
FloorView = floor_view.FloorViewClass
ItemActivityView = item_activity_view.ItemActivityClassView
DashboardView = DashboardViewClass
ReportDashboardView = ReportDashboardViewClass
StaffReportView = StaffReportViewClass

