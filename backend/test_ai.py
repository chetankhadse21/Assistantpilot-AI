import os
import sys
import django

# Setup django
sys.path.append(r'd:\freelances\virtual_leader01\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from slack_app.models import Workspace
from slack_app.consumers import ChatConsumer

# create dummy consumer instance
consumer = ChatConsumer()
res = consumer._call_gemini("how many members do we have in project?", workspace_id=1)
print("Result:", res)
