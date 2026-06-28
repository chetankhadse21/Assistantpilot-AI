from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import generics, status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied

from .models import (
    Workspace, WorkspaceMember, Channel, DirectMessage,
    Message, Reaction, UserProfile, PinnedMessage, CalendarEvent,
    Project, Milestone, Member, Task, AIMemory
)
from .serializers import (
    UserSerializer, UserRegisterSerializer, WorkspaceSerializer,
    ChannelSerializer, ChannelCreateSerializer, DirectMessageSerializer,
    MessageSerializer, ReactionSerializer, WorkspaceMemberSerializer,
    CalendarEventSerializer,
    ProjectSerializer, MilestoneSerializer, MemberSerializer, TaskSerializer, AIMemorySerializer
)
from .ai_service import analyze_message, smart_search, summarize_channel_activity
from .github_service import build_project_report, detect_github_intent
from .gemini_service import recommend_task_assignment, provide_project_insights, detect_risks
from .ai_pm_service import (
    get_task_recommendation, run_sprint_planning, run_risk_analysis,
    run_workload_balancing, run_member_skill_analysis
)


def add_user_to_all_workspaces(user):
    """Add a user to ALL workspaces and their public channels."""
    for workspace in Workspace.objects.all():
        WorkspaceMember.objects.get_or_create(
            workspace=workspace, user=user,
            defaults={'role': 'member'}
        )
        for channel in workspace.channels.filter(channel_type='public'):
            channel.members.add(user)


def add_all_users_to_workspace(workspace):
    """Add ALL existing users to a newly created workspace."""
    for user in User.objects.all():
        WorkspaceMember.objects.get_or_create(
            workspace=workspace, user=user,
            defaults={'role': 'member'}
        )
        for channel in workspace.channels.filter(channel_type='public'):
            channel.members.add(user)


# ── Auth Views ────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = UserRegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        # Auto join all existing workspaces
        add_user_to_all_workspaces(user)
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    from django.contrib.auth import authenticate
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if user:
        token, _ = Token.objects.get_or_create(user=user)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.status = 'active'
        profile.save()
        # Make sure user is in all workspaces
        add_user_to_all_workspaces(user)
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data
        })
    return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
def logout_view(request):
    try:
        request.user.profile.status = 'offline'
        request.user.profile.save()
    except Exception:
        pass
    try:
        request.user.auth_token.delete()
    except Exception:
        pass
    return Response({'message': 'Logged out'})


@api_view(['GET', 'PUT'])
def me(request):
    if request.method == 'GET':
        return Response(UserSerializer(request.user).data)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    data = request.data
    profile.display_name = data.get('display_name', profile.display_name)
    profile.bio = data.get('bio', profile.bio)
    profile.status = data.get('status', profile.status)
    profile.status_emoji = data.get('status_emoji', profile.status_emoji)
    profile.status_text = data.get('status_text', profile.status_text)
    profile.avatar_color = data.get('avatar_color', profile.avatar_color)
    profile.employee_level = data.get('employee_level', profile.employee_level)
    profile.skill_strength = data.get('skill_strength', profile.skill_strength)
    profile.save()
    return Response(UserSerializer(request.user).data)


@api_view(['POST'])
def join_all_workspaces(request):
    add_user_to_all_workspaces(request.user)
    return Response({'message': 'Joined all workspaces and channels'})


@api_view(['GET'])
def all_users(request):
    """Get ALL users in the system for DM and members list."""
    users = User.objects.exclude(id=request.user.id).select_related('profile')
    return Response(UserSerializer(users, many=True).data)


# ── Workspace Views ───────────────────────────────────────────────────────────

