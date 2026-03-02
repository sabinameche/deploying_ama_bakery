from datetime import date, datetime, time, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Sum, Value
from django.db.models.functions import (
    ExtractHour,
    ExtractWeek,
    ExtractWeekDay,
    ExtractYear,
    TruncHour,
)
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Branch, Invoice, InvoiceItem, User


class DashboardViewClass(APIView):
    todaydate = date.today()
    yesterdaydate = todaydate - timedelta(days=1)

    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    def date_filter(self, branch, start_date, end_date):
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date + timedelta(days=1), time.min)

        return Invoice.objects.filter(
            branch=branch, created_at__gte=start_datetime, created_at__lt=end_datetime
        )

    def get(self, request, branch_id=None):
        role = self.get_user_role(request.user)
        my_branch = getattr(request.user, "branch", None)

        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {"success": False, "message": "Insufficient permissions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if role in ["SUPER_ADMIN", "ADMIN"]:
            if not branch_id:
                # Global summary for network overview
                total_sum = (
                    Invoice.objects.aggregate(total=Sum("total_amount"))["total"] or 0
                )
                total_count_branch = Branch.objects.all().count()
                total_count_order = Invoice.objects.all().count()
                total_user_count = User.objects.all().count()
                average = total_sum / total_count_order if total_count_order else 0

                today = timezone.now().date()

                start_of_week = today - timedelta(days=today.weekday())  # Monday
                print("st_week->>", start_of_week)

                end_of_week = start_of_week + timedelta(days=6)

                current_week_data = (
                    Invoice.objects.filter(
                        created_at__date__gte=start_of_week,
                        created_at__date__lte=end_of_week,
                    )
                    .annotate(
                        year=ExtractYear("created_at"),
                        week=ExtractWeek("created_at"),
                        weekday=ExtractWeekDay(
                            "created_at"
                        ),  # 1=Sunday, 2=Monday, ..., 7=Saturday
                    )
                    .values("year", "week", "weekday")
                    .annotate(
                        total_sales=Sum("total_amount"),
                    )
                    .order_by("year", "week", "weekday")
                )

                days = {
                    "monday": 0,
                    "tuesday": 0,
                    "wednesday": 0,
                    "thursday": 0,
                    "friday": 0,
                    "saturday": 0,
                    "sunday": 0,
                }
                print("Current Week Data:")

                for item in current_week_data:
                    print(item)
                    if item["weekday"] == 2:
                        days["monday"] = item["total_sales"]
                    elif item["weekday"] == 3:
                        days["tuesday"] = item["total_sales"]
                    elif item["weekday"] == 4:
                        days["wednesday"] = item["total_sales"]
                    elif item["weekday"] == 5:
                        days["thursday"] = item["total_sales"]
                    elif item["weekday"] == 6:
                        days["friday"] = item["total_sales"]
                    elif item["weekday"] == 7:
                        days["saturday"] = item["total_sales"]
                    elif item["weekday"] == 1:
                        days["sunday"] = item["total_sales"]

                # sales by category pie chart percentage

                if total_sum > 0:
                    sales_per_category = (
                        InvoiceItem.objects.values("product__category__name")
                        .annotate(
                            total_category_sum=Sum(
                                ExpressionWrapper(
                                    F("quantity") * F("unit_price")
                                    - F("discount_amount"),
                                    output_field=DecimalField(
                                        max_digits=12, decimal_places=2
                                    ),
                                )
                            )
                        )
                        .annotate(
                            category_percent=ExpressionWrapper(
                                (F("total_category_sum") * 100.0) / Value(total_sum),
                                output_field=DecimalField(
                                    max_digits=10, decimal_places=2
                                ),
                            )
                        )
                    )
                else:
                    sales_per_category = []

                # branch performance
                top_performance_branch = (
                    Branch.objects.values("name")
                    .annotate(total_sales_per_branch=Sum(F("invoices__total_amount")))
                    .order_by("-total_sales_per_branch")[:5]
                )

                # best selling items
                top_sold_items = (
                    InvoiceItem.objects.values("product__name")
                    .annotate(total_sold_units=Sum("quantity"))
                    .order_by("-total_sold_units")[:5]
                )

                return Response(
                    {
                        "success": True,
                        "total_sales": total_sum,
                        "total_branch": total_count_branch,
                        "total_user": total_user_count - 1,
                        "total_count_order": total_count_order,
                        "average_order_value": average,
                        "sales_per_category": sales_per_category,
                        "Weekely_Sales": days,
                        "top_perfomance_branch": top_performance_branch,
                        "top_selling_items": top_sold_items,
                    },
                    status=status.HTTP_200_OK,
                )

            my_branch = branch_id

        if my_branch:
            # 1.today's total sales amount
            today_invoices = self.date_filter(my_branch, self.todaydate, self.todaydate)
            yesterday_invoices = self.date_filter(
                my_branch, self.yesterdaydate, self.yesterdaydate
            )

            yesterday_sales = 0
            today_sales = 0
            for invoice in today_invoices:
                print(invoice.created_at)
                print("Raw data time format ->>", invoice.created_at)
                today_sales += invoice.total_amount

            for invoice in yesterday_invoices:
                yesterday_sales += invoice.total_amount

            if yesterday_sales == 0:
                sales_percent = today_sales - yesterday_sales
                sales_percent = today_sales - yesterday_sales
            else:
                sales_percent = (
                    (today_sales - yesterday_sales) / yesterday_sales
                ) * 100

            # 2.today's total orders
            today_total_orders = today_invoices.count()
            yesterday_orders = yesterday_invoices.count()

            # 2.calculating order percent
            if yesterday_orders == 0:
                order_percent = float(today_total_orders - yesterday_orders)
            else:
                order_percent = (
                    (today_total_orders - yesterday_orders) / yesterday_orders
                ) * 100

            # 3. avg order value
            if today_total_orders == 0:
                today_avg_order = 0

            else:
                today_avg_order = Decimal(str((today_sales) / today_total_orders))

            if yesterday_orders == 0:
                yesterday_avg_order = 0
            else:
                yesterday_avg_order = Decimal(str((yesterday_sales) / yesterday_orders))

            if yesterday_avg_order == 0:
                avg_order_percent = (today_avg_order) - (yesterday_avg_order)
            else:
                avg_order_percent = (
                    (today_avg_order - yesterday_avg_order) / yesterday_avg_order
                ) * 100

            hourly_orders = (
                self.date_filter(my_branch, self.todaydate, self.todaydate)
                .annotate(hour=TruncHour("created_at"))
                .values("hour")
                .annotate(total_orders=Count("id"))
            )

            max_orders = hourly_orders.aggregate(max_orders=Max("total_orders"))[
                "max_orders"
            ]
            if max_orders is not None:
                peak_hours = hourly_orders.filter(total_orders=max_orders)
                formatted_peak_hours = [
                    h["hour"].strftime("%I:%M %p") for h in peak_hours
                ]
            else:
                formatted_peak_hours = []

            print("Max Orders-> ", max_orders)

            # 5.sales by category piechart
            total_sales_per_category = (
                InvoiceItem.objects.filter(invoice__branch=my_branch)
                .values("product__category__name")
                .annotate(
                    category_total_sales=Sum(
                        ExpressionWrapper(
                            F("quantity") * F("unit_price") - F("discount_amount"),
                            output_field=DecimalField(max_digits=10, decimal_places=2),
                        )
                    )
                )
                .order_by("-category_total_sales")[:5]
            )

            # 6. top selling items
            top_selling_items = (
                InvoiceItem.objects.filter(invoice__branch=my_branch)
                .values("product__name")
                .annotate(total_orders=Sum("quantity"))
                .order_by("-total_orders")[:5]
            )

            # 7. current week sales (Mon–Sun) for the Weekly Sales chart
            today = timezone.now().date()
            start_of_week = today - timedelta(days=today.weekday())  # Monday
            end_of_week = start_of_week + timedelta(days=6)

            branch_week_data = (
                Invoice.objects.filter(
                    branch=my_branch,
                    created_at__date__gte=start_of_week,
                    created_at__date__lte=end_of_week,
                )
                .annotate(
                    year=ExtractYear("created_at"),
                    week=ExtractWeek("created_at"),
                    weekday=ExtractWeekDay("created_at"),  # 1=Sun, 2=Mon, ..., 7=Sat
                )
                .values("year", "week", "weekday")
                .annotate(total_sales=Sum("total_amount"))
                .order_by("year", "week", "weekday")
            )

            branch_days = {
                "monday": 0,
                "tuesday": 0,
                "wednesday": 0,
                "thursday": 0,
                "friday": 0,
                "saturday": 0,
                "sunday": 0,
            }
            for item in branch_week_data:
                if item["weekday"] == 2:
                    branch_days["monday"] = item["total_sales"]
                elif item["weekday"] == 3:
                    branch_days["tuesday"] = item["total_sales"]
                elif item["weekday"] == 4:
                    branch_days["wednesday"] = item["total_sales"]
                elif item["weekday"] == 5:
                    branch_days["thursday"] = item["total_sales"]
                elif item["weekday"] == 6:
                    branch_days["friday"] = item["total_sales"]
                elif item["weekday"] == 7:
                    branch_days["saturday"] = item["total_sales"]
                elif item["weekday"] == 1:
                    branch_days["sunday"] = item["total_sales"]

            # 8. Hourly sales for today (8am to 8pm) - Branch specific
            hourly_data_branch = (
                Invoice.objects.filter(
                    branch=my_branch,
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
                for item in hourly_data_branch:
                    if item["hour"] == h:
                        sales_val = float(item["total_sales"] or 0)
                        break
                hourly_sales_branch.append({"hour": label, "sales": sales_val})

            return Response(
                {
                    "success": True,
                    "today_sales": today_sales,
                    "sales_percent": sales_percent,
                    "total_orders": today_total_orders,
                    "order_percent": order_percent,
                    "avg_orders": today_avg_order,
                    "avg_order_percent": avg_order_percent,
                    "peak_hours": formatted_peak_hours,
                    "total_sales_per_category": total_sales_per_category,
                    "top_selling_items": top_selling_items,
                    "Weekely_Sales": branch_days,
                    "Hourly_sales": hourly_sales_branch,
                }
            )


def report_dashboard(my_branch):
    current_month = timezone.localdate().month
    current_year = timezone.localdate().year

    last_month = timezone.localdate() - relativedelta(months=1)
    current_month_sales = (
        Invoice.objects.filter(
            branch=my_branch,
            created_at__year=current_year,
            created_at__month=current_month,
        ).aggregate(total_sales_amount=Sum("total_amount"))["total_sales_amount"]
        or 0
    )

    # total orders
    total_orders = Invoice.objects.filter(
        branch=my_branch,
        created_at__year=current_year,
        created_at__month=current_month,
    )

    # average order
    avg_order_month = current_month_sales / total_orders.count()

    print("This is last month->", last_month.month)

    # growth percent
    last_month_sales = Invoice.objects.filter(
        branch=my_branch, created_at__month=last_month.month
    )

    for sale in last_month_sales:
        print(sale)
    # growth percent
    last_month_sales = (
        Invoice.objects.filter(
            branch=my_branch, created_at__month=last_month.month
        ).aggregate(total_sales=Sum("total_amount"))["total_sales"]
        or 0
    )

    if last_month_sales == 0:
        growth_percent = current_month_sales - last_month_sales
    else:
        growth_percent = (
            (current_month_sales - last_month_sales) / last_month_sales
        ) * 100

    today = timezone.now().date()

    start_of_week = today - timedelta(days=today.weekday())  # Monday

    end_of_week = start_of_week + timedelta(days=6)

    current_week_data = (
        Invoice.objects.filter(
            branch=my_branch,
            created_at__date__gte=start_of_week,
            created_at__date__lte=end_of_week,
        )
        .annotate(
            year=ExtractYear("created_at"),
            week=ExtractWeek("created_at"),
            weekday=ExtractWeekDay("created_at"),  # 1=Sunday, 2=Monday, ..., 7=Saturday
        )
        .values("year", "week", "weekday")
        .annotate(
            total_sales=Sum("total_amount"),
        )
        .order_by("year", "week", "weekday")
    )

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
        print(item)

        if item["weekday"] == 2:
            days["monday"] = item["total_sales"]
        elif item["weekday"] == 3:
            days["tuesday"] = item["total_sales"]
        elif item["weekday"] == 4:
            days["wednesday"] = item["total_sales"]
        elif item["weekday"] == 5:
            days["thursday"] = item["total_sales"]
        elif item["weekday"] == 6:
            days["friday"] = item["total_sales"]
        elif item["weekday"] == 7:
            days["saturday"] = item["total_sales"]
        elif item["weekday"] == 1:
            days["sunday"] = item["total_sales"]

    # Hourly sales for today (8am to 8pm)
    hourly_data_raw = (
        Invoice.objects.filter(
            branch=my_branch,
            created_at__date=today,
        )
        .annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(total_sales=Sum("total_amount"))
    )

    # Initialize hours 8am to 8pm as a list for charts
    hourly_sales_list = []
    for h in range(8, 21):
        label = f"{h if h <= 12 else h - 12} {'AM' if h < 12 else 'PM'}"
        if h == 12:
            label = "12 PM"

        sales_val = 0
        for item in hourly_data_raw:
            if item["hour"] == h:
                sales_val = float(item["total_sales"] or 0)
                break
        hourly_sales_list.append({"hour": label, "sales": sales_val})

    top_selling_items_count = (
        InvoiceItem.objects.filter(invoice__branch=my_branch)
        .values("product__name")
        .annotate(total_orders=Sum("quantity"))
        .annotate(
            total_sales=Sum(
                ExpressionWrapper(
                    F("quantity") * F("unit_price") - F("discount_amount"),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
        )
        .order_by("-total_orders")[:5]
    )

    return {
        "success": True,
        "total_month_sales": current_month_sales,
        "total_month_orders": total_orders.count(),
        "Weekly_sales": days,
        "Hourly_sales": hourly_sales_list,
        "avg_order_month": avg_order_month,
        "top_selling_items_count": top_selling_items_count,
        "growth_percent": growth_percent,
    }


class ReportDashboardViewClass(APIView):
    def get_user_role(self, user):
        return "SUPER_ADMIN" if user.is_superuser else getattr(user, "user_type", "")

    def get(self, request, branch_id=None):
        role = self.get_user_role(request.user)
        my_branch = getattr(request.user, "branch", None)

        if role not in ["SUPER_ADMIN", "ADMIN", "BRANCH_MANAGER"]:
            return Response(
                {"success": False, "message": "Insufficient permissions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if role in ["SUPER_ADMIN", "ADMIN"]:
            if not branch_id:
                return Response(
                    {
                        "success": False,
                        "message": "branch_id is required for admin/superadmin",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            my_branch = branch_id

        data = report_dashboard(my_branch)
        return Response({"success": True, **data}, status=status.HTTP_200_OK)
