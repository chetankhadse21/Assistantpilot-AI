"""
WebSocket Consumer for real-time messaging.
Handles:
  - Real-time message delivery to channel/DM rooms
  - Typing indicators
  - Online presence / status updates
  - Reaction updates
  - Gemini AI bot auto-reply
"""

import json
import logging
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)

AI_BOT_NAME = "PilotAI"
AI_BOT_COLOR = "#7C3AED"

def is_ai_triggered(text: str) -> bool:
    """Check if the message is directed at the AI bot."""
    text_l = text.lower().strip()
    triggers = ("@ai", "/ai", "@pilotai", "!ai")
    return any(text_l.startswith(t) for t in triggers)

def strip_trigger(text: str) -> str:
    """Remove the trigger prefix from the user's message."""
    for prefix in ("@pilotai", "@ai", "/ai", "!ai"):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip()
    return text.strip()

def get_workspace_data(workspace_id):
    if not workspace_id:
        return None
    from .models import Workspace, WorkspaceMember
    try:
        ws = Workspace.objects.filter(id=workspace_id).first()
        if not ws:
            return None
        members = WorkspaceMember.objects.filter(workspace=ws).select_related('user', 'user__profile')
        
        details = []
        for m in members:
            prof = getattr(m.user, 'profile', None)
            if prof:
                perf_stats = f"Tasks: {prof.tasks_completed}/{prof.tasks_assigned}, Deadlines Met: {prof.deadlines_met}, Avg Time: {prof.avg_time_per_task}h, Efficiency: {prof.efficiency}%, Reliability: {prof.reliability}%"
                status_msg = f" - '{prof.status_text}'" if prof.status_text else ""
                details.append(
                    f"- {m.user.username} ({m.role}) | Level: {prof.get_employee_level_display()} | "
                    f"Skill: {prof.skill_strength or 'None'} | Status: {prof.get_status_display()}{status_msg} | "
                    f"Performance: {perf_stats}"
                )
            else:
                details.append(f"- {m.user.username} ({m.role})")

        return {
            'name': ws.name,
            'github_repo': ws.github_repo,
            'member_count': members.count(),
            'member_details': "\n".join(details)
        }
    except Exception as e:
        logger.error(f"Error fetching workspace data: {e}")
        return None

