from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import generics, status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .models import (
    Workspace, WorkspaceMember, Channel, DirectMessage,
    Message, Reaction, UserProfile, PinnedMessage
)
from .serializers import (
    UserSerializer, UserRegisterSerializer, WorkspaceSerializer,
    ChannelSerializer, ChannelCreateSerializer, DirectMessageSerializer,
    MessageSerializer, ReactionSerializer, WorkspaceMemberSerializer
)
from .ai_service import analyze_message, smart_search, summarize_channel_activity


# ─── Auth Views ───────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = UserRegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
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
        # Set user status to active
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.status = 'active'
        profile.save()
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data
        })
    return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
def logout_view(request):
    # Set status to offline
    try:
        request.user.profile.status = 'offline'
        request.user.profile.save()
    except Exception:
        pass
    request.user.auth_token.delete()
    return Response({'message': 'Logged out successfully'})


@api_view(['GET', 'PUT'])
def me(request):
    if request.method == 'GET':
        return Response(UserSerializer(request.user).data)
    # PUT: update profile
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    data = request.data
    profile.display_name = data.get('display_name', profile.display_name)
    profile.bio = data.get('bio', profile.bio)
    profile.status = data.get('status', profile.status)
    profile.status_emoji = data.get('status_emoji', profile.status_emoji)
    profile.status_text = data.get('status_text', profile.status_text)
    profile.avatar_color = data.get('avatar_color', profile.avatar_color)
    profile.save()
    return Response(UserSerializer(request.user).data)


# ─── Workspace Views ──────────────────────────────────────────────────────────

class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.request.user.workspaces.all()

    def perform_create(self, serializer):
        workspace = serializer.save(created_by=self.request.user)
        # Creator becomes admin member
        WorkspaceMember.objects.create(workspace=workspace, user=self.request.user, role='admin')
        # Auto-create default channels
        for ch_name, desc in [
            ('general', 'Company-wide announcements'),
            ('random', 'Non-work banter and fun'),
        ]:
            channel = Channel.objects.create(
                workspace=workspace, name=ch_name, description=desc,
                channel_type='public', created_by=self.request.user
            )
            channel.members.add(self.request.user)

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        workspace = self.get_object()
        WorkspaceMember.objects.get_or_create(workspace=workspace, user=request.user, defaults={'role': 'member'})
        return Response({'message': 'Joined workspace'})

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        workspace = self.get_object()
        members = WorkspaceMember.objects.filter(workspace=workspace).select_related('user', 'user__profile')
        return Response(WorkspaceMemberSerializer(members, many=True).data)


# ─── Channel Views ────────────────────────────────────────────────────────────

class ChannelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ChannelCreateSerializer
        return ChannelSerializer

    def get_queryset(self):
        workspace_id = self.kwargs.get('workspace_pk') or self.request.query_params.get('workspace')
        qs = Channel.objects.filter(workspace_id=workspace_id, is_archived=False)
        # Show public channels + private channels user is member of
        return qs.filter(
            Q(channel_type='public') | Q(members=self.request.user)
        ).distinct()

    def perform_create(self, serializer):
        workspace_id = self.kwargs.get('workspace_pk') or self.request.data.get('workspace')
        channel = serializer.save(
            workspace_id=workspace_id,
            created_by=self.request.user
        )
        channel.members.add(self.request.user)

    @action(detail=True, methods=['post'])
    def join(self, request, **kwargs):
        channel = self.get_object()
        channel.members.add(request.user)
        return Response({'message': f'Joined #{channel.name}'})

    @action(detail=True, methods=['post'])
    def leave(self, request, **kwargs):
        channel = self.get_object()
        channel.members.remove(request.user)
        return Response({'message': f'Left #{channel.name}'})

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
        """AI-powered channel activity summary using spaCy."""
        channel = self.get_object()
        messages = list(channel.messages.filter(is_deleted=False).values_list('text', flat=True)[:100])
        summary = summarize_channel_activity(messages)
        return Response(summary)


# ─── Message Views ────────────────────────────────────────────────────────────

class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        channel_id = self.kwargs.get('channel_pk') or self.request.query_params.get('channel')
        dm_id = self.request.query_params.get('dm')
        parent_id = self.request.query_params.get('parent')  # for threads

        qs = Message.objects.filter(is_deleted=False)

        if channel_id:
            qs = qs.filter(channel_id=channel_id, parent__isnull=True)
        elif dm_id:
            qs = qs.filter(dm_id=dm_id, parent__isnull=True)
        if parent_id:
            qs = Message.objects.filter(parent_id=parent_id, is_deleted=False)

        return qs.select_related('sender', 'sender__profile').prefetch_related('reactions').order_by('created_at')

    def perform_create(self, serializer):
        channel_id = self.kwargs.get('channel_pk') or self.request.data.get('channel')
        dm_id = self.request.data.get('dm')
        parent_id = self.request.data.get('parent')
        text = self.request.data.get('text', '')

        # Run AI analysis
        ai_result = analyze_message(text)

        msg = serializer.save(
            sender=self.request.user,
            channel_id=channel_id,
            dm_id=dm_id,
            parent_id=parent_id,
            ai_intent=ai_result['intent'],
            ai_sentiment=ai_result['sentiment'],
            ai_tags=ai_result['tags'],
        )
        return msg

    def perform_update(self, serializer):
        instance = serializer.save(is_edited=True)
        # Re-analyze on edit
        ai_result = analyze_message(instance.text)
        instance.ai_intent = ai_result['intent']
        instance.ai_sentiment = ai_result['sentiment']
        instance.ai_tags = ai_result['tags']
        instance.save()

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.text = "This message was deleted."
        instance.save()

    @action(detail=False, methods=['get'])
    def search(self, request):
        """AI-powered search using spaCy."""
        query = request.query_params.get('q', '')
        channel_id = request.query_params.get('channel')
        workspace_id = request.query_params.get('workspace')

        if not query:
            return Response([])

        qs = Message.objects.filter(is_deleted=False)
        if channel_id:
            qs = qs.filter(channel_id=channel_id)
        elif workspace_id:
            qs = qs.filter(channel__workspace_id=workspace_id)

        messages_data = MessageSerializer(qs[:500], many=True).data
        results = smart_search(query, [dict(m) for m in messages_data])
        return Response(results[:20])

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

    @action(detail=True, methods=['get'])
    def thread(self, request, **kwargs):
        message = self.get_object()
        replies = Message.objects.filter(parent=message, is_deleted=False).order_by('created_at')
        return Response(MessageSerializer(replies, many=True).data)


# ─── Direct Message Views ─────────────────────────────────────────────────────

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

        # Find or create DM
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

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        dm = self.get_object()
        msgs = Message.objects.filter(dm=dm, is_deleted=False).order_by('created_at')
        return Response(MessageSerializer(msgs, many=True).data)


# ─── AI Endpoints ─────────────────────────────────────────────────────────────

@api_view(['POST'])
def ai_analyze(request):
    """Analyze a message text and return AI insights."""
    text = request.data.get('text', '')
    if not text:
        return Response({'error': 'text required'}, status=400)
    result = analyze_message(text)
    return Response(result)


@api_view(['GET'])
def ai_search(request):
    """Smart search across messages in a workspace."""
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
