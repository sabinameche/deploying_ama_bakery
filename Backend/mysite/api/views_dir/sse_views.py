import json
import logging
import asyncio
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from json import JSONEncoder

from asgiref.sync import sync_to_async

from django.db.models import Count, F, Sum
from django.db.models.functions import (
    ExtractHour,
    ExtractWeek,
    ExtractWeekDay,
    ExtractYear,
    TruncHour,
)
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated

from ..models import Branch, Invoice, InvoiceItem, Payment, User
from ..serializer_dir.invoice_serializer import InvoiceResponseSerializer

logger = logging.getLogger(__name__)

# Store active connections for broadcasting
active_connections = set()


# Custom JSON encoder to handle Decimal and datetime objects
class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


@require_GET
@csrf_exempt
async def dashboard_sse(request):
    """
    Server-Sent Events endpoint for real-time dashboard updates (Async version)
    """
    # Manual authentication check for function view with EventSource
    user = request.user
    
    # If not authenticated via session/cookies, check for token in query param
    # Use sync_to_async for DB-related checks on user
    is_auth = await sync_to_async(lambda: user.is_authenticated)()
    if not is_auth:
        token = request.GET.get("token")
        if token:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            try:
                auth = JWTAuthentication()
                validated_token = await sync_to_async(auth.get_validated_token)(token)
                user = await sync_to_async(auth.get_user)(validated_token)
            except Exception:
                pass

    is_auth = await sync_to_async(lambda: user.is_authenticated)()
    if not is_auth:
        return StreamingHttpResponse(
            'event: error\ndata: {"message": "Unauthorized"}\n\n',
            content_type="text/event-stream",
            status=401,
        )

    branch_id = request.GET.get("branch_id")
    # Check permissions - also needs sync_to_async for potential DB field access (superuser)
    is_super = await sync_to_async(lambda: user.is_superuser)()
    role = "SUPER_ADMIN" if is_super else getattr(user, "user_type", "")

    if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
        return StreamingHttpResponse(
            'event: error\ndata: {"message": "Unauthorized"}\n\n',
            content_type="text/event-stream",
            status=403,
        )

    async def event_stream():
        # Generate unique connection ID
        connection_id = f"{user.id}_{timezone.now().timestamp()}"
        active_connections.add(connection_id)

        logger.info(
            f"SSE connection opened for user {user.username} (branch: {branch_id})"
        )

        try:
            # Send initial connection message
            yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'user': user.username, 'branch_id': branch_id}, cls=CustomJSONEncoder)}\n\n"

            # Send initial dashboard data
            initial_data = await sync_to_async(get_dashboard_data_sync)(user, branch_id, role)
            if initial_data:
                yield f"event: dashboard_update\ndata: {json.dumps(initial_data, cls=CustomJSONEncoder)}\n\n"
            else:
                yield f"event: error\ndata: {json.dumps({'message': 'Failed to load initial data'}, cls=CustomJSONEncoder)}\n\n"

            last_check = timezone.now()
            heartbeat_count = 0

            while True:
                # Check for database changes every 2 seconds
                changed = await sync_to_async(has_dashboard_data_changed_sync)(user, branch_id, last_check)
                if changed:
                    logger.debug(
                        f"Data changed for user {user.username}, sending update"
                    )
                    new_data = await sync_to_async(get_dashboard_data_sync)(user, branch_id, role)
                    if new_data:
                        yield f"event: dashboard_update\ndata: {json.dumps(new_data, cls=CustomJSONEncoder)}\n\n"
                    last_check = timezone.now()

                # Send heartbeat every 15 seconds to keep connection alive
                heartbeat_count += 1
                if heartbeat_count >= 7:  # ~14 seconds with 2s sleep
                    yield ": heartbeat\n\n"
                    heartbeat_count = 0

                await asyncio.sleep(2)

        except (asyncio.CancelledError, GeneratorExit):
            # Clean up on disconnect
            active_connections.discard(connection_id)
            logger.info(f"SSE connection closed for user {user.username}")
        except Exception as e:
            logger.error(f"SSE error for user {user.username}: {e}")
            active_connections.discard(connection_id)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # Disable nginx buffering
    response["Access-Control-Allow-Origin"] = "*"  # Add if needed for CORS
    return response


