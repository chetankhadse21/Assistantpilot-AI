from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Workspace, WorkspaceMember, Channel, DirectMessage,
    Message, Reaction, UserProfile, PinnedMessage, CalendarEvent,
    ChannelMilestone, Project, Milestone, Member, Task, AIMemory
)


class UserProfileSerializer(serializers.ModelSerializer):
    efficiency = serializers.ReadOnlyField()
    reliability = serializers.ReadOnlyField()

    class Meta:
        model = UserProfile
        fields = [
            'display_name', 'bio', 'avatar_color', 'status',
            'status_emoji', 'status_text', 'timezone',
            'employee_level', 'tasks_assigned', 'tasks_completed',
            'avg_time_per_task', 'deadlines_met', 'skill_strength',
            'efficiency', 'reliability'
        ]


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile', 'display_name']

    def get_display_name(self, obj):
        try:
            return obj.profile.display_name or obj.username
        except UserProfile.DoesNotExist:
            return obj.username


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    display_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'display_name']

    def create(self, validated_data):
        display_name = validated_data.pop('display_name', '')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
        )
        UserProfile.objects.create(user=user, display_name=display_name or user.username)
        return user


class ReactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Reaction
        fields = ['id', 'emoji', 'user', 'created_at']


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    reactions = ReactionSerializer(many=True, read_only=True)
    reply_count = serializers.SerializerMethodField()
    channel_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'sender', 'text', 'file', 'parent', 'is_edited', 'is_deleted',
            'created_at', 'updated_at', 'reactions', 'reply_count',
            'ai_tags', 'ai_intent', 'ai_sentiment', 'channel_name'
        ]
        extra_kwargs = {
            'text': {'required': False, 'allow_blank': True}
        }

    def get_reply_count(self, obj):
        return obj.thread_replies.count()

    def get_channel_name(self, obj):
        if obj.channel:
            return obj.channel.name
        return None


class ChannelMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChannelMilestone
        fields = ['id', 'title', 'description', 'is_completed', 'completed_at', 'created_at']


class ChannelSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    member_count = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    milestones = ChannelMilestoneSerializer(many=True, read_only=True)
    qualified_employees = UserSerializer(many=True, read_only=True)

    class Meta:
        model = Channel
        fields = [
            'id', 'name', 'description', 'notes', 'channel_type', 'created_by',
            'created_at', 'is_archived', 'member_count', 'unread_count',
            'is_project_channel', 'milestones', 'qualified_employees'
        ]

    def get_member_count(self, obj):
        return obj.members.count()

    def get_unread_count(self, obj):
        return 0  # Implement with read receipts if needed


class ChannelCreateSerializer(serializers.ModelSerializer):
    milestones = ChannelMilestoneSerializer(many=True, read_only=True)
    qualified_employees = UserSerializer(many=True, read_only=True)

    class Meta:
        model = Channel
        fields = ['id', 'name', 'description', 'notes', 'channel_type', 'is_project_channel', 'milestones', 'qualified_employees']
        read_only_fields = ['id', 'milestones', 'qualified_employees']


class DirectMessageSerializer(serializers.ModelSerializer):
    participants = UserSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = DirectMessage
        fields = ['id', 'participants', 'created_at', 'last_message']

    def get_last_message(self, obj):
        msg = obj.messages.filter(is_deleted=False).order_by('-created_at').first()
        if msg:
            return {'text': msg.text, 'sender': msg.sender.username, 'created_at': msg.created_at}
        return None


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = WorkspaceMember
        fields = ['user', 'role', 'joined_at']


class WorkspaceSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    member_count = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ['id', 'name', 'description', 'icon', 'github_repo', 'created_by', 'created_at', 'member_count', 'my_role']

    def get_member_count(self, obj):
        return obj.members.count()

    def get_my_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if request.user.is_superuser:
                return 'admin'
            try:
                member = WorkspaceMember.objects.get(workspace=obj, user=request.user)
                return member.role
            except WorkspaceMember.DoesNotExist:
                return 'none'
        return 'none'

class CalendarEventSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    google_calendar_url = serializers.SerializerMethodField()

    class Meta:
        model = CalendarEvent
        fields = ['id', 'workspace', 'title', 'description', 'event_type', 'date', 'created_by', 'created_at', 'google_calendar_url']
        read_only_fields = ['workspace', 'created_by']

    def get_google_calendar_url(self, obj):
        import urllib.parse
        from django.utils import timezone
        import datetime

        # Format date as YYYYMMDDTHHMMSSZ for ICS / Google Calendar
        dt_start = obj.date.astimezone(datetime.timezone.utc)
        # Default duration 1 hour
        dt_end = dt_start + datetime.timedelta(hours=1)

        def format_date(dt):
            return dt.strftime('%Y%m%dT%H%M%SZ')

        start_str = format_date(dt_start)
        end_str = format_date(dt_end)

        base_url = "https://calendar.google.com/calendar/render?action=TEMPLATE"
        params = {
            'text': obj.title,
            'dates': f"{start_str}/{end_str}",
            'details': obj.description,
        }
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}&{query_string}"


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = '__all__'


class MemberSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)

    class Meta:
        model = Member
        fields = ['id', 'project', 'user', 'user_detail', 'role', 'skills', 'availability', 'workload', 'specialization', 'created_at']


class TaskSerializer(serializers.ModelSerializer):
    assigned_to_detail = UserSerializer(source='assigned_to', read_only=True)
    project_name = serializers.ReadOnlyField(source='project.name')
    milestone_title = serializers.ReadOnlyField(source='milestone.title')

    class Meta:
        model = Task
        fields = [
            'id', 'project', 'project_name', 'milestone', 'milestone_title',
            'title', 'description', 'assigned_to', 'assigned_to_detail',
            'status', 'priority', 'due_date', 'completed_at', 'created_at', 'updated_at'
        ]


class AIMemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMemory
        fields = '__all__'


class ProjectSerializer(serializers.ModelSerializer):
    workspace_name = serializers.ReadOnlyField(source='workspace.name')
    project_milestones = MilestoneSerializer(many=True, read_only=True)
    members = MemberSerializer(many=True, read_only=True)
    tasks = TaskSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            'id', 'workspace', 'workspace_name', 'name', 'description', 'status',
            'start_date', 'end_date', 'created_at', 'updated_at',
            'project_milestones', 'members', 'tasks'
        ]
