from django.db import models
from django.contrib.auth.models import User


class Workspace(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workspaces_created')
    members = models.ManyToManyField(User, related_name='workspaces', through='WorkspaceMember')
    created_at = models.DateTimeField(auto_now_add=True)
    icon = models.CharField(max_length=10, default='💬')

    def __str__(self):
        return self.name


class WorkspaceMember(models.Model):
    ROLE_CHOICES = [('admin', 'Admin'), ('member', 'Member'), ('guest', 'Guest')]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('workspace', 'user')


class Channel(models.Model):
    TYPE_CHOICES = [('public', 'Public'), ('private', 'Private')]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='channels')
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    channel_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='public')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='channels_created')
    members = models.ManyToManyField(User, related_name='channels', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        unique_together = ('workspace', 'name')

    def __str__(self):
        return f"#{self.name}"


class DirectMessage(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='dms')
    participants = models.ManyToManyField(User, related_name='direct_messages')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"DM: {', '.join(u.username for u in self.participants.all())}"


class Message(models.Model):
    # Message can belong to a channel or a DM
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    dm = models.ForeignKey(DirectMessage, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    text = models.TextField()
    file = models.FileField(upload_to='message_files/', null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='thread_replies')
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # AI-generated fields
    ai_tags = models.JSONField(default=list, blank=True)       # spaCy extracted entities/keywords
    ai_intent = models.CharField(max_length=50, blank=True)    # question, announcement, task, etc.
    ai_sentiment = models.CharField(max_length=20, blank=True) # positive, negative, neutral

    def __str__(self):
        return f"{self.sender.username}: {self.text[:50]}"


class Reaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user', 'emoji')


class UserProfile(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('away', 'Away'),
        ('dnd', 'Do Not Disturb'),
        ('offline', 'Offline'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=80, blank=True)
    bio = models.TextField(blank=True)
    avatar_color = models.CharField(max_length=7, default='#4A154B')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    status_emoji = models.CharField(max_length=10, blank=True)
    status_text = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')

    def __str__(self):
        return f"Profile of {self.user.username}"


class PinnedMessage(models.Model):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='pinned_messages')
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    pinned_by = models.ForeignKey(User, on_delete=models.CASCADE)
    pinned_at = models.DateTimeField(auto_now_add=True)