def has_dashboard_data_changed_sync(user, branch_id, since):
    """
    Quick check if any relevant data has changed
    """
    try:
        # Check for new invoices since last check
        if branch_id and branch_id != "null" and branch_id != "undefined":
            # Branch-specific check
            new_invoices = Invoice.objects.filter(
                branch_id=branch_id, created_at__gt=since
            ).exists()

            # Check for new payments
            new_payments = Payment.objects.filter(
                invoice__branch_id=branch_id, created_at__gt=since
            ).exists()

            # Check for new invoice items
            new_items = InvoiceItem.objects.filter(
                invoice__branch_id=branch_id, invoice__created_at__gt=since
            ).exists()

        else:
            # For superadmin - check all branches
            new_invoices = Invoice.objects.filter(created_at__gt=since).exists()

            new_payments = Payment.objects.filter(created_at__gt=since).exists()

            new_items = InvoiceItem.objects.filter(
                invoice__created_at__gt=since
            ).exists()

        return new_invoices or new_payments or new_items

    except Exception as e:
        logger.error(f"Error checking data changes: {e}")
        return False


def get_dashboard_data_sync(user, branch_id, role):
    """
    Get dashboard data using your existing DashboardViewClass logic
    """
    try:
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)

        # Handle null/undefined branch_id
        if branch_id in ["null", "undefined", ""]:
            branch_id = None

        # SUPER_ADMIN or ADMIN without specific branch - show global data
        if role in ["SUPER_ADMIN", "ADMIN"] and not branch_id:
            return get_global_dashboard_data(today)

        # Branch-specific data (for BRANCH_MANAGER or when branch_id is provided)
        else:
            # Get branch_id from user if not provided
            my_branch = branch_id or getattr(user, "branch_id", None)
            if not my_branch:
                logger.warning(f"No branch ID available for user {user.username}")
                return {
                    "success": False,
                    "message": "No branch assigned",
                    "update_type": "error",
                }

            return get_branch_dashboard_data(my_branch, today, yesterday)

    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        return {"success": False, "message": str(e), "update_type": "error"}


