"""
WebSocket Consumer for real-time messaging.
Handles:
  - Real-time message delivery to channel/DM rooms
  - Typing indicators
  - Online presence / status updates
  - Reaction updates
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        """Authenticate and join the appropriate group."""
        self.user = await self.get_user_from_scope()

        if not self.user:
            await self.close(code=4001)
            return

        # Room can be channel_<id> or dm_<id>
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group = f"chat_{self.room_name}"

        # Join channel group
        await self.channel_layer.group_add(self.room_group, self.channel_name)

        # Join user-specific group (for presence)
        self.user_group = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)

        await self.accept()

        # Broadcast presence update
        await self.channel_layer.group_send(
            self.room_group,
            {
                'type': 'presence_update',
                'user_id': self.user.id,
                'username': self.user.username,
                'status': 'active',
            }
        )
        logger.info(f"WS: {self.user.username} joined {self.room_group}")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group'):
            # Broadcast offline status
            await self.channel_layer.group_send(
                self.room_group,
                {
                    'type': 'presence_update',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'status': 'offline',
                }
            )
            await self.channel_layer.group_discard(self.room_group, self.channel_name)
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def receive(self, text_data):
        """Handle incoming WebSocket messages from client."""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type')

        if msg_type == 'chat_message':
            await self.handle_chat_message(data)
        elif msg_type == 'typing':
            await self.handle_typing(data)
        elif msg_type == 'reaction':
            await self.handle_reaction(data)
        elif msg_type == 'message_read':
            await self.handle_read(data)
        elif msg_type == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    async def handle_chat_message(self, data):
        """Save message to DB and broadcast to room."""
        text = data.get('text', '').strip()
        if not text:
            return

        # Save to DB
        message = await self.save_message(
            text=text,
            room_name=self.room_name,
            parent_id=data.get('parent_id'),
            file_url=data.get('file_url'),
        )

        if not message:
            return

        # Broadcast to group
        await self.channel_layer.group_send(
            self.room_group,
            {
                'type': 'chat_message',
                'message': {
                    'id': message['id'],
                    'text': message['text'],
                    'sender_id': message['sender_id'],
                    'sender_username': message['sender_username'],
                    'sender_display_name': message['sender_display_name'],
                    'avatar_color': message['avatar_color'],
                    'created_at': message['created_at'],
                    'parent_id': message['parent_id'],
                    'ai_intent': message['ai_intent'],
                    'ai_sentiment': message['ai_sentiment'],
                    'ai_tags': message['ai_tags'],
                    'reactions': [],
                    'reply_count': 0,
                }
            }
        )

    async def handle_typing(self, data):
        """Broadcast typing indicator."""
        await self.channel_layer.group_send(
            self.room_group,
            {
                'type': 'typing_indicator',
                'user_id': self.user.id,
                'username': self.user.username,
                'is_typing': data.get('is_typing', False),
            }
        )

    async def handle_reaction(self, data):
        """Toggle reaction and broadcast."""
        message_id = data.get('message_id')
        emoji = data.get('emoji')
        if not message_id or not emoji:
            return

        result = await self.toggle_reaction(message_id, emoji)
        await self.channel_layer.group_send(
            self.room_group,
            {
                'type': 'reaction_update',
                'message_id': message_id,
                'emoji': emoji,
                'user_id': self.user.id,
                'username': self.user.username,
                'action': result,
            }
        )

    async def handle_read(self, data):
        """Mark messages as read (placeholder for read receipts)."""
        pass

    # ── Group message handlers (broadcast to WebSocket) ──────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
        }))

    async def typing_indicator(self, event):
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'username': event['username'],
                'is_typing': event['is_typing'],
            }))

    async def reaction_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'reaction_update',
            'message_id': event['message_id'],
            'emoji': event['emoji'],
            'user_id': event['user_id'],
            'username': event['username'],
            'action': event['action'],
        }))

    async def presence_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'user_id': event['user_id'],
            'username': event['username'],
            'status': event['status'],
        }))

    # ── DB operations (sync → async) ─────────────────────────────────────────

    @database_sync_to_async
    def get_user_from_scope(self):
        """Authenticate user from query string token."""
        try:
            query_string = self.scope.get('query_string', b'').decode()
            params = dict(p.split('=') for p in query_string.split('&') if '=' in p)
            token_key = params.get('token')
            if not token_key:
                return None
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except (Token.DoesNotExist, Exception):
            return None

    @database_sync_to_async
    def save_message(self, text, room_name, parent_id=None, file_url=None):
        """Save message to DB and run AI analysis."""
        from .models import Channel, DirectMessage, Message
        from .ai_service import analyze_message

        try:
            channel = None
            dm = None

            if room_name.startswith('channel_'):
                channel_id = room_name.split('_', 1)[1]
                channel = Channel.objects.get(id=channel_id)
            elif room_name.startswith('dm_'):
                dm_id = room_name.split('_', 1)[1]
                dm = DirectMessage.objects.get(id=dm_id)
            else:
                return None

            ai = analyze_message(text)

            msg = Message.objects.create(
                sender=self.user,
                channel=channel,
                dm=dm,
                text=text,
                parent_id=parent_id,
                ai_intent=ai['intent'],
                ai_sentiment=ai['sentiment'],
                ai_tags=ai['tags'],
            )

            profile = getattr(self.user, 'profile', None)
            return {
                'id': msg.id,
                'text': msg.text,
                'sender_id': self.user.id,
                'sender_username': self.user.username,
                'sender_display_name': profile.display_name if profile else self.user.username,
                'avatar_color': profile.avatar_color if profile else '#4A154B',
                'created_at': msg.created_at.isoformat(),
                'parent_id': parent_id,
                'ai_intent': ai['intent'],
                'ai_sentiment': ai['sentiment'],
                'ai_tags': ai['tags'],
            }
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return None

    @database_sync_to_async
    def toggle_reaction(self, message_id, emoji):
        from .models import Message, Reaction
        try:
            message = Message.objects.get(id=message_id)
            reaction, created = Reaction.objects.get_or_create(
                message=message, user=self.user, emoji=emoji
            )
            if not created:
                reaction.delete()
                return 'removed'
            return 'added'
        except Exception:
            return 'error'