class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Workspace.objects.all()

    def perform_create(self, serializer):
        workspace = serializer.save(created_by=self.request.user)
        WorkspaceMember.objects.create(
            workspace=workspace, user=self.request.user, role='admin'
        )
        # Create default channels
        for ch_name, desc in [
            ('general', 'Company-wide announcements'),
            ('random', 'Non-work banter and fun'),
        ]:
            channel = Channel.objects.create(
                workspace=workspace, name=ch_name,
                description=desc, channel_type='public',
                created_by=self.request.user
            )
            channel.members.add(self.request.user)

        # Add ALL existing users to this workspace
        add_all_users_to_workspace(workspace)

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        workspace = self.get_object()
        all_members = User.objects.filter(
            workspacemember__workspace=workspace
        ).select_related('profile')
        return Response(UserSerializer(all_members, many=True).data)

    @action(detail=True, methods=['patch'], url_path='set-repo')
    def set_repo(self, request, pk=None):
        workspace = self.get_object()
        if not request.user.is_superuser:
            try:
                member = WorkspaceMember.objects.get(workspace=workspace, user=request.user)
                if member.role != 'admin':
                    return Response({'error': 'Only admins can link a GitHub repo.'}, status=403)
            except WorkspaceMember.DoesNotExist:
                return Response({'error': 'Not a workspace member.'}, status=403)

        repo = request.data.get('github_repo', '').strip()
        workspace.github_repo = repo
        workspace.save(update_fields=['github_repo'])
        return Response({'github_repo': repo, 'message': f'GitHub repo linked: {repo}'})

    @action(detail=True, methods=['get'], url_path='dashboard-stats')
    def dashboard_stats(self, request, pk=None):
        workspace = self.get_object()
        
        # 1. Total members
        total_members = WorkspaceMember.objects.filter(workspace=workspace).count()
        
        # 2. Total messages in this workspace's channels
        messages = Message.objects.filter(channel__workspace=workspace, is_deleted=False)
        total_messages = messages.count()
        
        # 3. Sentiment stats (positive messages)
        positive_msg_count = messages.filter(ai_sentiment='positive').count()
        negative_msg_count = messages.filter(ai_sentiment='negative').count()
        neutral_msg_count = messages.filter(ai_sentiment='neutral').count()
        
        # 4. Intent stats (tasks, questions)
        task_msg_count = messages.filter(ai_intent='task').count()
        question_msg_count = messages.filter(ai_intent='question').count()
        
        # 5. Members progress metrics from UserProfile
        member_profiles = UserProfile.objects.filter(user__workspacemember__workspace=workspace)
        total_tasks_assigned = sum(p.tasks_assigned for p in member_profiles)
        total_tasks_completed = sum(p.tasks_completed for p in member_profiles)
        
        progress = 0
        if total_tasks_assigned > 0:
            progress = round((total_tasks_completed / total_tasks_assigned) * 100, 2)
            
        # 6. Commits: Fetch from GitHub if linked
        commits = []
        if workspace.github_repo:
            try:
                from .github_service import get_recent_commits
                owner, repo = workspace.github_repo.strip().split('/', 1)
                commits = get_recent_commits(owner, repo, limit=8)
            except Exception as e:
                # Silently ignore github fetch errors
                pass

        # 7. AI Project Channels milestone progress metrics
        project_channels = Channel.objects.filter(workspace=workspace, is_project_channel=True, is_archived=False)
        projects_data = []
        for chan in project_channels:
            total_m = chan.milestones.count()
            completed_m = chan.milestones.filter(is_completed=True).count()
            chan_progress = round((completed_m / total_m) * 100, 2) if total_m > 0 else 0.0
            
            projects_data.append({
                "channel_id": chan.id,
                "name": chan.name,
                "description": chan.description,
                "total_milestones": total_m,
                "completed_milestones": completed_m,
                "progress": chan_progress,
                "qualified_employees": [u.profile.display_name or u.username for u in chan.qualified_employees.all()[:3]]
            })
                
        return Response({
            'workspace_name': workspace.name,
            'total_members': total_members,
            'total_messages': total_messages,
            'sentiment': {
                'positive': positive_msg_count,
                'negative': negative_msg_count,
                'neutral': neutral_msg_count
            },
            'intents': {
                'tasks': task_msg_count,
                'questions': question_msg_count
            },
            'progress': {
                'total_tasks_assigned': total_tasks_assigned,
                'total_tasks_completed': total_tasks_completed,
                'percentage': progress
            },
            'commits': commits,
            'projects': projects_data
        })


# ── Channel Views ─────────────────────────────────────────────────────────────

class ChannelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ChannelCreateSerializer
        return ChannelSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Re-fetch the fresh channel from the DB to include updated milestones and qualified_employees
        fresh_channel = Channel.objects.get(id=serializer.instance.id)
        
        response_serializer = ChannelCreateSerializer(fresh_channel, context={'request': request})
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        workspace_id = self.kwargs.get('workspace_pk') or self.request.query_params.get('workspace')
        return Channel.objects.filter(
            workspace_id=workspace_id,
            is_archived=False
        ).filter(
            Q(channel_type='public') | Q(members=self.request.user)
        ).distinct()

    def perform_create(self, serializer):
        workspace_id = self.kwargs.get('workspace_pk') or self.request.data.get('workspace')
        
        # Superusers always have admin privileges
        if not self.request.user.is_superuser:
            try:
                member = WorkspaceMember.objects.get(workspace_id=workspace_id, user=self.request.user)
                if member.role != 'admin':
                    raise PermissionDenied("Only workspace admins can create channels.")
            except WorkspaceMember.DoesNotExist:
                raise PermissionDenied("You are not a member of this workspace.")

        is_project_channel = self.request.data.get('is_project_channel', False)
        if isinstance(is_project_channel, str):
            is_project_channel = is_project_channel.lower() == 'true'

        channel = serializer.save(
            workspace_id=workspace_id,
            created_by=self.request.user,
            is_project_channel=is_project_channel
        )
        
        channel.members.add(self.request.user)
        
        members_data = self.request.data.get('members', [])
        if members_data and isinstance(members_data, list):
            for m_id in members_data:
                channel.members.add(m_id)
        elif channel.channel_type == 'public':
            # Default behavior if no members specifically selected
            for member in WorkspaceMember.objects.filter(workspace_id=workspace_id):
                channel.members.add(member.user)

        # AI Project milestones generation & matched employees selection
        if is_project_channel:
            try:
                # 1. Gather all candidates from workspace members
                members_qs = User.objects.filter(workspacemember__workspace_id=workspace_id).select_related('profile')
                candidates = []
                for user in members_qs:
                    p = getattr(user, 'profile', None)
                    if p:
                        candidates.append({
                            "username": user.username,
                            "skills": p.skill_strength,
                            "employee_level": p.get_employee_level_display(),
                            "reliability": p.reliability,
                            "efficiency": p.efficiency
                        })
                
                # 2. Call Gemini
                from .gemini_service import generate_milestones_and_matches
                res = generate_milestones_and_matches(channel.name, channel.description, candidates)
                
                # 3. Create milestones in DB
                from .models import ChannelMilestone
                milestones_data = res.get('milestones', [])
                for m_data in milestones_data:
                    ChannelMilestone.objects.create(
                        channel=channel,
                        title=m_data.get('title'),
                        description=m_data.get('description', '')
                    )
                
                # 4. Add matched qualified employees
                matched_usernames = res.get('qualified_employees', [])
                matched_users = User.objects.filter(username__in=matched_usernames, workspacemember__workspace_id=workspace_id)
                for mu in matched_users:
                    channel.qualified_employees.add(mu)
            except Exception as e:
                print(f"Error generating AI milestones/matches: {e}")

    @action(detail=True, methods=['post'])
    def join(self, request, **kwargs):
        channel = self.get_object()
        channel.members.add(request.user)
        return Response({'message': f'Joined #{channel.name}'})

    @action(detail=True, methods=['post'], url_path='remove-member')
    def remove_member(self, request, **kwargs):
        channel = self.get_object()
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=400)
        
        is_admin = request.user.is_superuser
        if not is_admin:
            try:
                member = WorkspaceMember.objects.get(workspace=channel.workspace, user=request.user)
                if member.role == 'admin':
                    is_admin = True
            except WorkspaceMember.DoesNotExist:
                pass
        
        if not is_admin and int(user_id) != request.user.id:
            return Response({'error': 'Only admins can remove other members.'}, status=403)
            
        try:
            user_to_remove = User.objects.get(id=user_id)
            channel.members.remove(user_to_remove)
            return Response({'message': f'Removed member {user_to_remove.username}'})
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

    @action(detail=True, methods=['get'])
    def members(self, request, **kwargs):
        channel = self.get_object()
        return Response(UserSerializer(channel.members.all(), many=True).data)

    @action(detail=True, methods=['get'])
    def pins(self, request, **kwargs):
        channel = self.get_object()
        pins = PinnedMessage.objects.filter(channel=channel).select_related('message', 'pinned_by')
        return Response([{
            'message': MessageSerializer(p.message).data,
            'pinned_by': p.pinned_by.username,
            'pinned_at': p.pinned_at
        } for p in pins])

    @action(detail=True, methods=['get'])
    def summary(self, request, **kwargs):
        try:
            channel = self.get_object()
            messages = list(channel.messages.filter(
                is_deleted=False
            ).values_list('text', flat=True)[:100])
            summary = summarize_channel_activity(messages)
            return Response(summary)
        except Exception as e:
            return Response({
                'topics': [],
                'active_intents': {},
                'message_count': 0,
                'most_common_intent': 'general'
            })


