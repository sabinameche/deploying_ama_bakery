from rest_framework import serializers

from ..models import ItemActivity


class ItemActivitySerializer(serializers.ModelSerializer):
    product_detail = serializers.CharField(
        source="product.name", read_only=True, required=False
    )

    class Meta:
        model = ItemActivity
        fields = [
            "id",
            "product",  # Add this field
            "product_detail",  # For display
            "types",
            "change",
            "quantity",
            "created_at",
            "remarks",
        ]
        extra_kwargs = {
            "product": {"required": True},  # Make product required
            "types": {"required": False},
            "change": {"required": False},
            "quantity": {"required": False},
            "remarks": {"required": False},
        }
