from rest_framework import serializers

from ..models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    # Display related fields in response
    invoice_number = serializers.CharField(
        source="invoice.invoice_number", read_only=True
    )
    received_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "amount",
            "payment_method",
            "transaction_id",
            "notes",
            "payment_date",
            "received_by",
            "received_by_name",
        ]
        read_only_fields = ["id", "invoice", "payment_date", "received_by"]

    def get_received_by_name(self, obj):
        """Return full name of the user who received the payment"""
        if obj.received_by:
            return obj.received_by.get_full_name() or obj.received_by.username
        return None
