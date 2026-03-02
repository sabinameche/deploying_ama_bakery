from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Invoice, Payment
from ..serializer_dir.payment_serializer import PaymentSerializer


class PaymentClassView(APIView):
    """
    CRUD for Payments with branch permission checks.
    transaction_id is a UUID generated automatically by the model.
    """

    # ------------------ GET (List/Retrieve) ------------------
    def get(self, request, invoice_id=None, payment_id=None):
        role = getattr(request.user, "user_type", None)
        my_branch = getattr(request.user, "branch", None)

        if payment_id:
            try:
                payment = Payment.objects.select_related(
                    "invoice__branch", "received_by", "invoice"
                ).get(id=payment_id)
            except Payment.DoesNotExist:
                return Response(
                    {"success": False, "error": "Payment not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                role not in ["ADMIN", "SUPER_ADMIN"]
                and my_branch
                and payment.invoice.branch != my_branch
            ):
                return Response(
                    {"success": False, "error": "Payment not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = PaymentSerializer(payment)
            return Response({"success": True, "data": serializer.data})

        elif invoice_id:
            try:
                invoice = Invoice.objects.select_related("branch").get(id=invoice_id)
            except Invoice.DoesNotExist:
                return Response(
                    {"success": False, "error": "Invoice not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                role not in ["ADMIN", "SUPER_ADMIN"]
                and my_branch
                and invoice.branch != my_branch
            ):
                return Response(
                    {"success": False, "error": "Invoice not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            payments = Payment.objects.filter(invoice=invoice).order_by("-created_at")
            serializer = PaymentSerializer(payments, many=True)

            return Response(
                {
                    "success": True,
                    "data": serializer.data,
                    "invoice_total": float(invoice.total_amount),
                    "paid_total": float(invoice.paid_amount),
                    "due_amount": float(invoice.due_amount),
                }
            )

        else:
            filters = {}
            if role not in ["ADMIN", "SUPER_ADMIN"] and my_branch:
                filters["invoice__branch"] = my_branch

            start_date = request.query_params.get("start_date")
            end_date = request.query_params.get("end_date")
            payment_method = request.query_params.get("payment_method")

            if start_date:
                filters["created_at__date__gte"] = start_date
            if end_date:
                filters["created_at__date__lte"] = end_date
            if payment_method:
                filters["payment_method"] = payment_method

            payments = (
                Payment.objects.filter(**filters)
                .select_related("invoice", "received_by", "invoice__branch")
                .order_by("-created_at")
            )

            serializer = PaymentSerializer(payments, many=True)
            return Response({"success": True, "data": serializer.data})

    # ------------------ POST (Create Payment) ------------------
    @transaction.atomic
    def post(self, request, invoice_id):
        try:
            invoice = Invoice.objects.select_related("branch").get(id=invoice_id)
        except Invoice.DoesNotExist:
            return Response(
                {"success": False, "error": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        role = getattr(request.user, "user_type", None)
        my_branch = getattr(request.user, "branch", None)

        allowed_roles = ["ADMIN", "SUPER_ADMIN", "COUNTER", "BRANCH_MANAGER", "WAITER"]
        if role not in allowed_roles:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if (
            role not in ["ADMIN", "SUPER_ADMIN"]
            and my_branch
            and invoice.branch != my_branch
        ):
            return Response(
                {"success": False, "error": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # amount validation
        try:
            amount = Decimal(str(request.data.get("amount", 0)))
        except Exception:
            return Response(
                {"success": False, "error": "Invalid amount format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine if this is a zero-amount handover confirmation
        is_handover_confirmation = (
            amount == 0 
            and invoice.payment_status == "PARTIAL" 
            and invoice.received_by_waiter 
            and not invoice.received_by_counter
        )

        if amount <= 0 and not is_handover_confirmation:
            return Response(
                {"success": False, "error": "Payment amount must be greater than 0"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        due_amount = invoice.total_amount - invoice.paid_amount
        if not is_handover_confirmation and amount > due_amount:
            return Response(
                {
                    "success": False,
                    "error": f"Cannot pay more than due amount. Max allowed: {float(due_amount)}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_method = (request.data.get("payment_method") or "CASH").strip().upper()

        # Create payment (transaction_id auto-generated as full UUID)
        payment = Payment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_method=payment_method,
            notes=(request.data.get("notes") or "").strip() or None,
            received_by=request.user,
        )

        # Update invoice totals/status and log receiving staff
        invoice.paid_amount += amount
        
        if role == "WAITER":
            invoice.received_by_waiter = request.user
            invoice.payment_status = "PARTIAL"
        elif role in ["COUNTER", "BRANCH_MANAGER", "ADMIN", "SUPER_ADMIN"]:
            invoice.received_by_counter = request.user

        if invoice.paid_amount >= invoice.total_amount and role in ["COUNTER","BRANCH_MANAGER","ADMIN","SUPER_ADMIN"]:
            print("i am inside first condition ")
            invoice.payment_status = "PAID"
        elif invoice.paid_amount > 0:
            invoice.payment_status = "PARTIAL"
        invoice.save()

        return Response(
            {
                "success": True,
                "message": "Payment added successfully",
                "payment_id": payment.id,
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "amount_paid": float(amount),
                "total_paid": float(invoice.paid_amount),
                "due_amount": float(invoice.due_amount),
                "payment_status": invoice.payment_status,
                "transaction_id": str(
                    payment.transaction_id
                ),  # UUID -> string for JSON
                "payment_method": payment.payment_method,
            },
            status=status.HTTP_201_CREATED,
        )

    # ------------------ PATCH (Update Payment) ------------------
    @transaction.atomic
    def patch(self, request, payment_id):
        role = getattr(request.user, "user_type", None)

        if role not in ["ADMIN", "SUPER_ADMIN"]:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            payment = Payment.objects.select_related("invoice").get(id=payment_id)
        except Payment.DoesNotExist:
            return Response(
                {"success": False, "error": "Payment not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.invoice.payment_status in ["PAID", "CANCELLED"]:
            return Response(
                {
                    "success": False,
                    "error": "Cannot modify payment for a paid or cancelled invoice",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Do NOT allow transaction_id edits (UUID should be immutable)
        allowed_fields = ["notes", "payment_method"]
        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        serializer = PaymentSerializer(payment, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Payment updated successfully",
                    "data": serializer.data,
                }
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ------------------ DELETE (Refund/Delete Payment) ------------------
    @transaction.atomic
    def delete(self, request, payment_id):
        role = getattr(request.user, "user_type", None)

        if role not in ["ADMIN", "SUPER_ADMIN"]:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            payment = Payment.objects.select_related("invoice").get(id=payment_id)
        except Payment.DoesNotExist:
            return Response(
                {"success": False, "error": "Payment not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        invoice = payment.invoice
        refund_amount = payment.amount

        invoice.paid_amount -= refund_amount
        if invoice.paid_amount <= 0:
            invoice.paid_amount = Decimal("0")
            invoice.payment_status = "UNPAID"
        elif invoice.paid_amount < invoice.total_amount:
            invoice.payment_status = "PARTIAL"
        invoice.save()

        payment.delete()

        return Response(
            {
                "success": True,
                "message": "Payment refunded and deleted successfully",
                "invoice_id": invoice.id,
                "remaining_due": float(invoice.due_amount),
                "payment_status": invoice.payment_status,
            },
            status=status.HTTP_200_OK,
        )

