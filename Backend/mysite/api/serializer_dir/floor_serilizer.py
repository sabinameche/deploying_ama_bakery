from rest_framework import serializers

from ..models import Floor


class FloorSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Floor
        fields = ["id", "branch", "name", "branch_name", "table_count"]
