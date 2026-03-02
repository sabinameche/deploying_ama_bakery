import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Branch(models.Model):
    name = models.CharField(max_length=20, unique=True, null=True, blank=True)
    location = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.name}"


class ProductCategory(models.Model):
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name="product_categories"
    )
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ["branch", "name"]

    def __str__(self):
        return f"{self.name} ({self.branch})"


class User(AbstractUser):
    phone = models.CharField(max_length=15, blank=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="branch_user",
        null=True,
        blank=True,
    )

    USER_TYPE_CHOICES = [
        ("ADMIN", "Admin"),
        ("BRANCH_MANAGER", "Branch Manager"),
        ("WAITER", "Waiter"),
        ("COUNTER", "Counter"),
        ("KITCHEN", "Kitchen"),
    ]
    full_name = models.CharField(max_length=20, blank=True)
    user_type = models.CharField(
        max_length=20, choices=USER_TYPE_CHOICES, default="WAITER"
    )
    REQUIRED_FIELDS = ["user_type"]

    def __str__(self):
        return self.username


class Product(models.Model):
    uid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    product_quantity = models.IntegerField(default=0)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
    )
    branch = models.ForeignKey(  # Add direct branch field
        Branch,  # Replace with your actual Branch model name
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
    )
    low_stock_bar = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    is_available = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Auto-set branch from category when saving
        if not self.branch_id and self.category:
            self.branch = self.category.branch
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.category.branch.name}"

    class Meta:
        unique_together = ["name", "branch"]  # Now this works!


class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="branch_customer",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'phone'], 
                name='unique_customer_per_branch'
            )
        ]

    def __str__(self):
        return f"{self.name}"

class Floor(models.Model):
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name="floor_branch"
    )
    name = models.CharField(max_length=25, blank=False, unique=True)
    table_count = models.IntegerField(default=1)


class Invoice(models.Model):
    # Define choices
    INVOICE_TYPE_CHOICES = [
        ("SALE", "Sales Invoice"),
        ("PURCHASE", "Purchase Invoice"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("UNPAID", "Unpaid"),
        ("PARTIAL", "Partially Paid"),
        ("PAID", "Fully Paid"),
        ("CANCELLED", "Cancelled"),
    ]

    INVOICE_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("READY", "Ready"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    table_no = models.IntegerField(default=1)
    # Basic Info
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name="invoices"
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="invoices",
        null=True,
        blank=True,
    )
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    invoice_number = models.CharField(max_length=50, unique=True, blank=True)
    invoice_type = models.CharField(
        max_length=10, choices=INVOICE_TYPE_CHOICES, default="SALE"
    )
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_invoices"
    )
    received_by_waiter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="waiter_received_invoices",
    )
    received_by_counter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="counter_received_invoices",
    )
    floor = models.ForeignKey(
        Floor, on_delete=models.SET_NULL, null=True, related_name="floor_invoices"
    )
    notes = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    # Financial Summary (calculated from bills)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Status
    payment_status = models.CharField(
        max_length=10, choices=PAYMENT_STATUS_CHOICES, default="PENDING"
    )
    invoice_status = models.CharField(
        max_length=10, choices=INVOICE_STATUS_CHOICES, default="PENDING"
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["branch", "created_at"]),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number}"

    @property
    def due_amount(self):
        """Calculate due amount dynamically"""
        return Decimal(str(self.total_amount)) - Decimal(str(self.paid_amount))


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="bills")
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["invoice"]),
        ]

    def __str__(self):
        if self.product:
            return f"{self.quantity}"
        return "No Product"

    @property
    def line_total(self):
        try:
            total = Decimal(str(self.quantity)) * Decimal(str(self.unit_price))
            total -= Decimal(str(self.discount_amount))
            return total
        except:
            return Decimal("0")


class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("CARD", "Card"),
        ("ONLINE", "Online"),
        ("QR", "QR"),
    ]

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="payments"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default="CASH"
    )

    # FULL UUID (system transaction id)
    transaction_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )

    notes = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="received_payments"
    )

    def __str__(self):
        return f"Payment {self.amount} - {self.invoice.invoice_number}"  # models.py


class ItemActivity(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    change = models.CharField(max_length=200)
    quantity = models.IntegerField(default=0)
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="to_product",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="to_inovoice",
        null=True,
        blank=True,
    )
    TYPE_CHOICES = [
        ("ADD_STOCK", "Add Stock"),
        ("REDUCE_STOCK", "Reduce Stock"),
        ("EDIT_STOCK", "Edit Stock"),
        ("SALES", "Sales"),
    ]
    types = models.CharField(max_length=50, choices=TYPE_CHOICES)
    remarks = models.TextField(blank=True)
