import os
import json
import logging
import google.generativeai as genai
from django.conf import settings

logger = logging.getLogger(__name__)

# Configure Gemini
api_key = getattr(settings, 'GEMINI_API_KEY', None)
if api_key:
    genai.configure(api_key=api_key)
else:
    logger.warning("GEMINI_API_KEY not found in settings.")

# Using gemini-flash-latest
MODEL_NAME = "gemini-flash-latest"

def get_model():
    return genai.GenerativeModel(MODEL_NAME)

def recommend_task_assignment(task_description: str, candidates: list) -> dict:
    """
    Recommend the best candidate for a task based on skills, past performance, and current workload.
    """
    if not candidates:
        return {"assigned_to": None, "reason": "No candidates available."}
        
    model = get_model()
    
    prompt = f"""
    You are an AI project lead assistant. Your job is to assign tasks to the best-suited team member based on their skills, past performance, and current workload.
    You must NOT hallucinate. Use ONLY the provided candidates.
    Respond ONLY with valid JSON format containing 'assigned_to' (the username of the chosen candidate) and 'reason' (a concise explanation in natural language).
    
    Task: "{task_description}"
    
    Candidates (JSON):
    {json.dumps(candidates, indent=2)}
    
    Output JSON format:
    {{
      "assigned_to": "username",
      "reason": "explanation here"
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        return json.loads(text)
    except Exception as e:
        logger.error(f"Error in recommend_task_assignment: {e}")
        return {"assigned_to": None, "reason": "AI recommendation failed due to an error."}


def provide_project_insights(progress_data: dict) -> str:
    """
    Provide project-level insights: progress summaries, team performance observations.
    """
    model = get_model()
    
    prompt = f"""
    You are an AI project lead assistant. Provide project-level insights, including progress summaries and team performance observations, based ONLY on the provided structured data. 
    Keep your response concise, factual, and in natural language. Do not hallucinate.

    Project Data:
    {json.dumps(progress_data, indent=2)}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error in provide_project_insights: {e}")
        return "Could not generate project insights at this time."


