from api.views import (
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    LogoutView,
)
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/token/", CookieTokenObtainPairView.as_view(), name="get_token"),
    path("api/token/refresh/", CookieTokenRefreshView.as_view(), name="refresh"),
    path("api/logout/", LogoutView.as_view(), name="logout"),
    path("api-auth/", include("rest_framework.urls")),
    path("api/", include("api.urls")),
]
