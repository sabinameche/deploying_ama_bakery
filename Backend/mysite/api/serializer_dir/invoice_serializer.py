from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from ..models import Invoice, InvoiceItem  # adjust import path if needed
from .item_activity_serializer import ItemActivitySerializer


class InvoiceItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = InvoiceItem
        fields = [
            "product",
            "product_name",
            "quantity",
            "unit_price",
            "discount_amount",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Used for POST / PATCH / PUT
    - Does NOT accept created_at
    - Handles item creation and totals calculation
    """

    items = InvoiceItemSerializer(many=True)
    paid_amount = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
        min_value=0,
    )
    payment_method = serializers.CharField(
        write_only=True,
        required=False,
        default="CASH",
        allow_blank=True,
        allow_null=True,
    )

    # REMOVED the problematic print statement from here!

    class Meta:
        model = Invoice
        fields = [
            "branch",
            "customer",
            "invoice_type",
            "tax_amount",
            "discount",
            "description",
            "paid_amount",
            "payment_method",
            "items",
            "invoice_status",
            "floor",
            # Intentionally NO created_at, created_by, subtotal, total_amount, etc.
        ]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        paid_amount = validated_data.pop("paid_amount", Decimal("0.00"))
        payment_method = validated_data.pop("payment_method", "CASH")
        request = self.context.get("request")
        notes = validated_data.get("notes", "")

        user = request.user if request else None

        # Create invoice skeleton
        invoice = Invoice.objects.create(
            **validated_data,
            created_by=user,
            subtotal=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            paid_amount=paid_amount,
            payment_status="PENDING",
        )

        # Log who received the initial payment
        role = getattr(user, "user_type", None)
        if paid_amount > 0 and user:
            from ..models import Payment

            Payment.objects.create(
                invoice=invoice,
                amount=paid_amount,
                payment_method=payment_method,
                received_by=user,
                notes="Initial payment during invoice creation",
            )
            if role == "WAITER":
                invoice.payment_status = "PARTIAL"
                invoice.received_by_waiter = user
            elif role in ["COUNTER", "BRANCH_MANAGER", "ADMIN", "SUPER_ADMIN"]:
                invoice.received_by_counter = user

        # Generate invoice number
        branch_id = self.context.get("branch")
        try:
            branch_id_int = int(branch_id)
        except (TypeError, ValueError):
            branch_id_int = None

        if not branch_id_int:
            raise serializers.ValidationError(
                {"branch": "Invalid branch for invoice creation."}
            )

        today_date = timezone.localdate().strftime("%Y-%m-%d")
        prefix = f"{branch_id_int:02d}-{today_date}"

        # Find the latest invoice number for this branch for today
        latest_today = (
            Invoice.objects.filter(
                branch=branch_id_int, invoice_number__startswith=prefix
            )
            .exclude(id=invoice.id)
            .order_by("-invoice_number")
            .first()
        )

        if latest_today and latest_today.invoice_number:
            try:
                seq = int(latest_today.invoice_number.split("-")[-1]) + 1
            except Exception:
                seq = 1
        else:
            seq = 1

        final_invoice_no = f"{prefix}-{seq:02d}"

        invoice.invoice_number = final_invoice_no

        # Create items & calculate subtotal
        subtotal = Decimal("0.00")
        for item_data in items_data:
            item = InvoiceItem.objects.create(invoice=invoice, **item_data)

            item.product.product_quantity -= item.quantity
            item.product.save()
            line_total = item.quantity * item.unit_price - item.discount_amount
            subtotal += line_total

            itemactivity = {
                "change": str(item.quantity),
                "quantity": item.product.product_quantity,
                "product": item.product_id,
                "types": "SALES",
                "remarks": notes,
            }

            itemserializer = ItemActivitySerializer(data=itemactivity)
            itemserializer.is_valid(raise_exception=True)
            itemserializer.save()

        # Final totals
        invoice.subtotal = subtotal
        invoice.total_amount = (
            subtotal
            + (invoice.tax_amount or Decimal("0.00"))
            - (invoice.discount or Decimal("0.00"))
        )

        # Payment status logic for PAY LATER
        if invoice.paid_amount >= invoice.total_amount and role in [
            "COUNTER",
            "ADMIN",
            "BRANCH_MANAGER",
            "SUPER_ADMIN",
        ]:
            invoice.payment_status = "PAID"
        elif invoice.paid_amount > 0:
            invoice.payment_status = "PARTIAL"
        else:
            # This handles PAY LATER case (paid_amount = 0)
            invoice.payment_status = "PENDING"

        invoice.save()

        # Notify all screens via WebSocket (kitchen, waiter, counter)
        try:
            channel_layer = get_channel_layer()
            if channel_layer is not None:
                message = {
                    "type": "invoice_created",
                    "invoice_id": str(invoice.id),
                }
                # Notify kitchen screens
                async_to_sync(channel_layer.group_send)("kitchen_orders", message)
                # Notify waiter/counter screens
                async_to_sync(channel_layer.group_send)("orders", message)
        except Exception:
            pass

        return invoice

    def update(self, instance, validated_data):
        # For simplicity — you can expand this if partial updates of items are needed
        items_data = validated_data.pop("items", None)
        paid_amount = validated_data.pop("paid_amount", None)
        request = self.context.get("request")
        user = request.user if request else None
        role = getattr(user, "user_type", None)

        # Update scalar fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if paid_amount is not None:
            instance.paid_amount = paid_amount

        if items_data is not None:
            # Simple approach: delete old items, create new ones
            instance.bills.all().delete()  # assuming related_name="bills"
            subtotal = Decimal("0.00")
            for item_data in items_data:
                item = InvoiceItem.objects.create(invoice=instance, **item_data)
                subtotal += item.quantity * item.unit_price - item.discount_amount
            instance.subtotal = subtotal
            instance.total_amount = (
                subtotal + (instance.tax_amount or 0) - (instance.discount or 0)
            )

        # Re-evaluate payment status
        if instance.paid_amount >= instance.total_amount and role in [
            "COUNTER",
            "ADMIN",
            "BRANCH_MANAGER",
            "SUPER_ADMIN",
        ]:
            instance.payment_status = "PAID"
        elif instance.paid_amount > 0:
            instance.payment_status = "PARTIAL"
        else:
            instance.payment_status = "PENDING"

        instance.save()
        return instance


class InvoiceResponseSerializer(serializers.ModelSerializer):
    """
    Used for GET / list / retrieve
    - Includes read-only fields, names, due_amount, formatted created_at
    - Uses related_name 'bills' for items (adjust if your related_name is different)
    """

    items = InvoiceItemSerializer(many=True, source="bills")
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    floor_name = serializers.CharField(source="floor.name", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True
    )
    received_by_waiter_name = serializers.CharField(
        source="received_by_waiter.username", read_only=True
    )
    received_by_counter_name = serializers.CharField(
        source="received_by_counter.username", read_only=True
    )
    due_amount = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "invoice_type",
            "customer",
            "customer_name",
            "floor",
            "floor_name",
            "branch",
            "branch_name",
            "created_by",
            "created_at",
            "created_by_name",
            "received_by_waiter",
            "received_by_waiter_name",
            "received_by_counter",
            "received_by_counter_name",
            "notes",
            "subtotal",
            "tax_amount",
            "discount",
            "total_amount",
            "paid_amount",
            "due_amount",
            "payment_status",
            "is_active",
            "description",
            "invoice_status",
            "items",
            "payment_methods",
        ]

    def get_due_amount(self, obj):
        return obj.total_amount - obj.paid_amount

    def get_payment_methods(self, obj):
        print(list(obj.payments.values_list("payment_method", flat=True).distinct()))
        return list(obj.payments.values_list("payment_method", flat=True).distinct())
