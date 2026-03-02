import json

from channels.generic.websocket import AsyncWebsocketConsumer


class KitchenOrdersConsumer(AsyncWebsocketConsumer):
    """
    Broadcast consumer for kitchen screens.
    Listens for invoice creation and status updates.
    """

    async def connect(self):
        self.group_name = "kitchen_orders"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("kitchen_orders", self.channel_name)

    async def invoice_created(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "invoice_created",
                    "invoice_id": event.get("invoice_id"),
                }
            )
        )

    async def invoice_updated(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "invoice_updated",
                    "invoice_id": event.get("invoice_id"),
                    "status": event.get("status"),
                }
            )
        )


class OrdersConsumer(AsyncWebsocketConsumer):
    """
    Broadcast consumer for waiter/counter screens.
    Listens for invoice creation and status updates (e.g. kitchen marks ready).
    """

    async def connect(self):
        self.group_name = "orders"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("orders", self.channel_name)

    async def invoice_created(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "invoice_created",
                    "invoice_id": event.get("invoice_id"),
                }
            )
        )

    async def invoice_updated(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "invoice_updated",
                    "invoice_id": event.get("invoice_id"),
                    "status": event.get("status"),
                }
            )
        )
