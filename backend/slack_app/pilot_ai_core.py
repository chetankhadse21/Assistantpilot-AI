import os
import re
import json
import logging
from django.conf import settings
from django.contrib.auth.models import User
import google.generativeai as genai
from .models import Project, Task, Member, Milestone, AIMemory, Message, WorkspaceMember

logger = logging.getLogger(__name__)

# Configure Gemini
api_key = getattr(settings, 'GEMINI_API_KEY', None)
if api_key:
    genai.configure(api_key=api_key)
else:
    logger.warning("GEMINI_API_KEY not found in settings for PilotAI core.")

MODEL_NAME = "gemini-flash-latest"


class AIContextBuilder:
    """
    Gathers only highly relevant project data, uses only the last 5-10 messages,
    summarizes the context briefly, and avoids sending full chat history.
    """
    @staticmethod
    def build_compact_context(project: Project, recent_messages_limit: int = 7) -> dict:
        if not project:
            return {}

        # 1. Project basic info
        proj_info = {
            "project": project.name,
            "desc": project.description[:100] if project.description else "No description",
            "status": project.get_status_display(),
        }

        # 2. Member skills, availability, workload
        members = []
        for m in project.members.select_related('user', 'user__profile'):
            profile = getattr(m.user, 'profile', None)
            availability = "Online" if (profile and profile.status != 'offline') else "Offline"
            if not m.availability:
                availability = "Offline"

            members.append({
                "username": m.user.username,
                "role": m.get_role_display(),
                "skills": m.skills or (profile.skill_strength.split(',') if profile and profile.skill_strength else []),
                "status": availability,
                "workload": m.workload
            })

        # 3. Compact Tasks (only incomplete or high-priority)
        tasks = []
        for t in project.tasks.exclude(status='completed').order_by('-priority')[:5]:
            tasks.append({
                "title": t.title,
                "assignee": t.assigned_to.username if t.assigned_to else "Unassigned",
                "status": t.get_status_display(),
                "priority": t.get_priority_display()
            })

        # 4. Compact Milestones
        milestones = []
        for m in project.project_milestones.all().order_by('due_date')[:3]:
            milestones.append({
                "title": m.title,
                "done": m.is_completed
            })

        # 5. Blockers / Decisions from AIMemory
        memories = []
        for mem in project.ai_memories.filter(memory_type__in=['blocker', 'decision'])[:5]:
            val_text = mem.value.get('text', '') if isinstance(mem.value, dict) else str(mem.value)
            memories.append({
                "type": mem.memory_type,
                "key": mem.key,
                "value": val_text[:100]
            })

        # 6. Recent Chat messages (strictly limited)
        recent_chat = []
        channel = getattr(project, 'channel', None)
        if not channel:
            channel = project.workspace.channels.filter(is_project_channel=True).first()

        if channel:
            messages_qs = Message.objects.filter(channel=channel, is_deleted=False).order_by('-created_at')[:recent_messages_limit]
            recent_chat = [
                f"{m.sender.username}: {m.text}"
                for m in reversed(messages_qs)
            ]

        return {
            "active_project": proj_info,
            "members": members,
            "current_tasks": tasks,
            "milestones": milestones,
            "blockers_and_memories": memories,
            "recent_chat": recent_chat
        }


class AIPromptFormatter:
    """
    Formats the context and query into a strict, concise technical leader prompt.
    Enforces under-120-words constraint and the Decision/Reason/Risk layout.
    """
    
    SYSTEM_INSTRUCTION = (
        "You are PilotAI, an intelligent technical team leader.\n"
        "You manage projects like a startup CTO.\n\n"
        "Strict Rules:\n"
        "- Keep responses under 120 words at all costs.\n"
        "- Be highly concise, direct, and actionable.\n"
        "- Never repeat project context in your reply.\n"
        "- Avoid corporate jargon, large paragraphs, and long project summaries.\n"
        "- Sound confident, practical, and authoritative.\n"
        "- Do NOT generate ANALYSIS sections, excessive reasoning, or enterprise consulting style output.\n\n"
        "TASK ASSIGNMENT STYLE:\n"
        "If you are recommending or assigning a task to someone, you MUST strictly format your response exactly like this:\n"
        "Decision:\n"
        "[Actionable direct decision on who handles what]\n"
        "Reason:\n"
        "[1 concise sentence explaining skill/availability advantage]\n"
        "Risk:\n"
        "[1 concise sentence identifying a real bottleneck or risk]"
    )

    GENERAL_SYSTEM_INSTRUCTION = (
        "You are Gemini, a helpful, intelligent AI assistant.\n"
        "Answer the user's query clearly, accurately, and thoroughly in natural language.\n"
        "Do NOT mention any team members or make any project task-assignments, decisions, or risk assessments."
    )

    @classmethod
    def format_prompt(cls, query: str, compact_context: dict) -> str:
        return f"""
{cls.SYSTEM_INSTRUCTION}

PROJECT DATA CONTEXT:
{json.dumps(compact_context, indent=2)}

USER REQUEST:
"{query}"
"""

    @classmethod
    def format_general_prompt(cls, query: str) -> str:
        return f"""
{cls.GENERAL_SYSTEM_INSTRUCTION}

USER REQUEST:
"{query}"
"""


