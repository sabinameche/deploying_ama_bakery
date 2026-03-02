# api/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Branch,
    Customer,
    Floor,
    Invoice,
    InvoiceItem,
    ItemActivity,
    Payment,
    Product,
    ProductCategory,
    User,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + (
        "phone",
        "full_name",
        "user_type",
        "branch",
    )

    list_filter = UserAdmin.list_filter + ("user_type", "branch", "full_name")

    fieldsets = UserAdmin.fieldsets + (
        ("Custom Fields", {"fields": ("phone", "branch", "full_name", "user_type")}),
    )


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "location",
        "created_at",
    )
    list_filter = ("name", "id")
    search_fields = ("name", "name")


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )
    list_filter = ("name", "id")
    search_fields = ("name", "branch.name")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "product_quantity",
        "created_at",
    )
    list_filter = ("category", "is_available", "created_at")
    search_fields = ("name", "category__name")
    ordering = ("created_at",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "created_at", "branch")
    list_filter = ("name", "address", "email")
    search_fields = ["name"]
    ordering = ["name"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "invoice_number",
        "id",
        "branch",
        "customer",
        "invoice_type",
        "total_amount",
        "payment_status",
        "created_at",
        "floor",
        "received_by_waiter",
        "received_by_counter",
    ]

    list_filter = ["invoice_type", "payment_status", "invoice_status", "branch"]

    search_fields = ["invoice_number", "customer__name"]

    readonly_fields = ["uid", "subtotal", "tax_amount", "total_amount", "paid_amount"]

    fieldsets = (
        (
            "Basic Info",
            {
                "fields": (
                    "branch",
                    "floor",
                    "customer",
                    "uid",
                    "invoice_number",
                    "invoice_type",
                )
            },
        ),
        ("created_ats", {"fields": ("created_at", "created_by")}),
        (
            "Financial",
            {
                "fields": (
                    "subtotal",
                    "tax_amount",
                    "discount",
                    "total_amount",
                    "paid_amount",
                )
            },
        ),
        ("Status", {"fields": ("payment_status", "invoice_status", "is_active")}),
    )


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "quantity", "unit_price", "discount_amount","created_at")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "invoice",
        "amount",
        "payment_method",
        "notes",
        "created_at",
        "received_by",
    )


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ("id", "branch", "name", "table_count")

    # Custom order - branch first, then table_count
    # fieldsets = ((None, {"fields": ("branch", "table_count")}),)


@admin.register(ItemActivity)
class ItemActivityAdmin(admin.ModelAdmin):
    list_display = ("id", "types", "change", "quantity", "remarks", "product")