def get_global_dashboard_data(today):
    """Get global dashboard data for superadmin/admin"""
    # Total sales - convert to float
    total_sum = float(
        Invoice.objects.aggregate(total=Sum("total_amount"))["total"] or 0
    )

    # Counts
    total_count_branch = Branch.objects.count()
    total_count_order = Invoice.objects.count()
    total_user_count = User.objects.count()

    # Average order value - convert to float
    average = total_sum / total_count_order if total_count_order else 0

    # Get weekly sales
    start_of_week = today - timedelta(days=today.weekday())  # Monday
    end_of_week = start_of_week + timedelta(days=6)

    current_week_data = list(
        Invoice.objects.filter(
            created_at__date__gte=start_of_week,
            created_at__date__lte=end_of_week,
        )
        .annotate(
            year=ExtractYear("created_at"),
            week=ExtractWeek("created_at"),
            weekday=ExtractWeekDay("created_at"),
        )
        .values("year", "week", "weekday")
        .annotate(total_sales=Sum("total_amount"))
        .order_by("year", "week", "weekday")
    )

    # Map weekdays to day names
    days = {
        "monday": 0,
        "tuesday": 0,
        "wednesday": 0,
        "thursday": 0,
        "friday": 0,
        "saturday": 0,
        "sunday": 0,
    }

    for item in current_week_data:
        if item["weekday"] == 2:  # Monday in Django (1=Sunday, 2=Monday...)
            days["monday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 3:
            days["tuesday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 4:
            days["wednesday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 5:
            days["thursday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 6:
            days["friday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 7:
            days["saturday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 1:
            days["sunday"] = float(item["total_sales"] or 0)

    # Get top selling items - convert quantities to int
    top_selling_items = list(
        InvoiceItem.objects.values("product__name")
        .annotate(total_quantity=Sum("quantity"))
        .order_by("-total_quantity")[:5]
    )

    # Clean up top selling items
    top_selling_items = [
        {
            "product__name": item.get("product__name") or "Unknown",
            "total_orders": int(item["total_quantity"] or 0),  # Match DashboardView field name
        }
        for item in top_selling_items
    ]

    # Calculate sales per category for global view
    sales_per_category = []
    if total_sum > 0:
        sales_per_category_query = (
            InvoiceItem.objects.values("product__category__name")
            .annotate(
                total_category_sum=Sum(
                    ExpressionWrapper(
                        F("quantity") * F("unit_price") - F("discount_amount"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                )
            )
            .annotate(
                category_percent=ExpressionWrapper(
                    (F("total_category_sum") * 100.0) / Value(total_sum),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
        )
        sales_per_category = [
            {
                "product__category__name": item["product__category__name"],
                "total_category_sum": float(item["total_category_sum"] or 0),
                "category_percent": float(item["category_percent"] or 0),
            }
            for item in sales_per_category_query
        ]

    # Get recent activity using serializer for complete data
    recent_invoices_objs = (
        Invoice.objects.select_related("branch", "created_by", "customer", "floor")
        .prefetch_related("bills", "bills__product", "payments")
        .order_by("-created_at")[:5]
    )
    recent_activity = InvoiceResponseSerializer(recent_invoices_objs, many=True).data

    return {
        "success": True,
        "total_sales": float(total_sum),
        "total_branch": total_count_branch,
        "total_user": total_user_count - 1,
        "total_count_order": total_count_order,
        "average_order_value": float(average),
        "sales_per_category": sales_per_category,
        "total_sales_per_category": sales_per_category,
        "Weekely_Sales": days,
        "Weekly_sales": days,
        "top_selling_items": top_selling_items,
        "recent_activity": recent_activity,
        "recent_orders": recent_activity,  # Include both to be safe
        "update_type": "global_update",
        "timestamp": timezone.now().isoformat(),
    }


def get_branch_dashboard_data(branch_id, today, yesterday):
    """Get branch-specific dashboard data"""

    # Get today's invoices
    today_invoices = list(
        Invoice.objects.filter(branch_id=branch_id, created_at__date=today)
    )

    yesterday_invoices = list(
        Invoice.objects.filter(branch_id=branch_id, created_at__date=yesterday)
    )

    # Calculate totals and convert to float immediately
    today_sales = float(sum(i.total_amount for i in today_invoices))
    yesterday_sales = float(sum(i.total_amount for i in yesterday_invoices))

    # Calculate percentage change
    if yesterday_sales == 0:
        sales_percent = float(today_sales - yesterday_sales) if today_sales > 0 else 0
    else:
        sales_percent = ((today_sales - yesterday_sales) / yesterday_sales) * 100

    # Orders count
    today_total_orders = len(today_invoices)
    yesterday_orders = len(yesterday_invoices)

    if yesterday_orders == 0:
        order_percent = (
            float(today_total_orders - yesterday_orders)
            if today_total_orders > 0
            else 0
        )
    else:
        order_percent = (
            (today_total_orders - yesterday_orders) / yesterday_orders
        ) * 100

    # Average order value - convert to float
    today_avg_order = (
        float(today_sales / today_total_orders) if today_total_orders > 0 else 0
    )

    # Get hourly data for peak hours
    hourly_data = list(
        Invoice.objects.filter(branch_id=branch_id, created_at__date=today)
        .annotate(hour=TruncHour("created_at"))
        .values("hour")
        .annotate(total_orders=Count("id"))
        .order_by("hour")
    )

    # Find peak hours
    if hourly_data:
        max_orders = max(item["total_orders"] for item in hourly_data)
        peak_hours = [
            item["hour"].strftime("%I:%M %p") if item["hour"] else "N/A"
            for item in hourly_data
            if item["total_orders"] == max_orders
        ]
    else:
        peak_hours = ["No orders today"]

    # Get top selling items for this branch
    top_selling_items = list(
        InvoiceItem.objects.filter(
            invoice__branch_id=branch_id, invoice__created_at__date=today
        )
        .values("product__name")
        .annotate(total_quantity=Sum("quantity"))
        .order_by("-total_quantity")[:5]
    )

    # Clean up top selling items
    top_selling_items = [
        {
            "product__name": item.get("product__name") or "Unknown",
            "total_orders": int(item["total_quantity"] or 0),  # Match DashboardView field name
        }
        for item in top_selling_items
    ]

    # Get sales by category - using calculated line_total
    sales_by_category_query = list(
        InvoiceItem.objects.filter(
            invoice__branch_id=branch_id, invoice__created_at__date=today
        )
        .values("product__category__name")
        .annotate(
            total_sales=Sum(F("quantity") * F("unit_price") - F("discount_amount"))
        )
        .order_by("-total_sales")[:5]
    )

    # Clean up category data and convert to float (Match field 'total_sales_per_category')
    total_sales_per_category = [
        {
            "product__category__name": item.get("product__category__name")
            or "Uncategorized",
            "category_total_sales": float(item["total_sales"] or 0),  # Match DashboardView field name
        }
        for item in sales_by_category_query
    ]

    # Get recent orders for this branch using serializer
    recent_orders_objs = (
        Invoice.objects.filter(branch_id=branch_id)
        .select_related("branch", "created_by", "customer", "floor")
        .prefetch_related("bills", "bills__product", "payments")
        .order_by("-created_at")[:5]
    )
    recent_orders = InvoiceResponseSerializer(recent_orders_objs, many=True).data

    # Get Hourly Data for the chart (8 AM to 8 PM)
    hourly_data_query = (
        Invoice.objects.filter(
            branch_id=branch_id,
            created_at__date=today,
        )
        .annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(total_sales=Sum("total_amount"))
    )

    hourly_sales_branch = []
    for h in range(8, 21):
        label = f"{h if h <= 12 else h - 12} {'AM' if h < 12 else 'PM'}"
        if h == 12:
            label = "12 PM"
        sales_val = 0
        for item in hourly_data_query:
            if item["hour"] == h:
                sales_val = float(item["total_sales"] or 0)
                break
        hourly_sales_branch.append({"hour": label, "sales": sales_val})

    # Get branch weekly sales (Recalculate or use correct keys)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    branch_week_query = list(
        Invoice.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=start_of_week,
            created_at__date__lte=end_of_week,
        )
        .annotate(
            weekday=ExtractWeekDay("created_at"),
        )
        .values("weekday")
        .annotate(total_sales=Sum("total_amount"))
    )

    branch_days = {
        "monday": 0, "tuesday": 0, "wednesday": 0, "thursday": 0,
        "friday": 0, "saturday": 0, "sunday": 0,
    }
    for item in branch_week_query:
        if item["weekday"] == 2: branch_days["monday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 3: branch_days["tuesday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 4: branch_days["wednesday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 5: branch_days["thursday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 6: branch_days["friday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 7: branch_days["saturday"] = float(item["total_sales"] or 0)
        elif item["weekday"] == 1: branch_days["sunday"] = float(item["total_sales"] or 0)

    return {
        "success": True,
        "today_sales": float(today_sales),
        "sales_percent": round(float(sales_percent), 2),
        "total_orders": today_total_orders,
        "order_percent": round(float(order_percent), 2),
        "avg_orders": round(float(today_avg_order), 2),
        "peak_hours": peak_hours,
        "total_sales_per_category": total_sales_per_category,
        "sales_by_category": total_sales_per_category,  # Compatibility key
        "top_selling_items": top_selling_items,
        "recent_orders": recent_orders,
        "Weekely_Sales": branch_days,
        "Weekly_sales": branch_days,
        "Hourly_sales": hourly_sales_branch,
        "update_type": "branch_update",
        "branch_id": branch_id,
        "timestamp": timezone.now().isoformat(),
    }


# Function to manually trigger updates (call this from your signals)
def trigger_dashboard_update(branch_id=None):
    """
    Manually trigger dashboard update for all connected clients
    """
    logger.info(f"Dashboard update triggered for branch: {branch_id}")
    # In a more advanced implementation, you could use Django Channels
    # to push updates to connected clients. For now, clients will poll.
    return len(active_connections)