class AIResponseCleaner:
    """
    Post-processor that removes repetitive text, limits output length,
    compresses unnecessary wording, and formats concise, leadership-style replies.
    """
    @staticmethod
    def clean_response(text: str, query: str) -> str:
        text = text.strip()
        
        # 1. Strip corporate throat-clearing and intro/outro phrases
        throats = [
            r"Here is my recommendation.*",
            r"Based on the project context.*",
            r"As PilotAI, the technical team lead.*",
            r"I have analyzed the workload.*",
            r"Here are my thoughts.*",
            r"Let's break this down.*",
            r"Certainly!.*",
            r"Sure,.*",
        ]
        for pattern in throats:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # 2. Check if the model generated disallowed sections (like ANALYSIS:, TASK ASSIGNMENT:, REASON:, RISKS:)
        # and clean them up/map them to the target layout.
        if "ANALYSIS:" in text:
            # If the model produced a full enterprise PM report, extract only the actionable bits
            # and map to Decision/Reason/Risk or a short summary.
            decision_match = re.search(r"TASK ASSIGNMENT:\s*(.*?)(?=(REASON:|RISKS:|NEXT ACTIONS:|$))", text, re.DOTALL | re.IGNORECASE)
            reason_match = re.search(r"REASON:\s*(.*?)(?=(RISKS:|NEXT ACTIONS:|$))", text, re.DOTALL | re.IGNORECASE)
            risk_match = re.search(r"RISKS:\s*(.*?)(?=(NEXT ACTIONS:|$))", text, re.DOTALL | re.IGNORECASE)
            
            if decision_match:
                decision = decision_match.group(1).strip()
                reason = reason_match.group(1).strip() if reason_match else "Best fit based on skillset."
                risk = risk_match.group(1).strip() if risk_match else "None identified."
                text = f"Decision:\n{decision}\nReason:\n{reason}\nRisk:\n{risk}"
            else:
                # Remove the ANALYSIS block entirely
                text = re.sub(r"ANALYSIS:.*?(?=(TASK ASSIGNMENT|DECISION|REASON|RISKS|$))", "", text, flags=re.DOTALL | re.IGNORECASE)

        # 3. Clean headers formatting to be standard
        text = re.sub(r"\*\*Decision:\*\*", "Decision:", text, flags=re.IGNORECASE)
        text = re.sub(r"\*\*Reason:\*\*", "Reason:", text, flags=re.IGNORECASE)
        text = re.sub(r"\*\*Risk:\*\*", "Risk:", text, flags=re.IGNORECASE)

        # 4. Eliminate redundant spacing and clean newlines
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = "\n".join(lines)

        # 5. Compress wordy sentences
        text = re.sub(r"It is recommended that (\w+) should", r"\1 should", text, flags=re.IGNORECASE)
        text = re.sub(r"I decide that (\w+) is the best fit to", r"\1 will", text, flags=re.IGNORECASE)
        text = re.sub(r"In order to make sure that we", r"To ensure we", text, flags=re.IGNORECASE)
        text = re.sub(r"is currently the strongest (\w+) developer based on skills and availability", r"is the strongest \1", text, flags=re.IGNORECASE)

        # 6. Strict length limit (120 words)
        words = text.split()
        if len(words) > 120:
            # Let's cleanly truncate or keep only the structural headers
            # If it's a decision format, try to keep the headers
            if "Decision:" in text and "Reason:" in text:
                parts = re.split(r"(Decision:|Reason:|Risk:)", text, flags=re.IGNORECASE)
                # Reconstruct and trim each part to avoid total word overflow
                reconstructed = []
                current_header = ""
                for part in parts:
                    if part.strip().lower() in ["decision:", "reason:", "risk:"]:
                        current_header = part.strip()
                    elif current_header:
                        p_words = part.strip().split()
                        trimmed_part = " ".join(p_words[:25])  # Limit each section to ~25 words
                        reconstructed.append(f"{current_header}\n{trimmed_part}")
                        current_header = ""
                text = "\n".join(reconstructed)
            else:
                text = " ".join(words[:110]) + "..."

        return text.strip()