# ── Message Views ─────────────────────────────────────────────────────────────

class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        channel_id = self.kwargs.get('channel_pk') or self.request.query_params.get('channel')
        dm_id = self.kwargs.get('dm_pk') or self.request.query_params.get('dm')
        parent_id = self.request.query_params.get('parent')

        qs = Message.objects.filter(is_deleted=False)

        if channel_id:
            qs = qs.filter(channel_id=channel_id, parent__isnull=True)
        elif dm_id:
            qs = qs.filter(dm_id=dm_id, parent__isnull=True)
        if parent_id:
            qs = Message.objects.filter(parent_id=parent_id, is_deleted=False)

        return qs.select_related(
            'sender', 'sender__profile'
        ).prefetch_related('reactions').order_by('created_at')

    def perform_create(self, serializer):
        try:
            channel_id = self.kwargs.get('channel_pk') or self.request.data.get('channel')
            dm_id = self.kwargs.get('dm_pk') or self.request.data.get('dm') or None
            parent_id = self.request.data.get('parent') or None
            text = self.request.data.get('text', '')

            try:
                ai_result = analyze_message(text)
            except Exception:
                ai_result = {'intent': 'general', 'sentiment': 'neutral', 'tags': []}

            save_kwargs = {
                'sender': self.request.user,
                'ai_intent': ai_result['intent'],
                'ai_sentiment': ai_result['sentiment'],
                'ai_tags': ai_result['tags'],
            }

            if channel_id:
                save_kwargs['channel_id'] = int(channel_id)
            if dm_id:
                save_kwargs['dm_id'] = int(dm_id)
            if parent_id:
                save_kwargs['parent_id'] = int(parent_id)

            msg = serializer.save(**save_kwargs)

            # Broadcast the message to Channels WebSocket group so other users see it in real-time
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                from .serializers import MessageSerializer

                channel_layer = get_channel_layer()
                room_group = f"chat_channel_{channel_id}" if channel_id else f"chat_dm_{dm_id}"
                
                msg_data = MessageSerializer(msg).data
                
                async_to_sync(channel_layer.group_send)(
                    room_group,
                    {
                        'type': 'chat_message',
                        'message': msg_data
                    }
                )
            except Exception as e:
                print(f"Error broadcasting REST API message: {e}")

            # --- AI Project Progress check ---
            if msg.channel and msg.channel.is_project_channel:
                try:
                    from .gemini_service import check_and_update_project_progress
                    check_and_update_project_progress(msg)
                except Exception as ex:
                    print(f"Milestone update check failed: {ex}")

            # --- AI Calendar Auto-Scheduler ---
            intent = ai_result.get('intent')
            if intent in ['meeting', 'task']:
                date_str = None
                for t in ai_result.get('tags', []):
                    if t.startswith('date:') or t.startswith('time:'):
                        date_str = t.split(':', 1)[1]
                        break
                if date_str:
                    from .ai_service import parse_fuzzy_date
                    from django.utils import timezone
                    dt = parse_fuzzy_date(date_str)
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                        
                    event_type = 'meeting' if intent == 'meeting' else 'deadline'
                    workspace = msg.channel.workspace if msg.channel else (msg.dm.workspace if getattr(msg, 'dm', None) else None)
                    if workspace:
                        CalendarEvent.objects.create(
                            workspace=workspace,
                            title=f"{event_type.title()}: {msg.text[:40]}",
                            description=msg.text,
                            event_type=event_type,
                            date=dt,
                            created_by=self.request.user
                        )

            # If it is directed at the AI bot, trigger the AI reply in a background thread
            from .consumers import is_ai_triggered, strip_trigger, AI_BOT_NAME, AI_BOT_COLOR
            if is_ai_triggered(text):
                import threading
                def run_ai_reply():
                    try:
                        from django.contrib.auth.models import User
                        from .models import UserProfile, Message
                        from .consumers import get_workspace_data, call_gemini
                        from channels.layers import get_channel_layer
                        from asgiref.sync import async_to_sync
                        
                        query = strip_trigger(text)
                        if not query:
                            query = "Hello! How can I help with your project?"
                            
                        # Broadcast typing indicator
                        channel_layer = get_channel_layer()
                        room_group = f"chat_channel_{channel_id}" if channel_id else f"chat_dm_{dm_id}"
                        async_to_sync(channel_layer.group_send)(
                            room_group,
                            {
                                'type': 'typing_indicator',
                                'user_id': -1,
                                'username': AI_BOT_NAME,
                                'is_typing': True,
                            }
                        )
                        
                        # Get workspace data
                        workspace = msg.channel.workspace if msg.channel else (msg.dm.workspace if getattr(msg, 'dm', None) else None)
                        workspace_id = workspace.id if workspace else None
                        ws_data = get_workspace_data(workspace_id)
                        
                        # Call Gemini
                        try:
                            file_path = msg.file.path if msg.file else None
                            ai_reply = call_gemini(query, ws_data, file_path, workspace_id)
                        except Exception as e:
                            print(f"Error in Gemini: {e}")
                            ai_reply = "⚠️ I'm having trouble connecting right now. Please try again in a moment."
                            
                        # Get or create AI user
                        ai_user, _ = User.objects.get_or_create(
                            username=AI_BOT_NAME, defaults={'is_active': False}
                        )
                        UserProfile.objects.get_or_create(
                            user=ai_user, defaults={'display_name': '🤖 PilotAI', 'avatar_color': AI_BOT_COLOR}
                        )
                        
                        # Save AI reply
                        from .ai_service import analyze_message
                        ai_res = analyze_message(ai_reply)
                        
                        ai_msg = Message.objects.create(
                            sender=ai_user,
                            channel=msg.channel,
                            dm=msg.dm,
                            text=ai_reply,
                            parent_id=None,
                            ai_intent=ai_res['intent'],
                            ai_sentiment=ai_res['sentiment'],
                            ai_tags=ai_res['tags'],
                        )
                        
                        # Stop typing indicator
                        async_to_sync(channel_layer.group_send)(
                            room_group,
                            {
                                'type': 'typing_indicator',
                                'user_id': -1,
                                'username': AI_BOT_NAME,
                                'is_typing': False,
                            }
                        )
                        
                        # Broadcast AI reply
                        from .serializers import MessageSerializer
                        ai_msg_data = MessageSerializer(ai_msg).data
                        ai_msg_data['is_ai_bot'] = True
                        
                        async_to_sync(channel_layer.group_send)(
                            room_group,
                            {
                                'type': 'chat_message',
                                'message': ai_msg_data
                            }
                        )
                    except Exception as e:
                        print(f"Error in run_ai_reply: {e}")
                        import traceback
                        traceback.print_exc()
                        
                threading.Thread(target=run_ai_reply).start()

        except Exception as e:
            print(f"perform_create error: {e}")
            import traceback
            traceback.print_exc()
            raise

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.text = "This message was deleted."
        instance.save()

    @action(detail=True, methods=['post'])
    def react(self, request, **kwargs):
        message = self.get_object()
        emoji = request.data.get('emoji')
        if not emoji:
            return Response({'error': 'emoji required'}, status=400)
        reaction, created = Reaction.objects.get_or_create(
            message=message, user=request.user, emoji=emoji
        )
        if not created:
            reaction.delete()
            return Response({'status': 'removed'})
        return Response({'status': 'added'})

    @action(detail=True, methods=['post'])
    def pin(self, request, **kwargs):
        message = self.get_object()
        if not message.channel:
            return Response({'error': 'Can only pin channel messages'}, status=400)
        PinnedMessage.objects.get_or_create(
            channel=message.channel, message=message,
            defaults={'pinned_by': request.user}
        )
        return Response({'status': 'pinned'})

    @action(detail=True, methods=['post'])
    def unpin(self, request, **kwargs):
        message = self.get_object()
        if not message.channel:
            return Response({'error': 'Can only unpin channel messages'}, status=400)
        PinnedMessage.objects.filter(
            channel=message.channel, message=message
        ).delete()
        return Response({'status': 'unpinned'})

    @action(detail=True, methods=['get'])
    def thread(self, request, **kwargs):
        message = self.get_object()
        replies = Message.objects.filter(
            parent=message, is_deleted=False
        ).order_by('created_at')
        return Response(MessageSerializer(replies, many=True).data)


