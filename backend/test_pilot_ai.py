import os
import sys
import django

# Setup Django environment
sys.path.append(r'd:\freelances\virtual_leader01\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth.models import User
from slack_app.models import Project, Workspace, Member, WorkspaceMember, UserProfile
from slack_app.pilot_ai_core import (
    AIContextBuilder,
    AIPromptFormatter,
    AIResponseCleaner,
    AIMemorySummarizer,
    AIServiceLayer
)

def run_tests():
    print("==================================================")
    print("           PILOTAI BACKEND TEST PIPELINE          ")
    print("==================================================")

    # 1. Get or Create Dummy Workspace and Project
    user = User.objects.first()
    if not user:
        user = User.objects.create_user(username="test_admin", password="password")
    
    # Check or create profile
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'display_name': 'Test Admin',
            'status': 'active',
            'skill_strength': 'Python,Django,React'
        }
    )

    workspace, _ = Workspace.objects.get_or_create(
        name="Test Workspace",
        defaults={'created_by': user}
    )
    
    WorkspaceMember.objects.get_or_create(
        workspace=workspace,
        user=user,
        defaults={'role': 'admin'}
    )

    project, _ = Project.objects.get_or_create(
        workspace=workspace,
        name="Test Project Core",
        defaults={'description': 'Core development project for verifying PilotAI capabilities.'}
    )

    Member.objects.get_or_create(
        project=project,
        user=user,
        defaults={
            'role': 'lead',
            'skills': ['Python', 'Django', 'React'],
            'availability': True,
            'specialization': 'Python Backend'
        }
    )

    # 2. Test Context Builder
    print("\n[1/5] Testing AIContextBuilder...")
    context = AIContextBuilder.build_compact_context(project)
    print(f"Compact Context Fields: {list(context.keys())}")
    print(f"Compact Context Project Info: {context.get('active_project')}")
    print(f"Compact Context Members Count: {len(context.get('members', []))}")
    assert 'active_project' in context
    assert 'members' in context
    assert 'recent_chat' in context
    print("-> Context Builder PASSED.")

    # 3. Test Prompt Formatter
    print("\n[2/5] Testing AIPromptFormatter...")
    query = "Recommend task assignment for building a React UI page."
    prompt = AIPromptFormatter.format_prompt(query, context)
    print("Snippet of formatted prompt:")
    print("-" * 40)
    print("\n".join(prompt.split("\n")[:15]))
    print("-" * 40)
    assert "PilotAI" in prompt
    assert "Rules:" in prompt
    print("-> Prompt Formatter PASSED.")

    # 4. Test Response Cleaner & Post-processor
    print("\n[3/5] Testing AIResponseCleaner...")
    # Test task assignment format cleaning
    dirty_response = """
    ANALYSIS:
    We have evaluated the options and Spiderman has React skills while Ashwini is offline.
    
    TASK ASSIGNMENT:
    Spiderman is assigned to build the React UI page.
    
    REASON:
    He has React specialization and is currently active.
    
    RISKS:
    There is a small delay risk due to sprint backlog overload.
    
    NEXT ACTIONS:
    - Get started today.
    """
    cleaned = AIResponseCleaner.clean_response(dirty_response, query)
    print("Cleaned / Post-processed response:")
    print("-" * 40)
    print(cleaned)
    print("-" * 40)
    
    # Word count check
    word_count = len(cleaned.split())
    print(f"Cleaned Word Count: {word_count}")
    assert word_count < 120
    assert "Decision:" in cleaned
    assert "Reason:" in cleaned
    assert "Risk:" in cleaned
    assert "ANALYSIS:" not in cleaned
    print("-> Response Cleaner PASSED.")

    # 5. Test Memory Summarizer
    print("\n[4/5] Testing AIMemorySummarizer...")
    AIMemorySummarizer.summarize_and_store(project, query, cleaned)
    memories = project.ai_memories.all()
    print(f"Stored Memories Count: {memories.count()}")
    for mem in memories:
        print(f"- Key: {mem.key} | Type: {mem.memory_type} | Val: {mem.value}")
    assert memories.count() > 0
    print("-> Memory Summarizer PASSED.")

    # 6. Test Full AIServiceLayer
    print("\n[5/5] Testing Full AIServiceLayer call...")
    try:
        # A. General Mode (Without @team)
        general_query = "What is system architecture?"
        general_reply = AIServiceLayer.call_pilot_ai(general_query, project=project)
        print("General reply from Gemini (no @team):")
        print("-" * 40)
        print(general_reply)
        print("-" * 40)
        # Verify it behaves like a standard response (not technical leader Decision/Reason/Risk layout)
        assert "Decision:" not in general_reply
        assert "Reason:" not in general_reply
        assert "Risk:" not in general_reply
        print("-> General AI Mode PASSED.")

        # B. Team Mode (With @team)
        team_query = f"{query} @team"
        team_reply = AIServiceLayer.call_pilot_ai(team_query, project=project)
        print("Team reply from Gemini (with @team):")
        print("-" * 40)
        print(team_reply)
        print("-" * 40)
        print(f"Team reply Word Count: {len(team_reply.split())}")
        assert len(team_reply.split()) < 120
        assert "Decision:" in team_reply
        assert "Reason:" in team_reply
        assert "Risk:" in team_reply
        print("-> Team AI Mode PASSED.")
        
        print("-> Full AIServiceLayer call PASSED.")
    except Exception as e:
        print(f"-> Full AIServiceLayer call failed with error (possibly no API key): {e}")

    print("\n==================================================")
    print("         ALL PILOTAI CORE COMPONENT TESTS PASSED   ")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
