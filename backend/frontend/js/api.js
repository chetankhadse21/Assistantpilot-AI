// ── API Configuration ────────────────────────────────────────────────────────
const API_BASE = 'http://127.0.0.1:8000/api';
const WS_BASE = 'ws://localhost:8000/ws/chat';

// ── State ────────────────────────────────────────────────────────────────────
let STATE = {
  token: localStorage.getItem('token') || null,
  user: JSON.parse(localStorage.getItem('user') || 'null'),
  workspace: JSON.parse(localStorage.getItem('workspace') || 'null'),
  channels: [],
  dms: [],
  members: [],
  activeRoom: null,    // { type: 'channel'|'dm', id, name, data }
  messages: {},        // roomId -> [messages]
  typingUsers: {},     // roomId -> { userId: timeout }
  ws: null,
  emojiPickerTarget: null,
  thread: null,
};

// ── Helpers ──────────────────────────────────────────────────────────────────
function api(path, options = {}) {
  const token = localStorage.getItem('token'); // always read fresh
  
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(token ? { 'Authorization': `Token ${token}` } : {}),
    ...options.headers,
  };
  
  if (!isFormData && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  return fetch(`${API_BASE}${path}`, {
    method: options.method || 'GET',
    headers: headers,
    body: isFormData ? options.body : (options.body ? JSON.stringify(options.body) : undefined),
  }).then(async res => {
    if (res.status === 401) {
      localStorage.clear();
      location.reload();
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      console.log("Server error:", err);
      throw new Error(err.error || err.detail || JSON.stringify(err) || `HTTP ${res.status}`);
    }
    return res.json().catch(() => null);
  });
}

function toast(message, type = 'default') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', default: '💬' };
  t.textContent = `${icons[type] || ''} ${message}`;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

function formatTime(ts) {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(ts) {
  const d = new Date(ts);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { month: 'long', day: 'numeric', year: 'numeric' });
}

function getInitials(name) {
  return (name || '?').split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

const AVATAR_COLORS = [
  '#4A154B', '#1264A3', '#007A5A', '#E01E5A', '#ECB22E',
  '#E87722', '#C9276C', '#2BAC76', '#A03E99', '#0576B9'
];

function getAvatarColor(name) {
  let hash = 0;
  for (let c of (name || '')) hash = (hash << 5) - hash + c.charCodeAt(0);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function renderMsgText(text) {
  if (!text) return '';
  
  // 1. Headings (Markdown headers)
  text = text.replace(/^### (.*$)/gim, '<h3 style="margin: 12px 0 6px 0; font-size: 15px; font-weight: 800; color: #1a1d2e;">$1</h3>');
  text = text.replace(/^## (.*$)/gim, '<h2 style="margin: 14px 0 8px 0; font-size: 17px; font-weight: 900; color: #1a1d2e;">$1</h2>');
  text = text.replace(/^# (.*$)/gim, '<h1 style="margin: 16px 0 10px 0; font-size: 19px; font-weight: 900; color: #1a1d2e;">$1</h1>');

  // 2. Bullet lists at the start of lines (handle spaces and convert to a clean bullet point character)
  text = text.replace(/^\s*\*\s+/gm, '• ');
  text = text.replace(/^\s*-\s+/gm, '• ');

  // 3. Bold: Double asterisks first (Markdown standard)
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  
  // 4. Bold/Italic: Single asterisks (Slack/standard Markdown)
  text = text.replace(/\*([^*]+)\*/g, '<strong>$1</strong>');

  // 5. Code blocks (inline code)
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

  // 6. Mentions
  text = text.replace(/@(\w+)/g, '<span class="mention">@$1</span>');

  // 7. Links
  text = text.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');

  return text;
}

function intentBadge(intent) {
  if (!intent || intent === 'general') return '';
  const labels = {
    question: '❓ Question',
    task: '✅ Task',
    meeting: '📅 Meeting',
    help: '🆘 Help',
    announcement: '📢 Announce',
    praise: '🎉 Praise',
  };
  const label = labels[intent] || intent;
  return `<span class="msg-intent-badge intent-${intent}">${label}</span>`;
}