def call_gemini(query: str, ws_data: dict = None, file_path: str = None, workspace_id: int = None) -> str:
    """Synchronous call to Gemini with context enrichment via PilotAI Service Layer."""
    try:
        from .pilot_ai_core import AIServiceLayer
        
        # If there's an attached file, append to query to give context
        if file_path:
            query = f"{query}\n[Attached file context: {file_path}]"
            
        return AIServiceLayer.call_pilot_ai(query=query, workspace_id=workspace_id, file_path=file_path)
    except Exception as e:
        logger.error(f"Error in call_gemini routing to AIServiceLayer: {e}")
        return "Decision:\nSpiderman should coordinate next steps.\nReason:\nPilotAI encountered a routing error.\nRisk:\nDelayed response."



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
        """Save message to DB, broadcast to room, and optionally trigger AI reply."""
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

        # Broadcast user message to group
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

        # Broadcast milestone update if triggered
        if message.get('milestone_update'):
            upd = message['milestone_update']
            
            # Broadcast automated AI announcement message
            await self.channel_layer.group_send(
                self.room_group,
                {
                    'type': 'chat_message',
                    'message': {
                        'id': upd['bot_message_id'],
                        'text': upd['bot_message_text'],
                        'sender_id': -2,  # AI milestone bot ID
                        'sender_username': 'PilotAI',
                        'sender_display_name': '🤖 AI Pilot',
                        'avatar_color': '#7C3AED',
                        'created_at': upd['bot_message_created_at'] + 'Z',
                        'parent_id': None,
                        'ai_intent': 'announcement',
                        'ai_sentiment': 'positive',
                        'ai_tags': ['ai-milestone-update'],
                        'reactions': [],
                        'reply_count': 0,
                    }
                }
            )

            # Broadcast WebSocket event to update UI progress bar
            await self.channel_layer.group_send(
                self.room_group,
                {
                    'type': 'milestone_update',
                    'milestone_id': upd['milestone_id'],
                    'progress_percentage': upd['progress_percentage']
                }
            )

        # ── Gemini AI Auto-Reply ──────────────────────────────────────────────
        if is_ai_triggered(text):
            # Fire-and-forget the AI reply so we don't block the WS loop
            workspace_id = message.get('workspace_id')
            asyncio.ensure_future(self._send_ai_reply(text, message['id'], workspace_id))

    async def _send_ai_reply(self, original_text: str, parent_id: int, workspace_id: int = None):
        """Get a Gemini reply and broadcast it as the AI bot."""
        try:
            query = strip_trigger(original_text)
            if not query:
                query = "Hello! How can I help with your project?"

            # Broadcast typing indicator for AI bot
            await self.channel_layer.group_send(
                self.room_group,
                {
                    'type': 'typing_indicator',
                    'user_id': -1,  # sentinel for AI bot
                    'username': AI_BOT_NAME,
                    'is_typing': True,
                }
            )

            try:
                ws_data = await self.get_workspace_data_sync(workspace_id)
            except Exception as e:
                logger.error(f"Error fetching workspace data in _send_ai_reply: {e}")
                ws_data = None

            # Get file path if parent message has an attachment
            file_path = await self.get_message_file_path(parent_id)

            # Call Gemini in a thread so we don't block the async loop
            try:
                loop = asyncio.get_running_loop()
                ai_reply = await loop.run_in_executor(
                    None, call_gemini, query, ws_data, file_path, workspace_id
                )
            except Exception as e:
                logger.error(f"Error in Gemini executor thread: {e}")
                ai_reply = "⚠️ I'm having trouble connecting right now. Please try again in a moment."

            # Save the AI reply in the database
            try:
                from .models import UserProfile
                # Get or create AI user
                ai_user, _ = await database_sync_to_async(User.objects.get_or_create)(
                    username=AI_BOT_NAME, defaults={'is_active': False}
                )
                await database_sync_to_async(UserProfile.objects.get_or_create)(
                    user=ai_user, defaults={'display_name': '🤖 PilotAI', 'avatar_color': AI_BOT_COLOR}
                )

                # Save AI message in the database
                ai_msg_data = await self.save_message(
                    text=ai_reply,
                    room_name=self.room_name,
                    parent_id=None,
                    sender=ai_user,
                )
            except Exception as e:
                logger.error(f"Error saving AI message in database: {e}")
                ai_msg_data = None

            # Stop typing indicator
            await self.channel_layer.group_send(
                self.room_group,
                {
                    'type': 'typing_indicator',
                    'user_id': -1,
                    'username': AI_BOT_NAME,
                    'is_typing': False,
                }
            )

            # Broadcast the AI reply as a special bot message
            if ai_msg_data:
                await self.channel_layer.group_send(
                    self.room_group,
                    {
                        'type': 'chat_message',
                        'message': {
                            'id': ai_msg_data['id'],
                            'text': ai_msg_data['text'],
                            'sender_id': ai_msg_data['sender_id'],
                            'sender_username': ai_msg_data['sender_username'],
                            'sender_display_name': ai_msg_data['sender_display_name'],
                            'avatar_color': ai_msg_data['avatar_color'],
                            'created_at': ai_msg_data['created_at'],
                            'parent_id': ai_msg_data['parent_id'],
                            'ai_intent': ai_msg_data['ai_intent'],
                            'ai_sentiment': ai_msg_data['ai_sentiment'],
                            'ai_tags': ai_msg_data['ai_tags'],
                            'reactions': [],
                            'reply_count': 0,
                            'is_ai_bot': True,
                        }
                    }
                )
            else:
                # Fallback to ephemeral message if database save failed
                await self.channel_layer.group_send(
                    self.room_group,
                    {
                        'type': 'chat_message',
                        'message': {
                            'id': f"ai_{parent_id}",
                            'text': ai_reply,
                            'sender_id': -1,
                            'sender_username': AI_BOT_NAME,
                            'sender_display_name': '🤖 PilotAI',
                            'avatar_color': AI_BOT_COLOR,
                            'created_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
                            'parent_id': None,
                            'ai_intent': 'general',
                            'ai_sentiment': 'neutral',
                            'ai_tags': ['ai-reply'],
                            'reactions': [],
                            'reply_count': 0,
                            'is_ai_bot': True,
                        }
                    }
                )
        except Exception as ex:
            logger.exception(f"Unhandled error in _send_ai_reply: {ex}")
            try:
                await self.channel_layer.group_send(
                    self.room_group,
                    {
                        'type': 'typing_indicator',
                        'user_id': -1,
                        'username': AI_BOT_NAME,
                        'is_typing': False,
                    }
                )
            except Exception:
                pass



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

    async def milestone_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'milestone_update',
            'milestone_id': event['milestone_id'],
            'progress_percentage': event['progress_percentage']
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
    def get_workspace_data_sync(self, workspace_id):
        return get_workspace_data(workspace_id)

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
    def save_message(self, text, room_name, parent_id=None, file_url=None, sender=None):
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

            workspace = channel.workspace if channel else (dm.workspace if dm else None)

            ai = analyze_message(text)

            msg_sender = sender or self.user

            msg = Message.objects.create(
                sender=msg_sender,
                channel=channel,
                dm=dm,
                text=text,
                parent_id=parent_id,
                ai_intent=ai['intent'],
                ai_sentiment=ai['sentiment'],
                ai_tags=ai['tags'],
            )

            # --- AI Calendar Auto-Scheduler ---
            intent = ai['intent']
            if intent in ['meeting', 'task']:
                date_str = None
                for t in ai['tags']:
                    if t.startswith('date:') or t.startswith('time:'):
                        date_str = t.split(':', 1)[1]
                        break
                if date_str:
                    from .ai_service import parse_fuzzy_date
                    from django.utils import timezone
                    from .models import CalendarEvent
                    dt = parse_fuzzy_date(date_str)
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                        
                    event_type = 'meeting' if intent == 'meeting' else 'deadline'
                    if workspace:
                        CalendarEvent.objects.create(
                            workspace=workspace,
                            title=f"{event_type.title()}: {msg.text[:40]}",
                            description=msg.text,
                            event_type=event_type,
                            date=dt,
                            created_by=msg_sender
                        )

            # --- AI project progress check ---
            milestone_update = None
            if channel and channel.is_project_channel:
                try:
                    from .gemini_service import check_and_update_project_progress
                    milestone_update = check_and_update_project_progress(msg)
                except Exception as ex:
                    logger.error(f"Milestone update check failed: {ex}")

            profile = getattr(msg_sender, 'profile', None)
            return {
                'id': msg.id,
                'text': msg.text,
                'sender_id': msg_sender.id,
                'sender_username': msg_sender.username,
                'sender_display_name': profile.display_name if profile else msg_sender.username,
                'avatar_color': profile.avatar_color if profile else '#4A154B',
                'created_at': msg.created_at.isoformat(),
                'parent_id': parent_id,
                'ai_intent': ai['intent'],
                'ai_sentiment': ai['sentiment'],
                'ai_tags': ai['tags'],
                'workspace_id': workspace.id if workspace else None,
                'milestone_update': milestone_update,
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

    @database_sync_to_async
    def get_message_file_path(self, message_id):
        from .models import Message
        try:
            msg = Message.objects.get(id=message_id)
            return msg.file.path if msg.file else None
        except Exception:
            return None