# ── Direct Message Views ──────────────────────────────────────────────────────

class DirectMessageViewSet(viewsets.ModelViewSet):
    serializer_class = DirectMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        workspace_id = self.request.query_params.get('workspace')
        return DirectMessage.objects.filter(
            participants=self.request.user,
            workspace_id=workspace_id
        )

    def create(self, request):
        workspace_id = request.data.get('workspace')
        other_user_id = request.data.get('user_id')

        existing = DirectMessage.objects.filter(
            workspace_id=workspace_id,
            participants=request.user
        ).filter(participants=other_user_id)

        if existing.exists():
            dm = existing.first()
        else:
            dm = DirectMessage.objects.create(workspace_id=workspace_id)
            dm.participants.add(request.user, other_user_id)

        return Response(DirectMessageSerializer(dm).data)



# ── AI Endpoints ──────────────────────────────────────────────────────────────

@api_view(['POST'])
def ai_analyze(request):
    text = request.data.get('text', '')
    if not text:
        return Response({'error': 'text required'}, status=400)
    result = analyze_message(text)
    return Response(result)


@api_view(['GET'])
def ai_search(request):
    query = request.query_params.get('q', '')
    workspace_id = request.query_params.get('workspace')
    if not query or not workspace_id:
        return Response({'error': 'q and workspace params required'}, status=400)

    messages = Message.objects.filter(
        channel__workspace_id=workspace_id,
        is_deleted=False
    ).select_related('sender', 'channel')[:500]

    messages_data = MessageSerializer(messages, many=True).data
    results = smart_search(query, [dict(m) for m in messages_data])
    return Response(results[:20])

