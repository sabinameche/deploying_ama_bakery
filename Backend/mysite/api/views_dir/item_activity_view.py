from decimal import Decimal

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from django.shortcuts import get_object_or_404
from ..models import ItemActivity, Product
from ..serializer_dir.item_activity_serializer import ItemActivitySerializer
from django.db import transaction

class ItemActivityClassView(APIView):
    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    def get(self, request, activity_id=None, product_id=None, action=None):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        if activity_id:
            item_activity = get_object_or_404(ItemActivity,id=activity_id)
            serializer = ItemActivitySerializer(item_activity)
        else:
            if product_id:
                if action == "detail":
                    item_activity = ItemActivity.objects.filter(product=product_id).order_by('-created_at')
                    serializer = ItemActivitySerializer(item_activity, many=True)
            else:
                item_activity = ItemActivity.objects.all()
                serializer = ItemActivitySerializer(item_activity, many=True)
        return Response({"success": True, "data": serializer.data})

    def post(self, request, action=None, product_id=None):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        if action:
            if action not in ["add", "reduce"]:
                return Response(
                    {"success": False, "message": "Invalid action"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if product_id:
                product = get_object_or_404(Product, id=product_id, is_deleted=False)
                data = request.data.copy()
                data["product"] = product_id

                #  Validate change
                try:
                    change = Decimal(data.get("change"))
                except (TypeError, ValueError):
                    return Response(
                        {"success": False, "message": "Invalid change value"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                original_qty = product.product_quantity

                if action == "add":
                    data["quantity"] = original_qty + change
                    data["types"] = "ADD_STOCK"

                elif action == "reduce":
                    data["quantity"] = original_qty - change
                    data["types"] = "REDUCE_STOCK"

                serializer = ItemActivitySerializer(data=data)

                if serializer.is_valid():
                    try:
                        with transaction.atomic():
                            product.product_quantity = Decimal(
                                serializer.validated_data["quantity"]
                            )
                            product.save()
                            serializer.save()

                        return Response(
                            {
                                "success": True,
                                "message": "Modified product successfully",
                                "data": serializer.data,
                            },
                            status=status.HTTP_200_OK,
                        )

                    except Exception as e:
                        return Response(
                            {
                                "success": False,
                                "message": "Something went wrong",
                                "error": str(e),  # remove in production
                            },
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )

                return Response(
                    {
                        "success": False,
                        "message": "Validation error",
                        "errors": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(
            {"success": False, "message": "Invalid request"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def patch(self, request, activity_id):
        role = self.get_user_role(request.user)
        my_branch = request.user.branch

        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {"success": False, "message": "Insufficient permissions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        item_activity = get_object_or_404(ItemActivity, id=activity_id)
        data = request.data.copy()

        # Validate change before transaction
        try:
            new_change = Decimal(data.get("change"))
        except (TypeError, ValueError):
            return Response(
                {"success": False, "message": "Invalid change value"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():

                # Reverse old effect and apply new change
                if item_activity.types == "ADD_STOCK":
                    tempqty = item_activity.quantity - Decimal(item_activity.change)
                    item_activity.quantity = tempqty + new_change

                elif item_activity.types == "REDUCE_STOCK":
                    tempqty = item_activity.quantity + Decimal(item_activity.change)
                    item_activity.quantity = tempqty - new_change

                item_activity.change = new_change
                item_activity.save()

                prev = item_activity.quantity

                #  Update subsequent activities safely
                subsequent_activities = ItemActivity.objects.filter(
                    product=item_activity.product,
                    created_at__gt=item_activity.created_at,
                ).order_by("created_at")

                for act in subsequent_activities:
                    if act.types == "ADD_STOCK":
                        act.quantity = prev + Decimal(act.change)
                    elif act.types == "REDUCE_STOCK":
                        act.quantity = prev - Decimal(act.change)

                    prev = act.quantity
                    act.save()

                #  Safe handling of last()
                last_activity = subsequent_activities.last()

                if last_activity:
                    item_activity.product.product_quantity = last_activity.quantity
                else:
                    item_activity.product.product_quantity = item_activity.quantity

                item_activity.product.save()

        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": "Something went wrong",
                    "error": str(e),  # remove in production
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        serializer = ItemActivitySerializer(item_activity)
        return Response(
            {"success": True, "data": serializer.data},
            status=status.HTTP_200_OK,
        )