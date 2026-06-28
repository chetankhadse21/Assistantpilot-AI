from django.db import models
from django.contrib.auth.models import User


class Workspace(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workspaces_created')
    members = models.ManyToManyField(User, related_name='workspaces', through='WorkspaceMember')
    created_at = models.DateTimeField(auto_now_add=True)
    icon = models.CharField(max_length=10, default='💬')
    github_repo = models.CharField(max_length=200, blank=True, help_text="Format: owner/repo-name")

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
    notes = models.TextField(blank=True)
    channel_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='public')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='channels_created')
    members = models.ManyToManyField(User, related_name='channels', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_archived = models.BooleanField(default=False)
    
    # AI Project Fields
    is_project_channel = models.BooleanField(default=False)
    qualified_employees = models.ManyToManyField(User, related_name='qualified_channels', blank=True)

    class Meta:
        unique_together = ('workspace', 'name')

    def __str__(self):
        return f"#{self.name}"


class ChannelMilestone(models.Model):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.channel.name} - {self.title} ({'Done' if self.is_completed else 'Pending'})"


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
    text = models.TextField(blank=True, default='')
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
    EMPLOYEE_LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('professional', 'Professional'),
        ('expert', 'Expert'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=80, blank=True)
    bio = models.TextField(blank=True)
    avatar_color = models.CharField(max_length=7, default='#4A154B')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    status_emoji = models.CharField(max_length=10, blank=True)
    status_text = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')
    
    # HR & Performance Fields
    employee_level = models.CharField(max_length=20, choices=EMPLOYEE_LEVEL_CHOICES, default='beginner')
    tasks_assigned = models.PositiveIntegerField(default=0)
    tasks_completed = models.PositiveIntegerField(default=0)
    avg_time_per_task = models.FloatField(default=0.0, help_text="Avg time taken per task in hours")
    deadlines_met = models.PositiveIntegerField(default=0)
    skill_strength = models.CharField(max_length=100, blank=True, help_text="Most frequent task type")

    @property
    def efficiency(self):
        if self.tasks_assigned > 0:
            return round((self.tasks_completed / self.tasks_assigned) * 100, 2)
        return 0.0

    @property
    def reliability(self):
        total_tasks = self.tasks_completed if self.tasks_completed > 0 else self.tasks_assigned
        if total_tasks > 0:
            return round((self.deadlines_met / total_tasks) * 100, 2)
        return 0.0

    def __str__(self):
        return f"Profile of {self.user.username}"


class PinnedMessage(models.Model):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='pinned_messages')
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    pinned_by = models.ForeignKey(User, on_delete=models.CASCADE)
    pinned_at = models.DateTimeField(auto_now_add=True)

class CalendarEvent(models.Model):
    EVENT_CHOICES = [
        ('meeting', 'Meeting'),
        ('deadline', 'Deadline'),
        ('general', 'General'),
    ]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES, default='general')
    date = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_events')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type.title()}: {self.title} on {self.date}"


class Project(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
    ]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='project_milestones')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.name} - {self.title}"


class Member(models.Model):
    ROLE_CHOICES = [
        ('lead', 'Project Lead'),
        ('developer', 'Developer'),
        ('designer', 'Designer'),
        ('qa', 'QA Engineer'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='developer')
    skills = models.JSONField(default=list, blank=True, help_text="List of skills e.g., ['React', 'Python', 'Django']")
    availability = models.BooleanField(default=True)
    workload = models.IntegerField(default=0, help_text="Number of active tasks assigned")
    specialization = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('project', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.project.name} ({self.role})"


class Task(models.Model):
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('blocked', 'Blocked'),
        ('completed', 'Completed'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    milestone = models.ForeignKey(Milestone, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.status})"


class AIMemory(models.Model):
    MEMORY_TYPE_CHOICES = [
        ('blocker', 'Blocker'),
        ('decision', 'Decision'),
        ('general', 'General'),
        ('preference', 'Preference'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='ai_memories')
    key = models.CharField(max_length=100)
    value = models.JSONField(default=dict)
    memory_type = models.CharField(max_length=20, choices=MEMORY_TYPE_CHOICES, default='general')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('project', 'key')

    def __str__(self):
        return f"{self.project.name} memory: {self.key}"
