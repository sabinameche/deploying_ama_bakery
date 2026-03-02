from django.urls import include, path

from . import views
from .views_dir.sse_views import dashboard_sse

urlpatterns = [
    path("calculate/", include("api.calculate_urls")),
    path("users/", views.UserView.as_view(), name="users_details"),
    path("users/<int:id>/", views.UserView.as_view(), name="users"),
    path("products/<int:id>/", views.ProductView.as_view(), name="product"),
    path("products/", views.ProductView.as_view(), name="product_details"),
    path("category/", views.CategoryViewClass.as_view(), name="Category"),
    path(
        "category/<int:id>/", views.CategoryViewClass.as_view(), name="Category_details"
    ),
    path("branch/<int:id>/", views.BranchViewClass.as_view(), name="Branch_details"),
    path("branch/", views.BranchViewClass.as_view(), name="Branch"),
    path("customer/<int:id>/", views.CustomerView.as_view(), name="customer_details"),
    path("customer/", views.CustomerView.as_view(), name="customer"),
    path("invoice/", views.InvoiceViewClass.as_view(), name="Invoice_details"),
    path("invoice/<int:id>/", views.InvoiceViewClass.as_view(), name="Invoice"),
    path("payments/", views.PaymentView.as_view(), name="payment-list"),
    path(
        "invoice/<int:invoice_id>/payments/",
        views.PaymentView.as_view(),
        name="payment-by-invoice",
    ),
    path(
        "payments/<int:payment_id>/", views.PaymentView.as_view(), name="payment-detail"
    ),
    path("floor/", views.FloorView.as_view(), name="floor-detail"),
    path("floor/<int:floor_id>/", views.FloorView.as_view(), name="floor-details"),
    path(
        "itemactivity/<int:product_id>/<str:action>/",
        views.ItemActivityView.as_view(),
    ),  # used to add , reduce stock
    path(
        "itemactivity/<int:activity_id>/",
        views.ItemActivityView.as_view(),
        name="activity_detail",
    ),
    path("change-password/", views.change_own_password, name="change-password"),
    path(
        "admin-reset-password/<int:user_id>/",
        views.admin_reset_password,
        name="admin-reset-password",
    ),
    path("dashboard/stream/", dashboard_sse, name="dashboard-sse"),
    path("test-rate-limit/", views.test_rate_limit, name="test-rate-limit"),
]
