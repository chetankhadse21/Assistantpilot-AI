import os
import sys
import asyncio
import django

# Setup django
sys.path.append(r'd:\freelances\virtual_leader01\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from slack_app.consumers import ChatConsumer
from django.contrib.auth.models import User

async def main():
    consumer = ChatConsumer()
    from asgiref.sync import sync_to_async
    consumer.user = await sync_to_async(User.objects.first)()
    consumer.room_group = "test_group"
    
    # We won't actually broadcast, we just want to see if _send_ai_reply raises an exception.
    # But channel_layer is not set up on this fake consumer.
    # Let's mock it.
    class FakeChannelLayer:
        async def group_send(self, group, message):
            print(f"Broadcast to {group}: {message['type']}")
            if message['type'] == 'chat_message':
                print(message['message']['text'])
                
    consumer.channel_layer = FakeChannelLayer()
    
    try:
        await consumer._send_ai_reply("@ai test", 1, 1)
        print("Success")
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
