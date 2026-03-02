from rest_framework import serializers
from ..models import Customer, Invoice


class CustomerInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ["id", "total_amount", "payment_status", "created_by"]


class CustomerSerializer(serializers.ModelSerializer):
    invoice = CustomerInvoiceSerializer(source="invoices", many=True, read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "address",
            "created_at",
            "branch",
            "invoice",
        ]
        extra_kwargs = {
            "name": {"required": True},
            "phone": {"required": True},
            "branch": {"required": True},
        }

    def validate(self, data):
        instance = self.instance
        phone = data.get('phone', getattr(instance, 'phone', None))
        branch = data.get('branch', getattr(instance, 'branch', None))
        
        if not phone or not branch:
            return data
            
        queryset = Customer.objects.filter(phone=phone, branch=branch)
        
        if instance:
            queryset = queryset.exclude(id=instance.id)
            
        if queryset.exists():
            raise serializers.ValidationError(
                f"A customer with phone '{phone}' already exists in this branch."
            )
            
        return data
