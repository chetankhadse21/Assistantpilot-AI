import os
import django
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth.models import User
from slack_app.models import UserProfile

users = User.objects.all()
if not users:
    print("No users found. Creating a test user 'testuser' with password 'password123'...")
    user = User.objects.create_user(username='testuser', password='password123', email='test@example.com')
    UserProfile.objects.create(user=user, display_name='Test User')
    users = [user]

skills = ['Frontend', 'Backend', 'Design', 'DevOps', 'Data Science', 'QA']

for user in users:
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Generate realistic fake stats
    tasks_assigned = random.randint(20, 100)
    tasks_completed = random.randint(int(tasks_assigned * 0.4), tasks_assigned) # 40-100% completion
    deadlines_met = random.randint(int(tasks_completed * 0.5), tasks_completed) # 50-100% deadlines met
    avg_speed = round(random.uniform(1.5, 8.5), 1) # 1.5 to 8.5 hours
    
    profile.employee_level = random.choice(['beginner', 'professional', 'expert'])
    profile.skill_strength = random.choice(skills)
    profile.tasks_assigned = tasks_assigned
    profile.tasks_completed = tasks_completed
    profile.deadlines_met = deadlines_met
    profile.avg_time_per_task = avg_speed
    
    profile.save()
    print(f"Updated {user.username} -> Level: {profile.employee_level}, Skill: {profile.skill_strength}")
    print(f"Stats -> Assigned: {tasks_assigned}, Completed: {tasks_completed}, Deadlines: {deadlines_met}, Speed: {avg_speed}h")
    print("-" * 40)

print("✅ Successfully populated dummy stats for all users!")
