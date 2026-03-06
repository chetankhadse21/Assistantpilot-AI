"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from slack_app.views import (
    register, login_view, logout_view, me,
    WorkspaceViewSet, ChannelViewSet, MessageViewSet,
    DirectMessageViewSet, ai_analyze, ai_search
)

router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')
router.register(r'workspaces/(?P<workspace_pk>[^/.]+)/channels', ChannelViewSet, basename='channel')
router.register(r'workspaces/(?P<workspace_pk>[^/.]+)/messages', MessageViewSet, basename='message')
router.register(r'channels/(?P<channel_pk>[^/.]+)/messages', MessageViewSet, basename='channel-message')
router.register(r'dms', DirectMessageViewSet, basename='dm')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/register/', register),
    path('api/auth/login/', login_view),
    path('api/auth/logout/', logout_view),
    path('api/auth/me/', me),
    path('api/ai/analyze/', ai_analyze),
    path('api/ai/search/', ai_search),
    path('api/', include(router.urls)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

