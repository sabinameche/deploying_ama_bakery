# backend/api/signals.py
import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from ..models import Invoice, InvoiceItem, Payment, Product

logger = logging.getLogger(__name__)

# Optional: You can import this if you set up Django Channels later
# from .sse_views import trigger_dashboard_update


@receiver(post_save, sender=Invoice)
def invoice_saved(sender, instance, created, **kwargs):
    """Trigger dashboard update when invoice is created/updated"""
    action = "created" if created else "updated"
    logger.info(
        f"📝 Invoice {instance.invoice_number} {action} - branch: {instance.branch_id}"
    )
    # Uncomment when you have Channels set up
    # trigger_dashboard_update(branch_id=instance.branch_id)


@receiver(post_delete, sender=Invoice)
def invoice_deleted(sender, instance, **kwargs):
    """Trigger dashboard update when invoice is deleted"""
    logger.info(
        f"🗑️ Invoice {instance.invoice_number} deleted - branch: {instance.branch_id}"
    )
    # trigger_dashboard_update(branch_id=instance.branch_id)


@receiver(post_save, sender=Payment)
def payment_saved(sender, instance, created, **kwargs):
    """Trigger dashboard update when payment is made"""
    action = "created" if created else "updated"
    logger.info(
        f"💰 Payment {instance.transaction_id} {action} - invoice: {instance.invoice.invoice_number}"
    )
    # trigger_dashboard_update(branch_id=instance.invoice.branch_id)


@receiver(post_save, sender=InvoiceItem)
def invoice_item_saved(sender, instance, created, **kwargs):
    """Trigger dashboard update when items are added to invoice"""
    if created:
        logger.info(f"🛒 Item added to invoice {instance.invoice.invoice_number}")
        # trigger_dashboard_update(branch_id=instance.invoice.branch_id)


@receiver(post_save, sender=Product)
def product_saved(sender, instance, **kwargs):
    """Trigger dashboard update when product stock changes"""
    logger.info(
        f"📦 Product {instance.name} stock updated to {instance.product_quantity}"
    )
    # trigger_dashboard_update(branch_id=instance.branch_id)
