from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Workspace, WorkspaceMember, Channel, DirectMessage,
    Message, Reaction, UserProfile, PinnedMessage
)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['display_name', 'bio', 'avatar_color', 'status',
                  'status_emoji', 'status_text', 'timezone']


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

    def get_reply_count(self, obj):
        return obj.thread_replies.count()

    def get_channel_name(self, obj):
        if obj.channel:
            return obj.channel.name
        return None


class ChannelSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    member_count = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Channel
        fields = [
            'id', 'name', 'description', 'channel_type', 'created_by',
            'created_at', 'is_archived', 'member_count', 'unread_count'
        ]

    def get_member_count(self, obj):
        return obj.members.count()

    def get_unread_count(self, obj):
        return 0  # Implement with read receipts if needed


class ChannelCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = ['name', 'description', 'channel_type']


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

    class Meta:
        model = Workspace
        fields = ['id', 'name', 'description', 'icon', 'created_by', 'created_at', 'member_count']

    def get_member_count(self, obj):
        return obj.members.count()