class AIMemorySummarizer:
    """
    Extracts decisions, risks, or key parameters from queries and responses
    and writes them to Django's AIMemory table.
    """
    @staticmethod
    def summarize_and_store(project: Project, query: str, response: str):
        if not project or not response:
            return

        # Simple detection of decisions or blockers
        is_decision = "decision:" in response.lower()
        is_blocker = "risk:" in response.lower() or "blocker" in query.lower()

        if is_decision:
            # Extract decision text
            decision_part = ""
            match = re.search(r"decision:\s*(.*?)(?=(reason:|risk:|$))", response, re.DOTALL | re.IGNORECASE)
            if match:
                decision_part = match.group(1).strip()
            else:
                decision_part = response[:100]

            if decision_part:
                # Create a concise key
                key = f"dec_{project.id}_{hash(decision_part) % 10000}"
                AIMemory.objects.update_or_create(
                    project=project,
                    key=key[:100],
                    defaults={
                        'value': {'text': decision_part},
                        'memory_type': 'decision'
                    }
                )
                logger.info(f"Stored project decision in AIMemory: {key}")

        if is_blocker:
            # Extract risk or blocker text
            risk_part = ""
            match = re.search(r"risk:\s*(.*?)(?=$)", response, re.DOTALL | re.IGNORECASE)
            if match:
                risk_part = match.group(1).strip()
            else:
                risk_part = response[:100]

            if risk_part:
                key = f"risk_{project.id}_{hash(risk_part) % 10000}"
                AIMemory.objects.update_or_create(
                    project=project,
                    key=key[:100],
                    defaults={
                        'value': {'text': risk_part},
                        'memory_type': 'blocker'
                    }
                )
                logger.info(f"Stored project risk/blocker in AIMemory: {key}")


class AIServiceLayer:
    """
    Facade serving as the single entry point for AI project operations.
    Coordinates Context Builder, Prompt Formatter, Gemini API call,
    Response Cleaner, and Memory Summarizer.
    """
    @classmethod
    def call_pilot_ai(cls, query: str, workspace_id: int = None, project: Project = None, recent_messages_limit: int = 7, file_path: str = None) -> str:
        # Check if @team is mentioned to determine mode
        is_team_mode = "@team" in query.lower()

        # 1. Resolve Project
        if not project and workspace_id:
            project = Project.objects.filter(workspace_id=workspace_id).first()
            if not project:
                # Fallback: create standard workspace core project
                from .models import Workspace
                workspace = Workspace.objects.filter(id=workspace_id).first()
                if workspace:
                    project = Project.objects.create(
                        workspace=workspace,
                        name=f"{workspace.name} Core",
                        description=f"Automated project synchronization for workspace {workspace.name}."
                    )

        # Sync members to project if not already present
        if project:
            try:
                from .models import WorkspaceMember
                for wm in WorkspaceMember.objects.filter(workspace=project.workspace):
                    prof = getattr(wm.user, 'profile', None)
                    skills = [prof.skill_strength] if prof and prof.skill_strength else []
                    Member.objects.get_or_create(
                        project=project,
                        user=wm.user,
                        defaults={
                            'role': 'developer',
                            'skills': skills,
                            'availability': prof.status != 'offline' if prof else True,
                            'specialization': prof.skill_strength if prof else ""
                        }
                    )
            except Exception as e:
                logger.error(f"Error syncing project members in AIServiceLayer: {e}")

        # 2. Format Prompt based on mode
        if not is_team_mode:
            formatted_prompt = AIPromptFormatter.format_general_prompt(query)
        else:
            # Build Context
            context = {}
            if project:
                context = AIContextBuilder.build_compact_context(project, recent_messages_limit)

            formatted_prompt = AIPromptFormatter.format_prompt(query, context)

        # 3. Generate Content
        success = True
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            contents = [formatted_prompt]
            if file_path and os.path.exists(file_path):
                try:
                    import PIL.Image
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                        img = PIL.Image.open(file_path)
                        contents.append(img)
                        logger.info(f"PilotAI Core successfully loaded image: {file_path}")
                except Exception as img_err:
                    logger.error(f"Failed to load image for Gemini: {img_err}")

            response = model.generate_content(contents)
            raw_text = response.text.strip()
        except Exception as e:
            logger.error(f"Error calling Gemini in AIServiceLayer: {e}")
            if is_team_mode:
                raw_text = "Decision:\nSpiderman should coordinate next steps.\nReason:\nGemini API connection error.\nRisk:\nDelayed response until connection is restored."
            else:
                raw_text = "⚠️ I'm having trouble connecting right now. Please try again in a moment."
            success = False

        if not is_team_mode:
            return raw_text

        # 4. Clean & Post-Process Response
        cleaned_text = AIResponseCleaner.clean_response(raw_text, query)

        # 5. Save relevant memory
        if project and success:
            try:
                AIMemorySummarizer.summarize_and_store(project, query, cleaned_text)
            except Exception as e:
                logger.error(f"Error storing memory: {e}")

        return cleaned_text