def detect_risks(project_data: dict) -> str:
    """
    Detect risks such as delays (missed deadlines, low activity) or workload imbalance.
    """
    model = get_model()
    
    prompt = f"""
    You are an AI project lead assistant. Detect risks based ONLY on the provided structured data. 
    Look for potential delays, missed deadlines, low activity, or workload imbalances across the team.
    Keep your response concise, factual, and in natural language. If there are no risks, state that clearly. Do not hallucinate.

    Project Data:
    {json.dumps(project_data, indent=2)}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error in detect_risks: {e}")
        return "Could not detect risks at this time."


def generate_milestones_and_matches(channel_name: str, channel_desc: str, candidates: list) -> dict:
    """
    Generate a list of project milestones and recommend qualified workspace contributors.
    """
    model = get_model()
    
    prompt = f"""
    You are an AI Project Lead. The team is creating a new project channel or goal in their workspace:
    Project/Channel Name: "{channel_name}"
    Description: "{channel_desc}"
    
    Your tasks:
    1. Generate a sequence of exactly 3 to 5 clear, developer-friendly and actionable project milestones.
       Example milestones for "frontend calculator website":
       - "Setup base HTML outline and CSS styling"
       - "Implement arithmetic functions in JavaScript"
       - "Conduct final testing and complete project demo"
    
    2. Analyze the candidates list below (which contains usernames, skills, levels, and efficiency/reliability metrics) and select 1 to 3 best-suited candidates who are qualified to help on this project.
    
    Candidates:
    {json.dumps(candidates, indent=2)}
    
    Return ONLY a valid JSON object matching the following structure. Do NOT include markdown backticks (e.g. ```json) or explanation outside the JSON block.
    
    {{
      "milestones": [
        {{
          "title": "Milestone Title Here",
          "description": "Short description of milestone goal"
        }}
      ],
      "qualified_employees": ["username1", "username2"]
    }}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        return json.loads(text)
    except Exception as e:
        logger.error(f"Error in generate_milestones_and_matches: {e}")
        # Default fallback
        return {
            "milestones": [
                {"title": "Initial Base Setup", "description": "Set up project base files and outline base layout structure."},
                {"title": "Core Development & Scripting", "description": "Implement core scripting functions and interactive features."},
                {"title": "Testing & Final Demonstration", "description": "Conduct thorough testing and complete full project demo."}
            ],
            "qualified_employees": [c["username"] for c in candidates[:2]] if candidates else []
        }


def check_milestone_completion(message_text: str, milestones: list) -> str:
    """
    Verify if the user's message indicates they completed a pending milestone.
    Returns the exact title of the completed milestone, or None.
    """
    if not milestones:
        return None
        
    # Fast heuristic check to save Gemini API quota
    text_lower = message_text.lower()
    
    # If the message starts with an AI trigger, it's a query to the AI, not a milestone report!
    if text_lower.startswith(('@ai', '/ai', '@pilotai', '!ai')):
        return None
        
    completion_keywords = {
        'done', 'complete', 'finish', 'add', 'implement', 'create', 'build', 
        'achieve', 'make', 'ready', 'success', 'working', 'worked', 'upload', 
        'push', 'commit', 'deploy'
    }
    
    # Check if there is any overlap with completion terms or specific milestone words
    has_completion_word = any(kw in text_lower for kw in completion_keywords)
    
    # Extract words from milestone titles to match contextually
    milestone_words = set()
    for m in milestones:
        for w in m['title'].lower().split():
            # filter out common short stop words
            if len(w) > 2:
                milestone_words.add(w)
                
    has_milestone_word = any(mw in text_lower for mw in milestone_words)
    
    # If it has neither, it is highly unlikely to be a milestone completion report.
    # Return None early to save Gemini daily API quota!
    if not (has_completion_word or has_milestone_word):
        return None
        
    model = get_model()
    
    prompt = f"""
    You are an AI Project Lead. A team member has just sent this chat message:
    Message: "{message_text}"
    
    Here are the pending project milestones:
    {json.dumps(milestones, indent=2)}
    
    Analyze if this message clearly and explicitly reports or asserts that one of these milestones is now completed or achieved.
    Examples of matches:
    - Message: "html skeleton is done and css is added" matches milestone "Setup base HTML outline and CSS styling"
    - Message: "javascript function added like it" matches milestone "Implement arithmetic functions in JavaScript"
    - Message: "demo completed" matches milestone "Conduct final testing and complete project demo"
    
    If one of the milestones is matches as completed, return ONLY the exact "title" of that completed milestone.
    If no milestone matches or the message is just general talk, return ONLY the word "none".
    Do not add any markdown, explanation or styling. Just return the title or "none".
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip().strip('"').strip("'")
        if text.lower() == "none" or not text:
            return None
        return text
    except Exception as e:
        logger.error(f"Error in check_milestone_completion: {e}")
        return None


def check_and_update_project_progress(message) -> dict:
    """
    Checks if a message completes a project milestone. If it does, updates it in the DB,
    notifies the channel, and returns update metadata.
    """
    from .models import ChannelMilestone, Message
    from django.contrib.auth.models import User
    from django.utils import timezone
    
    channel = message.channel
    if not channel or not channel.is_project_channel:
        return None
        
    pending_milestones = channel.milestones.filter(is_completed=False)
    if not pending_milestones.exists():
        return None
        
    milestones_list = [{"title": m.title, "description": m.description} for m in pending_milestones]
    
    # Call Gemini to check matches
    matched_title = check_milestone_completion(message.text, milestones_list)
    if not matched_title:
        return None
        
    # Find matching milestone
    milestone = pending_milestones.filter(title__iexact=matched_title).first()
    if not milestone:
        # Fuzzy fallback match
        for m in pending_milestones:
            if m.title.lower() in matched_title.lower() or matched_title.lower() in m.title.lower():
                milestone = m
                break
                
    if milestone:
        milestone.is_completed = True
        milestone.completed_at = timezone.now()
        milestone.save()
        
        # Calculate new progress percentage
        total_milestones = channel.milestones.count()
        completed_milestones = channel.milestones.filter(is_completed=True).count()
        progress_percentage = round((completed_milestones / total_milestones) * 100)
        
        # Create an automated bot announcement
        announcement_text = f"🎉 **Milestone Achieved!**\n" \
                            f"**{message.sender.username}** has completed the milestone: *\"{milestone.title}\"*!\n\n" \
                            f"📈 Project **\"{channel.name}\"** is now **{progress_percentage}%** complete!"
                            
        # Create system notification message
        bot_sender = User.objects.filter(is_superuser=True).first() or message.sender
        bot_msg = Message.objects.create(
            sender=bot_sender,
            channel=channel,
            text=announcement_text,
            ai_intent="announcement",
            ai_sentiment="positive",
            ai_tags=["ai-milestone-update"]
        )
        
        return {
            "milestone_id": milestone.id,
            "milestone_title": milestone.title,
            "progress_percentage": progress_percentage,
            "bot_message_id": bot_msg.id,
            "bot_message_text": bot_msg.text,
            "bot_message_sender": bot_msg.sender.username,
            "bot_message_created_at": bot_msg.created_at.isoformat()
        }
    return None
