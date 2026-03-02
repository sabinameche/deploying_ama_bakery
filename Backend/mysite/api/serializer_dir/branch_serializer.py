from rest_framework import serializers

from ..models import Branch


class BranchSerializers(serializers.ModelSerializer):
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Branch
        fields = ["id", "name", "location", "revenue"]
