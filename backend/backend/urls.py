from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from slack_app.views import (
    register, login_view, logout_view, me,
    WorkspaceViewSet, ChannelViewSet, MessageViewSet,
    DirectMessageViewSet, ai_analyze, ai_search,
    join_all_workspaces, all_users, CalendarEventViewSet, github_project,
    api_ai_assign_task, api_ai_project_insights, api_ai_detect_risks,
    ProjectViewSet, MilestoneViewSet, MemberViewSet, TaskViewSet, AIMemoryViewSet,
    ai_voice_chat
)

router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')
router.register(r'workspaces/(?P<workspace_pk>[^/.]+)/channels', ChannelViewSet, basename='channel')
router.register(r'workspaces/(?P<workspace_pk>[^/.]+)/events', CalendarEventViewSet, basename='calendar-event')
router.register(r'channels/(?P<channel_pk>[^/.]+)/messages', MessageViewSet, basename='channel-message')
router.register(r'dms/(?P<dm_pk>[^/.]+)/messages', MessageViewSet, basename='dm-message')
router.register(r'dms', DirectMessageViewSet, basename='dm')
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'project-milestones', MilestoneViewSet, basename='project-milestone')
router.register(r'project-members', MemberViewSet, basename='project-member')
router.register(r'project-tasks', TaskViewSet, basename='project-task')
router.register(r'ai-memories', AIMemoryViewSet, basename='ai-memory')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/register/', register),
    path('api/auth/login/', login_view),
    path('api/auth/logout/', logout_view),
    path('api/auth/me/', me),
    path('api/ai/analyze/', ai_analyze),
    path('api/ai/search/', ai_search),
    path('api/ai/assign-task/', api_ai_assign_task),
    path('api/ai/project-insights/', api_ai_project_insights),
    path('api/ai/detect-risks/', api_ai_detect_risks),
    path('api/ai-chat/', ai_voice_chat),
    path('api/github/report/', github_project),
    path('api/join-all/', join_all_workspaces),
    path('api/users/', all_users),
    path('api/', include(router.urls)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)