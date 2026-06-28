import os
import json
import logging
from django.conf import settings
from django.contrib.auth.models import User
import google.generativeai as genai
from .models import Project, Task, Member, Milestone, AIMemory, Message

logger = logging.getLogger(__name__)

# Configure Gemini
api_key = getattr(settings, 'GEMINI_API_KEY', None)
if api_key:
    genai.configure(api_key=api_key)
else:
    logger.warning("GEMINI_API_KEY not found in settings.")

MODEL_NAME = "gemini-flash-latest"

SYSTEM_INSTRUCTION = (
    "You are PilotAI, an advanced technical project leader.\n"
    "You manage teams, assign tasks, analyze risks, prioritize execution, and guide software development professionally."
)

REQUIRED_FORMAT = (
    "Your response MUST strictly use the following header sections exactly as written, with no extra intro/outro text outside this format:\n\n"
    "ANALYSIS:\n"
    "[Provide a deep context-aware analysis of the team workload, milestones, code patterns, and request details]\n\n"
    "TASK ASSIGNMENT:\n"
    "[Specifically name the assigned individuals and describe their tasks. E.g., 'Ashwini should handle frontend calculator UI because of React experience. Snehal can support with UI refinement.']\n\n"
    "REASON:\n"
    "[Clear engineering justification highlighting member skills, availability, current workloads, and past performances]\n\n"
    "RISKS:\n"
    "[Highlight critical blockers, team overload issues, near-miss deadlines, or skill-gaps]\n\n"
    "NEXT ACTIONS:\n"
    "[Bullet list of concrete, next-step recommendations for team members]"
)


def get_gemini_model():
    """Returns GenerativeModel with permanent system prompt."""
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_INSTRUCTION
    )


def build_ai_context(project: Project, recent_messages_limit: int = 15) -> dict:
    """
    Gathers comprehensive context details for the current Project.
    """
    # 1. Project details
    proj_info = {
        "name": project.name,
        "description": project.description,
        "status": project.get_status_display(),
        "workspace": project.workspace.name,
        "github_repo": project.workspace.github_repo,
    }

    # 2. Milestones
    milestones_qs = project.project_milestones.all().order_by('due_date', 'created_at')
    milestones = [
        {
            "title": m.title,
            "description": m.description,
            "due_date": str(m.due_date) if m.due_date else "None",
            "is_completed": m.is_completed,
            "completed_at": str(m.completed_at) if m.completed_at else "None"
        }
        for m in milestones_qs
    ]

    # 3. Tasks
    tasks_qs = project.tasks.all().order_by('due_date', 'created_at')
    tasks = [
        {
            "title": t.title,
            "description": t.description,
            "assigned_to": t.assigned_to.username if t.assigned_to else "Unassigned",
            "status": t.get_status_display(),
            "priority": t.get_priority_display(),
            "due_date": str(t.due_date) if t.due_date else "None"
        }
        for t in tasks_qs
    ]

    # 4. Members (skills, availability, workload, historical performance)
    members_qs = project.members.select_related('user', 'user__profile')
    members = []
    for m in members_qs:
        profile = getattr(m.user, 'profile', None)
        member_data = {
            "username": m.user.username,
            "role": m.get_role_display(),
            "skills": m.skills,
            "availability": "Available" if m.availability else "Unavailable",
            "workload": m.workload,
            "specialization": m.specialization,
        }
        if profile:
            member_data.update({
                "level": profile.get_employee_level_display(),
                "status": profile.get_status_display(),
                "status_text": profile.status_text,
                "efficiency": profile.efficiency,
                "reliability": profile.reliability,
                "tasks_assigned": profile.tasks_assigned,
                "tasks_completed": profile.tasks_completed,
                "avg_time_per_task": profile.avg_time_per_task
            })
        members.append(member_data)

    # 5. Memories
    memories_qs = project.ai_memories.all()
    memories = [
        {
            "key": mem.key,
            "value": mem.value,
            "type": mem.get_memory_type_display()
        }
        for mem in memories_qs
    ]

    # 6. Recent Chat messages (if channel is linked)
    recent_chat = []
    # Try to find a channel related to this project or use project name match
    channel = getattr(project, 'channel', None)
    if not channel:
        # Fallback: check if workspace has a channel matching project name or 'general'
        channel = project.workspace.channels.filter(name__iexact=project.name).first()
        if not channel:
            channel = project.workspace.channels.filter(is_project_channel=True).first()

    if channel:
        messages_qs = Message.objects.filter(channel=channel, is_deleted=False).order_by('-created_at')[:recent_messages_limit]
        recent_chat = [
            f"[{m.created_at.strftime('%H:%M:%S')}] {m.sender.username}: {m.text}"
            for m in reversed(messages_qs)
        ]

    return {
        "project": proj_info,
        "milestones": milestones,
        "tasks": tasks,
        "members": members,
        "memories": memories,
        "recent_chat": recent_chat
    }


def call_pilot_ai(prompt: str, context: dict) -> str:
    """
    Bridge to the new AIServiceLayer. Ensures that direct calls to this
    function are post-processed and follow the startup-CTO persona.
    """
    from .pilot_ai_core import AIPromptFormatter, AIResponseCleaner
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        formatted_prompt = AIPromptFormatter.format_prompt(prompt, context)
        response = model.generate_content(formatted_prompt)
        return AIResponseCleaner.clean_response(response.text.strip(), prompt)
    except Exception as e:
        logger.error(f"Error in bridged call_pilot_ai: {e}")
        return "Decision:\nSpiderman should coordinate next steps.\nReason:\nPilotAI encountered a network error.\nRisk:\nDelayed response."


# ─── Feature API Implementations ─────────────────────────────────────────────

def get_task_recommendation(project: Project, task_description: str) -> str:
    """Recommends task assignment intelligently."""
    from .pilot_ai_core import AIServiceLayer
    prompt = f"Recommend task assignment for the task: '{task_description}'."
    return AIServiceLayer.call_pilot_ai(query=prompt, project=project)


def run_sprint_planning(project: Project, sprint_goal: str) -> str:
    """Performs sprint planning and outputs milestones and assignments."""
    from .pilot_ai_core import AIServiceLayer
    prompt = f"Run complete sprint planning for this sprint goal: '{sprint_goal}'."
    return AIServiceLayer.call_pilot_ai(query=prompt, project=project)


def run_risk_analysis(project: Project) -> str:
    """Analyzes projects for delays, blockers, and workload imbalances."""
    from .pilot_ai_core import AIServiceLayer
    prompt = "Perform project risk analysis. Inspect milestones, deadlines, blockers, and team workloads."
    return AIServiceLayer.call_pilot_ai(query=prompt, project=project)


def run_workload_balancing(project: Project) -> str:
    """Balances tasks across members who are overloaded or have skill alignment."""
    from .pilot_ai_core import AIServiceLayer
    prompt = "Review workloads and balance tasks to prevent overloading."
    return AIServiceLayer.call_pilot_ai(query=prompt, project=project)


def run_member_skill_analysis(project: Project) -> str:
    """Analyzes the skills, levels, and gaps of members for the current project."""
    from .pilot_ai_core import AIServiceLayer
    prompt = "Analyze member skills/specialization and resource/skill gaps."
    return AIServiceLayer.call_pilot_ai(query=prompt, project=project)
