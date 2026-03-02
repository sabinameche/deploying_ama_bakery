from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    # Kitchen live orders feed
    re_path(r"ws/kitchen/$", consumers.KitchenOrdersConsumer.as_asgi()),
    # Waiter/Counter orders feed
    re_path(r"ws/orders/$", consumers.OrdersConsumer.as_asgi()),
]

