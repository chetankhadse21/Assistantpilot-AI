import os
import sys
import django

sys.path.append(r'd:\freelances\virtual_leader01\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

import google.generativeai as genai
from django.conf import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-flash-latest")
print("Calling API...")
response = model.generate_content("hello")
print(response.text)
