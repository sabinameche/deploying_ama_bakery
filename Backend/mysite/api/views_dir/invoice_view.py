from datetime import date

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Invoice
from ..serializer_dir.invoice_serializer import (
    InvoiceResponseSerializer,
    InvoiceSerializer,
)


class InvoiceViewClass(APIView):
    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    def get_branch_filter(self, user, role):
        if role in ["ADMIN", "SUPER_ADMIN"]:
            return {}
        elif user.branch:
            return {"branch": user.branch}
        return {"branch__isnull": True}

    def get(self, request, id=None):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch
        today_date = date.today()
        from django.utils import timezone

        current_time = timezone.now()
        print(f"DEBUG: Current Time: {current_time}, Today Date Filter: {today_date}")

        if id:
            try:
                # Apply branch filter for non-admin users
                if role not in ["ADMIN", "SUPER_ADMIN"] and my_branch:
                    invoice = Invoice.objects.get(
                        branch=my_branch, created_at__date=today_date, id=id
                    )
                    serializer = InvoiceResponseSerializer(invoice)
                    return Response({"success": True, "data": serializer.data})
                else:
                    invoice = Invoice.objects.get(id=id)
                    serializer = InvoiceResponseSerializer(invoice)
                    return Response({"success": True, "data": serializer.data})

            except Invoice.DoesNotExist:
                return Response(
                    {"success": False, "error": "Invoice not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            # Base filtering
            if role in ["COUNTER", "WAITER", "KITCHEN"]:
                invoices = Invoice.objects.filter(
                    branch=my_branch, created_at__date=today_date
                ).exclude(payment_status__in=["PAID", "CANCELLED"])
            elif role == "BRANCH_MANAGER":
                invoices = Invoice.objects.filter(branch=my_branch)
            else:
                invoices = Invoice.objects.all()

            # Filter by customer if provided
            customer_id = request.query_params.get("customer")
            if customer_id:
                invoices = invoices.filter(customer_id=customer_id)

            invoices = invoices.order_by("-created_at")
            serializer = InvoiceResponseSerializer(invoices, many=True)
            return Response({"success": True, "count": invoices.count(), "data": serializer.data})

    # ------------------ POST (Create) ------------------
    @transaction.atomic
    def post(self, request):
        """Create new invoice"""
        role = self.get_user_role(request.user)
        my_branch = getattr(request.user, "branch", None)

        # Check permissions
        if role not in ["ADMIN", "SUPER_ADMIN", "COUNTER", "WAITER", "BRANCH_MANAGER"]:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,  #  Use status constants
            )

        # Resolve branch for invoice creation:
        # - branch-bound roles use their assigned branch
        # - ADMIN/SUPER_ADMIN may pass `branch` in the request body (frontend already does)
        branch_id = my_branch.id if my_branch else request.data.get("branch")
        if not branch_id:
            return Response(
                {
                    "success": False,
                    "message": "Branch is required to create an invoice.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent non-global roles from creating invoices for another branch
        if (
            my_branch
            and str(branch_id) != str(my_branch.id)
            and role not in ["ADMIN", "SUPER_ADMIN"]
        ):
            return Response(
                {
                    "success": False,
                    "message": "You can only create invoices in your own branch.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InvoiceSerializer(
            data=request.data, context={"request": request, "branch": branch_id}
        )

        if serializer.is_valid():
            print("yy")
            try:
                invoice = serializer.save()
                response_serializer = InvoiceResponseSerializer(invoice)
                return Response(
                    {"success": True, "data": response_serializer.data},
                    status=status.HTTP_201_CREATED,  # ✅ Use status constants
                )
            except Exception as e:
                print("except:::::")
                return Response(
                    {"success": False, "error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,  # ✅ Use status constants
                )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,  # ✅ Use status constants
        )

    # ------------------ PATCH (Update) ------------------
    @transaction.atomic
    def patch(self, request, id):
        """Update invoice partially"""
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        try:
            # Apply branch filter for non-admin users
            filter_kwargs = {"id": id}
            if role not in ["ADMIN", "SUPER_ADMIN"] and my_branch:
                filter_kwargs["branch"] = my_branch.id
            invoice = Invoice.objects.get(**filter_kwargs)
        except Invoice.DoesNotExist:
            return Response(
                {"success": False, "error": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND,  # ✅ Use status constants
            )

        # Don't allow modifying paid/cancelled invoices

        print("i", invoice.payment_status)
        if invoice.payment_status in ["PAID", "CANCELLED"]:
            print("i am inside patch method!")
            return Response(
                {
                    "success": False,
                    "error": f"Cannot modify {invoice.payment_status.lower()} invoice",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only allow updating safe fields
        allowed_fields = ["notes", "description", "is_active", "invoice_status"]
        if role in ["ADMIN", "SUPER_ADMIN"]:
            allowed_fields.extend(["tax_amount", "discount"])

        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        serializer = InvoiceResponseSerializer(invoice, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()

            # Broadcast status update to all connected clients (kitchen, waiter, counter)
            new_status = data.get("invoice_status")
            if new_status:
                try:
                    channel_layer = get_channel_layer()
                    if channel_layer is not None:
                        message = {
                            "type": "invoice_updated",
                            "invoice_id": str(id),
                            "status": new_status,
                        }
                        # Notify kitchen screens
                        async_to_sync(channel_layer.group_send)(
                            "kitchen_orders", message
                        )
                        # Notify waiter/counter screens
                        async_to_sync(channel_layer.group_send)("orders", message)
                except Exception:
                    pass

            return Response({"success": True, "data": serializer.data})

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,  # ✅ Use status constants
        )

    # ------------------ DELETE ------------------
    def delete(self, request, id):
        """Delete invoice"""
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        if role not in ["ADMIN", "SUPER_ADMIN"]:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,  # ✅ Use status constants
            )

        try:
            # Apply branch filter for non-admin users
            filter_kwargs = {"id": id}
            if role not in ["ADMIN", "SUPER_ADMIN"] and my_branch:
                filter_kwargs["branch"] = my_branch

            invoice = Invoice.objects.get(**filter_kwargs)

            # Don't delete paid invoices
            if invoice.payment_status == "PAID":
                return Response(
                    {"success": False, "error": "Cannot delete paid invoice"},
                    status=status.HTTP_400_BAD_REQUEST,  # ✅ Use status constants
                )

            invoice.delete()
            return Response(
                {"success": True, "message": "Invoice deleted"},
                status=status.HTTP_204_NO_CONTENT,  # ✅ Use status constants
            )

        except Invoice.DoesNotExist:
            return Response(
                {"success": False, "error": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND,  # ✅ Use status constants
            )