class CalendarEventViewSet(viewsets.ModelViewSet):
    serializer_class = CalendarEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        workspace_id = self.kwargs.get('workspace_pk') or self.request.query_params.get('workspace')
        return CalendarEvent.objects.filter(workspace_id=workspace_id)

    def perform_create(self, serializer):
        workspace_id = self.kwargs.get('workspace_pk') or self.request.data.get('workspace')
        serializer.save(created_by=self.request.user, workspace_id=workspace_id)


# ── GitHub Integration ────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def github_project(request):
    """
    GET /api/github/report/?workspace=<id>
    Returns project report for the GitHub repo linked to the workspace.
    """
    workspace_id = request.query_params.get('workspace')
    if not workspace_id:
        return Response({'error': 'workspace param required'}, status=400)
    try:
        workspace = Workspace.objects.get(id=workspace_id)
    except Workspace.DoesNotExist:
        return Response({'error': 'Workspace not found'}, status=404)

    if not workspace.github_repo:
        return Response({'error': 'No GitHub repo linked to this workspace. An admin must link one first.'}, status=404)

    report = build_project_report(workspace.github_repo)
    if 'error' in report:
        return Response(report, status=502)  # Bad Gateway — upstream GitHub API failed
    return Response(report)

# ── Gemini API Integration ───────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_ai_assign_task(request):
    """
    POST /api/ai/assign-task/
    Input: {"task_description": "...", "workspace_id": 1}
    """
    task_desc = request.data.get('task_description')
    workspace_id = request.data.get('workspace_id')
    
    if not task_desc or not workspace_id:
        return Response({'error': 'task_description and workspace_id required'}, status=400)
        
    try:
        workspace = Workspace.objects.get(id=workspace_id)
    except Workspace.DoesNotExist:
        return Response({'error': 'Workspace not found'}, status=404)
        
    # Get candidates (members of workspace)
    members = User.objects.filter(workspacemember__workspace=workspace).select_related('profile')
    
    candidates = []
    for user in members:
        p = user.profile
        candidates.append({
            "username": user.username,
            "skills": p.skill_strength,
            "employee_level": p.get_employee_level_display(),
            "status": p.get_status_display(),
            "status_message": p.status_text,
            "efficiency": p.efficiency,
            "reliability": p.reliability,
            "tasks_assigned": p.tasks_assigned,
            "tasks_completed": p.tasks_completed,
            "avg_time_per_task": p.avg_time_per_task
        })
        
    # Ask Gemini
    result = recommend_task_assignment(task_desc, candidates)
    assigned_username = result.get('assigned_to')
    
    if not assigned_username:
        return Response({'error': 'Could not assign task', 'reason': result.get('reason')}, status=500)
        
    # Validate against our database
    try:
        assigned_user = User.objects.get(username=assigned_username, workspacemember__workspace=workspace)
    except User.DoesNotExist:
        return Response({'error': f"Gemini suggested an invalid user: {assigned_username}"}, status=400)
        
    # Execute action
    # 1. Update Profile
    profile = assigned_user.profile
    profile.tasks_assigned += 1
    profile.save()
    
    # 2. Create CalendarEvent
    from django.utils import timezone
    dt = timezone.now() + timezone.timedelta(days=7) # arbitrary deadline
    CalendarEvent.objects.create(
        workspace=workspace,
        title=f"Task: {task_desc[:40]}",
        description=task_desc,
        event_type="deadline",
        date=dt,
        created_by=request.user
    )
    
    return Response({
        'message': f"Task assigned to {assigned_username}",
        'assigned_to': assigned_username,
        'reason': result.get('reason'),
        'profile_stats': {
            'tasks_assigned': profile.tasks_assigned,
            'efficiency': profile.efficiency
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_ai_project_insights(request):
    """
    GET /api/ai/project-insights/?workspace=<id>
    """
    workspace_id = request.query_params.get('workspace')
    if not workspace_id:
        return Response({'error': 'workspace param required'}, status=400)
        
    # Gather data
    members = UserProfile.objects.filter(user__workspacemember__workspace_id=workspace_id)
    events = CalendarEvent.objects.filter(workspace_id=workspace_id).order_by('-date')[:10]
    
    progress_data = {
        "team_metrics": [
            {
                "username": p.user.username,
                "skills": p.skill_strength,
                "employee_level": p.get_employee_level_display(),
                "status": p.get_status_display(),
                "status_message": p.status_text,
                "efficiency": p.efficiency,
                "reliability": p.reliability,
                "tasks_assigned": p.tasks_assigned,
                "tasks_completed": p.tasks_completed,
            } for p in members
        ],
        "recent_events": [
            {
                "title": e.title,
                "type": e.event_type,
                "date": str(e.date)
            } for e in events
        ]
    }
    
    insights = provide_project_insights(progress_data)
    return Response({"insights": insights})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_ai_detect_risks(request):
    """
    GET /api/ai/detect-risks/?workspace=<id>
    """
    workspace_id = request.query_params.get('workspace')
    if not workspace_id:
        return Response({'error': 'workspace param required'}, status=400)
        
    # Gather data
    members = UserProfile.objects.filter(user__workspacemember__workspace_id=workspace_id)
    
    project_data = {
        "team_workload": [
            {
                "username": p.user.username,
                "skills": p.skill_strength,
                "employee_level": p.get_employee_level_display(),
                "status": p.get_status_display(),
                "status_message": p.status_text,
                "pending_tasks": p.tasks_assigned - p.tasks_completed,
                "efficiency": p.efficiency,
                "reliability": p.reliability
            } for p in members
        ]
    }
    
    risks = detect_risks(project_data)
    return Response({"risks": risks})


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().prefetch_related('project_milestones', 'members', 'tasks')
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'], url_path='task-recommendation')
    def task_recommendation(self, request, pk=None):
        project = self.get_object()
        task_desc = request.data.get('task_description')
        if not task_desc:
            return Response({'error': 'task_description is required'}, status=400)
        recommendation = get_task_recommendation(project, task_desc)
        return Response({'recommendation': recommendation})

    @action(detail=True, methods=['post'], url_path='sprint-planning')
    def sprint_planning(self, request, pk=None):
        project = self.get_object()
        sprint_goal = request.data.get('sprint_goal')
        if not sprint_goal:
            return Response({'error': 'sprint_goal is required'}, status=400)
        planning = run_sprint_planning(project, sprint_goal)
        return Response({'sprint_planning': planning})

    @action(detail=True, methods=['get'], url_path='risk-analysis')
    def risk_analysis(self, request, pk=None):
        project = self.get_object()
        analysis = run_risk_analysis(project)
        return Response({'risk_analysis': analysis})

    @action(detail=True, methods=['get'], url_path='workload-balancing')
    def workload_balancing(self, request, pk=None):
        project = self.get_object()
        balancing = run_workload_balancing(project)
        return Response({'workload_balancing': balancing})

    @action(detail=True, methods=['get'], url_path='skill-analysis')
    def skill_analysis(self, request, pk=None):
        project = self.get_object()
        analysis = run_member_skill_analysis(project)
        return Response({'skill_analysis': analysis})


class MilestoneViewSet(viewsets.ModelViewSet):
    queryset = Milestone.objects.all()
    serializer_class = MilestoneSerializer
    permission_classes = [IsAuthenticated]


class MemberViewSet(viewsets.ModelViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated]


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]


class AIMemoryViewSet(viewsets.ModelViewSet):
    queryset = AIMemory.objects.all()
    serializer_class = AIMemorySerializer
    permission_classes = [IsAuthenticated]


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ai_voice_chat(request):
    """
    POST /api/ai-chat/
    Receive voice-to-text chat message, query Gemini AI, and optionally save/broadcast both.
    """
    message_text = request.data.get('message', '').strip()
    room_id = request.data.get('room_id')  # e.g., "channel_1" or "dm_2"
    
    if not message_text:
        return Response({'error': 'message is required'}, status=400)

    # 1. Clean trigger words if present
    from .consumers import is_ai_triggered, strip_trigger
    query = strip_trigger(message_text) if is_ai_triggered(message_text) else message_text
    
    # 2. Get Workspace & Project context for PilotAI if room_id is specified
    project = None
    workspace_id = None
    channel_obj = None
    dm_obj = None
    
    if room_id:
        if room_id.startswith('channel_'):
            try:
                ch_id = int(room_id.replace('channel_', ''))
                from .models import Channel
                channel_obj = Channel.objects.get(id=ch_id)
                workspace_id = channel_obj.workspace_id
                # Check if channel is an AI project channel
                if channel_obj.is_project_channel:
                    from .models import Project
                    project = Project.objects.filter(workspace_id=workspace_id).first()
            except Exception:
                pass
        elif room_id.startswith('dm_'):
            try:
                dm_id = int(room_id.replace('dm_', ''))
                from .models import DirectMessage
                dm_obj = DirectMessage.objects.get(id=dm_id)
                workspace_id = dm_obj.workspace_id
            except Exception:
                pass

    # 3. Call PilotAI (Gemini) in CTO persona
    from .pilot_ai_core import AIServiceLayer
    try:
        ai_reply = AIServiceLayer.call_pilot_ai(query=query, project=project, workspace_id=workspace_id)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error calling PilotAI in voice chat endpoint: {e}")
        ai_reply = "Decision:\nSpiderman should coordinate next steps.\nReason:\nPilotAI encountered a voice chat error.\nRisk:\nDelayed response until connection is restored."

    # 4. If room_id is provided, save user message and AI response in DB and broadcast to WebSocket
    if room_id:
        try:
            # Save user message
            from .ai_service import analyze_message
            try:
                ai_result = analyze_message(message_text)
            except Exception:
                ai_result = {'intent': 'general', 'sentiment': 'neutral', 'tags': []}
                
            from .models import Message
            user_msg = Message.objects.create(
                sender=request.user,
                text=message_text,
                channel=channel_obj,
                dm=dm_obj,
                ai_intent=ai_result.get('intent', 'general'),
                ai_sentiment=ai_result.get('sentiment', 'neutral'),
                ai_tags=ai_result.get('tags', []),
            )
            
            # Broadcast user message
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            from .serializers import MessageSerializer
            
            channel_layer = get_channel_layer()
            room_group = f"chat_{room_id}"
            
            user_msg_data = MessageSerializer(user_msg).data
            async_to_sync(channel_layer.group_send)(
                room_group,
                {
                    'type': 'chat_message',
                    'message': user_msg_data
                }
            )

            # Get or create AI user
            ai_user, _ = User.objects.get_or_create(username='PilotAI', defaults={'is_active': False})
            from .models import UserProfile
            UserProfile.objects.get_or_create(
                user=ai_user, 
                defaults={'display_name': '🤖 PilotAI', 'avatar_color': '#7C3AED'}
            )
            
            # Save AI response
            try:
                ai_resp_result = analyze_message(ai_reply)
            except Exception:
                ai_resp_result = {'intent': 'general', 'sentiment': 'neutral', 'tags': []}
                
            ai_msg = Message.objects.create(
                sender=ai_user,
                text=ai_reply,
                channel=channel_obj,
                dm=dm_obj,
                ai_intent=ai_resp_result.get('intent', 'general'),
                ai_sentiment=ai_resp_result.get('sentiment', 'neutral'),
                ai_tags=ai_resp_result.get('tags', []),
            )
            
            # Broadcast AI message
            ai_msg_data = MessageSerializer(ai_msg).data
            ai_msg_data['is_ai_bot'] = True
            async_to_sync(channel_layer.group_send)(
                room_group,
                {
                    'type': 'chat_message',
                    'message': ai_msg_data
                }
            )
            
            # --- AI Project Progress check for user message ---
            if user_msg.channel and user_msg.channel.is_project_channel:
                try:
                    from .gemini_service import check_and_update_project_progress
                    check_and_update_project_progress(user_msg)
                except Exception as ex:
                    print(f"Milestone update check failed: {ex}")
                    
        except Exception as e:
            print(f"Error handling room message saving/broadcast: {e}")

    return Response({
        'message': message_text,
        'response': ai_reply
    })