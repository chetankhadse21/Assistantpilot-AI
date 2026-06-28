// ── Page Navigation ─────────────────────────────────────────────────────────

function showAuthPage() {
  document.getElementById('auth-page').style.display = 'flex';
  document.getElementById('workspace-page').style.display = 'none';
  document.getElementById('app').classList.remove('visible');
}

function showWorkspacePage() {
  document.getElementById('auth-page').style.display = 'none';
  document.getElementById('workspace-page').style.display = 'flex';
  document.getElementById('app').classList.remove('visible');
  loadWorkspaces();
}

function showApp() {
  document.getElementById('auth-page').style.display = 'none';
  document.getElementById('workspace-page').style.display = 'none';
  document.getElementById('app').classList.add('visible');
  initApp();
}

// ── Workspace Page ───────────────────────────────────────────────────────────

async function loadWorkspaces() {
  const list = document.getElementById('workspace-list');
  list.innerHTML = '<p style="color:#616061;font-size:13px;">Loading…</p>';

  try {
    const workspaces = await api('/workspaces/');
    STATE.workspaces = workspaces;
    if (workspaces.length === 0) {
      list.innerHTML = '<p style="color:#616061;font-size:13px;">No workspaces yet. Create one below!</p>';
      return;
    }
    list.innerHTML = workspaces.map(ws => `
      <div class="workspace-item" onclick="selectWorkspace(${ws.id})">
        <div class="ws-icon">${ws.icon || '💬'}</div>
        <div class="ws-info">
          <h3>${ws.name}</h3>
          <p>${ws.member_count} member${ws.member_count !== 1 ? 's' : ''}</p>
        </div>
      </div>
    `).join('');
  } catch (err) {
    list.innerHTML = `<p style="color:#e01e5a;font-size:13px;">Error: ${err.message}</p>`;
  }
}

function selectWorkspace(id) {
  const ws = (STATE.workspaces || []).find(w => w.id === id);
  if (!ws) return;
  STATE.workspace = ws;
  localStorage.setItem('workspace', JSON.stringify(ws));
  showApp();
}

async function createWorkspace() {
  const name = document.getElementById('ws-name').value.trim();
  if (!name) return toast('Please enter a workspace name', 'error');
  try {
    const ws = await api('/workspaces/', { method: 'POST', body: { name } });
    STATE.workspaces = STATE.workspaces || [];
    STATE.workspaces.push(ws);
    selectWorkspace(ws.id);
    toast(`Workspace "${ws.name}" created! 🎉`, 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── App Init ─────────────────────────────────────────────────────────────────

async function initApp() {
  // Always refresh workspace data from the API to get my_role, github_repo, etc.
  try {
    const workspaces = await api('/workspaces/');
    STATE.workspaces = workspaces;
    const fresh = workspaces.find(w => w.id === STATE.workspace.id);
    if (fresh) {
      STATE.workspace = fresh;
      localStorage.setItem('workspace', JSON.stringify(fresh));
    }
  } catch(e) {
    console.warn('Could not refresh workspace:', e);
  }

  const ws = STATE.workspace;
  document.getElementById('workspace-title').textContent = ws.name;

  // Update sidebar user
  const user = STATE.user;
  const profile = user.profile || {};
  const displayName = profile.display_name || user.username;
  const color = profile.avatar_color || getAvatarColor(displayName);

  document.getElementById('sidebar-username').textContent = displayName;
  document.getElementById('sidebar-avatar').textContent = getInitials(displayName);
  document.getElementById('sidebar-avatar').style.background = color;

  const createChanBtn = document.getElementById('create-channel-btn');
  if (createChanBtn) {
    createChanBtn.style.display = (ws.my_role === 'admin') ? 'inline-block' : 'none';
  }

  // Show GitHub link button for admins
  const githubRow = document.getElementById('github-link-row');
  if (githubRow && ws.my_role === 'admin') {
    githubRow.style.display = 'block';
    const label = document.getElementById('github-link-label');
    if (label) {
      label.textContent = ws.github_repo ? `🐙 ${ws.github_repo}` : '🐙 Link GitHub Repo';
    }
  }

  await Promise.all([loadChannels(), loadDMs(), loadMembers()]);
  renderSidebarWorkspaces();
  initMessageInput();
  initSearch();
  initWebSocket();
}

function renderSidebarWorkspaces() {
  const list = document.getElementById('sidebar-workspace-list');
  if (!list || !STATE.workspaces) return;
  list.innerHTML = STATE.workspaces.map(ws => `
    <div class="channel-item ${STATE.workspace?.id === ws.id ? 'active' : ''}"
         onclick="selectWorkspace(${ws.id})">
      <span class="channel-hash" style="font-size:12px;margin-right:8px;">${ws.icon || '💼'}</span>
      <span>${ws.name}</span>
    </div>
  `).join('');
}

// ── Channels ─────────────────────────────────────────────────────────────────

async function loadChannels() {
  try {
    const channels = await api(`/workspaces/${STATE.workspace.id}/channels/`);
    STATE.channels = channels;
    renderChannelList();
    // Auto-join general
    const general = channels.find(c => c.name === 'general') || channels[0];
    if (general) openChannel(general);
  } catch (err) {
    console.error('loadChannels:', err);
  }
}

function renderChannelList() {
  const list = document.getElementById('channel-list');
  list.innerHTML = STATE.channels.map(ch => `
    <div class="channel-item ${STATE.activeRoom?.id == ch.id ? 'active' : ''}"
         id="ch-item-${ch.id}"
         onclick="openChannel(${JSON.stringify(ch).replace(/"/g, '&quot;')})">
      <span class="channel-hash">${ch.channel_type === 'private' ? '🔒' : '#'}</span>
      <span>${ch.name}</span>
    </div>
  `).join('');
}

async function openChannel(channel) {
  if (STATE.ws && STATE.activeRoom) {
    STATE.ws.send(JSON.stringify({ type: 'leave', room: STATE.activeRoom.id }));
  }

  const roomId = `channel_${channel.id}`;
  STATE.activeRoom = { type: 'channel', id: channel.id, roomId, name: channel.name, data: channel };

  // Update UI
  document.querySelectorAll('.channel-item, .dm-item').forEach(el => el.classList.remove('active'));
  const el = document.getElementById(`ch-item-${channel.id}`);
  if (el) el.classList.add('active');

  // Channel header
  document.getElementById('channel-name').textContent = `# ${channel.name}`;
  const descEl = document.getElementById('channel-description');
if (descEl) descEl.textContent = channel.description || '';
  const placeholderEl = document.getElementById('msg-placeholder');
if (placeholderEl) placeholderEl.textContent = `Message #${channel.name}`;

const msgInput = document.getElementById('msg-input');
if (msgInput) msgInput.placeholder = `Message #${channel.name}`;

  // Handle AI Project Milestones Banner
  const banner = document.getElementById('ai-project-banner');
  if (banner) {
    if (channel.is_project_channel) {
      banner.style.display = 'flex';
      
      // Render qualified team chips
      const teamChips = document.getElementById('ai-project-team-chips');
      if (teamChips) {
        if (channel.qualified_employees && channel.qualified_employees.length > 0) {
          teamChips.innerHTML = channel.qualified_employees.map(u => {
            const name = u.profile?.display_name || u.username;
            return `<span class="employee-chip">👤 ${name}</span>`;
          }).join('');
        } else {
          teamChips.innerHTML = '<span style="color:var(--text-muted); font-size:11px;">Calculating best candidates...</span>';
        }
      }

      // Render milestones checklist
      renderProjectMilestones(channel);
    } else {
      banner.style.display = 'none';
    }
  }

  closeThread();
  await loadMessages(roomId);
  connectWebSocket(roomId);
  loadChannelSummary(channel.id);
}


function renderProjectMilestones(channel) {
  const list = document.getElementById('ai-project-milestones-list');
  const fill = document.getElementById('ai-project-progress-bar-fill');
  const pct = document.getElementById('ai-project-progress-pct');

  if (!list || !fill || !pct) return;

  if (!channel.milestones || channel.milestones.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding: 4px 0;">🎯 Generating project milestones via PilotAI...</div>';
    fill.style.width = '0%';
    pct.textContent = '0%';
    return;
  }

  // Calculate progress
  const total = channel.milestones.length;
  const completed = channel.milestones.filter(m => m.is_completed).length;
  const percentage = Math.round((completed / total) * 100);

  fill.style.width = `${percentage}%`;
  pct.textContent = `${percentage}%`;

  list.innerHTML = channel.milestones.map(m => {
    return `
      <div class="ai-project-milestone-item ${m.is_completed ? 'completed' : ''}" id="milestone-card-${m.id}">
        <div class="ai-project-milestone-item-title">
          <span class="ai-project-milestone-check">${m.is_completed ? '✅' : '⏳'}</span>
          <span>${m.title}</span>
        </div>
        <div class="ai-project-milestone-item-desc">${m.description || ''}</div>
      </div>
    `;
  }).join('');
}


// ── DMs ──────────────────────────────────────────────────────────────────────

async function loadDMs() {
  try {
    const dms = await api(`/dms/?workspace=${STATE.workspace.id}`);
    STATE.dms = dms;
    renderDMList();
  } catch (err) {
    console.error('loadDMs:', err);
  }
}

function renderDMList() {
  const list = document.getElementById('dm-list');

  // Show all members as potential DM contacts
  const otherUsers = STATE.members.filter(m => m.id !== STATE.user?.id);

  if (otherUsers.length === 0) {
    list.innerHTML = '<div style="padding:4px 16px;color:rgba(255,255,255,0.4);font-size:12px;">No other members yet</div>';
    return;
  }

  list.innerHTML = otherUsers.map(user => {
    const profile = user.profile || {};
    const name = profile.display_name || user.username;
    const color = profile.avatar_color || getAvatarColor(name);
    const status = profile.status || 'offline';

    // Check if DM already exists
    const existingDm = STATE.dms.find(d =>
      d.participants.some(p => p.id === user.id)
    );

    return `
      <div class="dm-item ${existingDm && STATE.activeRoom?.id == existingDm.id ? 'active' : ''}"
           id="dm-user-${user.id}"
           onclick="startDM(${user.id})">
        <div class="dm-avatar" style="background:${color}">
          ${getInitials(name)}
          <span class="status-dot status-${status}"></span>
        </div>
        <span>${name}</span>
      </div>
    `;
  }).join('');
}

async function openDM(dmId) {
  const dm = STATE.dms.find(d => d.id == dmId);
  if (!dm) return;

  const other = dm.participants.find(p => p.id !== STATE.user.id) || dm.participants[0];
  const name = other.profile?.display_name || other.username;
  const roomId = `dm_${dm.id}`;

  STATE.activeRoom = { type: 'dm', id: dm.id, roomId, name, data: dm };

  document.querySelectorAll('.channel-item, .dm-item').forEach(el => el.classList.remove('active'));
  const el = document.getElementById(`dm-item-${dm.id}`);
  if (el) el.classList.add('active');

  const channelNameEl = document.getElementById('channel-name');
  if (channelNameEl) channelNameEl.textContent = name;
  const descEl = document.getElementById('channel-description');
  if (descEl) descEl.textContent = '';
  const placeholderEl = document.getElementById('msg-placeholder');
  if (placeholderEl) placeholderEl.textContent = `Message ${name}`;

  const msgInput = document.getElementById('msg-input');
  if (msgInput) msgInput.placeholder = `Message ${name}`;

  closeThread();
  await loadMessages(roomId);
  connectWebSocket(roomId);
}

async function startDM(userId) {
  try {
    const dm = await api('/dms/', {
      method: 'POST',
      body: { workspace: STATE.workspace.id, user_id: userId }
    });
    const exists = STATE.dms.find(d => d.id === dm.id);
    if (!exists) STATE.dms.push(dm);
    renderDMList();
    openDM(dm.id);
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Members ───────────────────────────────────────────────────────────────────

async function loadMembers() {
  try {
    // Get ALL users in the system
    const users = await api('/users/');
    STATE.members = users;
    console.log('Members loaded:', users.length);
  } catch (err) {
    console.error('loadMembers:', err);
  }
}

// ── Messages ─────────────────────────────────────────────────────────────────

async function loadMessages(roomId) {
  const container = document.getElementById('messages-container');
  container.innerHTML = '<div style="padding:20px;color:#616061;text-align:center;">Loading messages…</div>';

  try {
    let messages = [];
    if (roomId.startsWith('channel_')) {
      const channelId = roomId.replace('channel_', '');
      messages = await api(`/channels/${channelId}/messages/`);
    } else {
      const dmId = roomId.replace('dm_', '');
      messages = await api(`/dms/${dmId}/messages/`);
    }
    STATE.messages[roomId] = messages;
    renderMessages(roomId);
    scrollToBottom();
  } catch (err) {
    container.innerHTML = `<div style="padding:20px;color:#e01e5a;">Error: ${err.message}</div>`;
  }
}

function renderMessages(roomId) {
  const container = document.getElementById('messages-container');
  const messages = STATE.messages[roomId] || [];

  if (messages.length === 0) {
    const room = STATE.activeRoom;
    container.innerHTML = `
      <div style="padding:40px 20px;">
        <div style="font-size:48px;margin-bottom:12px;">${room.type === 'channel' ? '💬' : '👋'}</div>
        <h2 style="font-size:24px;font-weight:900;margin-bottom:8px;">
          ${room.type === 'channel' ? `# ${room.name}` : room.name}
        </h2>
        <p style="color:#616061;">
          ${room.type === 'channel'
            ? `This is the beginning of the #${room.name} channel.`
            : `This is the start of your direct message history with ${room.name}.`}
        </p>
      </div>
    `;
    return;
  }

  let html = '';
  let lastDate = null;
  let lastSenderId = null;

  messages.forEach((msg, i) => {
    const date = formatDate(msg.created_at);
    if (date !== lastDate) {
      html += `<div class="date-divider"><div class="date-divider-line"></div><span class="date-divider-text">${date}</span><div class="date-divider-line"></div></div>`;
      lastDate = date;
      lastSenderId = null;
    }

    const isNewSender = msg.sender.id !== lastSenderId;
    lastSenderId = msg.sender.id;

    html += renderMessageHTML(msg, isNewSender);
  });

  container.innerHTML = html;

  // Bind reaction buttons
  container.querySelectorAll('[data-react]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleEmojiPicker(btn.closest('.message').dataset.id);
    });
  });

  // Bind thread open
  container.querySelectorAll('[data-thread]').forEach(btn => {
    btn.addEventListener('click', () => openThread(btn.dataset.thread));
  });

  // Bind reaction chips
  container.querySelectorAll('.reaction-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      sendReaction(chip.dataset.msgId, chip.dataset.emoji);
    });
  });
}

function renderMessageHTML(msg, isNewSender) {
  const sender = msg.sender;
  const profile = sender.profile || {};
  const displayName = profile.display_name || sender.username;
  const color = profile.avatar_color || getAvatarColor(displayName);
  const isMe = sender.id === STATE.user?.id;
  const isAi = sender.username === 'PilotAI' || msg.is_ai_bot;
  const aiBadge = isAi ? '<span class="ai-bot-badge">VIRTUAL LEADER</span>' : '';

  // Group reactions by emoji
  const reactionMap = {};
  (msg.reactions || []).forEach(r => {
    if (!reactionMap[r.emoji]) reactionMap[r.emoji] = { emoji: r.emoji, users: [], count: 0 };
    reactionMap[r.emoji].users.push(r.user.username);
    reactionMap[r.emoji].count++;
  });

  const reactionsHTML = Object.values(reactionMap).map(r => `
    <span class="reaction-chip ${r.users.includes(STATE.user?.username) ? 'mine' : ''}"
          data-msg-id="${msg.id}" data-emoji="${r.emoji}"
          title="${r.users.join(', ')}">
      ${r.emoji} <span class="reaction-count">${r.count}</span>
    </span>
  `).join('');

  const tagsHTML = msg.ai_tags?.length ? `
    <div class="ai-tags">
      ${msg.ai_tags.slice(0, 5).map(t => `<span class="ai-tag">${t}</span>`).join('')}
      ${msg.ai_sentiment !== 'neutral' ? `<span class="ai-tag sentiment-${msg.ai_sentiment}">${msg.ai_sentiment === 'positive' ? '😊' : '😔'} ${msg.ai_sentiment}</span>` : ''}
    </div>
  ` : '';

  const fileHTML = msg.file ? `
    <div class="msg-file" style="margin-top: 8px;">
      <a href="${msg.file}" target="_blank" style="display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; background: #f4f4f4; border: 1px solid #e8e8e8; border-radius: 6px; text-decoration: none; color: #1264A3; font-weight: 700; font-size: 13px;">
        <span>📎</span> Attachment
      </a>
    </div>
  ` : '';

  const threadHTML = msg.reply_count > 0 ? `
    <div class="thread-indicator" data-thread="${msg.id}">
      <span>${msg.reply_count} repl${msg.reply_count !== 1 ? 'ies' : 'y'}</span>
      <span style="color:#616061;font-size:12px;">View thread</span>
    </div>
  ` : '';

  return `
    <div class="message ${isNewSender ? 'new-sender' : ''} ${isAi ? 'is-ai' : ''}" data-id="${msg.id}">
      <div class="msg-avatar ${!isNewSender ? 'hidden' : ''}" style="background:${color}">
        ${getInitials(displayName)}
      </div>
      <div class="msg-body">
        ${isNewSender ? `
          <div class="msg-header">
            <span class="msg-sender">${displayName}</span>${aiBadge}
            <span class="msg-time">${formatTime(msg.created_at)}</span>
            ${intentBadge(msg.ai_intent)}
          </div>
        ` : ''}
        <div class="msg-text ${msg.is_deleted ? 'deleted' : ''}">${msg.is_deleted ? 'This message was deleted.' : renderMsgText(msg.text)}${msg.is_edited ? '<span class="msg-edited">(edited)</span>' : ''}</div>
        ${fileHTML}
        ${tagsHTML}
        ${reactionsHTML ? `<div class="msg-reactions">${reactionsHTML}</div>` : ''}
        ${threadHTML}
      </div>
      <div class="msg-toolbar">
        <button class="toolbar-btn" data-react title="Add reaction">😊</button>
        <button class="toolbar-btn" data-thread="${msg.id}" title="Reply in thread">💬</button>
        ${isMe ? `<button class="toolbar-btn" onclick="deleteMessage(${msg.id})" title="Delete">🗑️</button>` : ''}
        <button class="toolbar-btn" onclick="pinMessage(${msg.id})" title="Pin">📌</button>
      </div>
    </div>
  `;
}

function addMessageToView(roomId, msg) {
  const container = document.getElementById('messages-container');
  if (!STATE.messages[roomId]) STATE.messages[roomId] = [];

  const msgs = STATE.messages[roomId];
  
  // Deduplicate messages by ID
  if (msgs.some(m => m.id === msg.id)) {
    return;
  }

  const isNewSender = msgs.length === 0 || msgs[msgs.length - 1].sender.id !== msg.sender.id;

  // Check if date divider needed
  const lastDate = msgs.length > 0 ? formatDate(msgs[msgs.length - 1].created_at) : null;
  const thisDate = formatDate(msg.created_at);

  if (thisDate !== lastDate) {
    container.insertAdjacentHTML('beforeend', `
      <div class="date-divider"><div class="date-divider-line"></div>
      <span class="date-divider-text">${thisDate}</span>
      <div class="date-divider-line"></div></div>
    `);
  }

  container.insertAdjacentHTML('beforeend', renderMessageHTML(msg, isNewSender));
  msgs.push(msg);

  // Rebind new message
  const newEl = container.querySelector(`[data-id="${msg.id}"]`);
  if (newEl) {
    newEl.querySelector('[data-react]')?.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleEmojiPicker(msg.id);
    });
    newEl.querySelectorAll('.reaction-chip').forEach(chip => {
      chip.addEventListener('click', () => sendReaction(chip.dataset.msgId, chip.dataset.emoji));
    });
  }

  scrollToBottom();
}

function scrollToBottom() {
  const area = document.getElementById('messages-area');
  setTimeout(() => area.scrollTop = area.scrollHeight, 50);
}

// ── Message Input ─────────────────────────────────────────────────────────────

function initMessageInput() {
  const input = document.getElementById('msg-input');
  let typingTimeout = null;

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener('input', () => {
    const val = input.value;
    document.getElementById('send-btn').disabled = !val.trim() && !selectedFile;

    // Typing indicator
    if (STATE.ws && STATE.activeRoom && STATE.ws.readyState === WebSocket.OPEN) {
      STATE.ws.send(JSON.stringify({ type: 'typing', is_typing: true }));
      clearTimeout(typingTimeout);
      typingTimeout = setTimeout(() => {
        if (STATE.ws?.readyState === WebSocket.OPEN) {
          STATE.ws.send(JSON.stringify({ type: 'typing', is_typing: false }));
        }
      }, 2000);
    }

    // @mention autocomplete
    const cursor = input.selectionStart;
    const before = val.slice(0, cursor);
    const match = before.match(/@(\w*)$/);
    if (match) {
      showMentionDropdown(match[1]);
    } else {
      hideMentionDropdown();
    }
  });
}

async function sendMessage() {
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text && !selectedFile) return;
  if (!STATE.activeRoom) return;

  // --- GitHub AI Intercept ---
  const isAiTriggered = /^(@ai|\/ai|@pilotai|!ai)\b/i.test(text);
  if (!isAiTriggered && text && isGithubQuery(text)) {
    input.value = '';
    document.getElementById('send-btn').disabled = false;
    await showGithubCard(text);
    return;
  }

  input.value = '';
  document.getElementById('send-btn').disabled = true;

  if (selectedFile) {
    try {
      const room = STATE.activeRoom;
      const formData = new FormData();
      formData.append('text', text);
      formData.append('file', selectedFile);
      if (room.type === 'channel') {
        formData.append('channel', room.id);
        await api(`/channels/${room.id}/messages/`, {
          method: 'POST',
          body: formData,
        });
      } else {
        formData.append('dm', room.id);
        await api(`/dms/${room.id}/messages/`, {
          method: 'POST',
          body: formData,
        });
      }
      clearFilePreview();
      await loadMessages(room.roomId);
    } catch (err) {
      toast(err.message, 'error');
    }
  } else if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
    STATE.ws.send(JSON.stringify({
      type: 'chat_message',
      text,
      parent_id: STATE.thread?.id || null,
    }));
  } else {
    // Fallback to REST API
    try {
      const room = STATE.activeRoom;
      if (room.type === 'channel') {
        await api(`/channels/${room.id}/messages/`, { method: 'POST', body: { text } });
      } else {
        await api(`/dms/${room.id}/messages/`, { method: 'POST', body: { text, dm: room.id } });
      }
      await loadMessages(room.roomId);
    } catch (err) {
      toast(err.message, 'error');
    }
  }
}


// ── Voice-to-Text Speech Recognition ──────────────────────────────────────────

let voiceRecognition = null;
let isVoiceRecording = false;
let voiceSilenceTimeout = null;
let voiceCancelled = false;
let originalTextareaValue = '';

function toggleVoiceInput(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (isVoiceRecording) {
    stopSpeechRecognition();
  } else {
    startSpeechRecognition();
  }
}

function startSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    toast('Web Speech API is not supported in this browser. Please use Chrome, Edge, or Safari.', 'error');
    return;
  }

  const micBtn = document.getElementById('mic-btn');
  const voiceOverlay = document.getElementById('voice-overlay');
  const statusText = document.getElementById('voice-status-text');
  const textarea = document.getElementById('msg-input');

  voiceCancelled = false;
  originalTextareaValue = textarea.value;
  isVoiceRecording = true;

  micBtn.classList.add('recording');
  voiceOverlay.style.display = 'flex';
  statusText.innerHTML = 'Listening... Speak now';
  
  voiceRecognition = new SpeechRecognition();
  voiceRecognition.continuous = true;
  voiceRecognition.interimResults = true;
  voiceRecognition.lang = 'en-US';

  let finalTranscript = '';

  voiceRecognition.onstart = () => {
    console.log('Voice recognition started.');
    resetSilenceTimeout();
  };

  voiceRecognition.onresult = (event) => {
    let interimTranscript = '';
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interimTranscript += event.results[i][0].transcript;
      }
    }

    const currentText = (originalTextareaValue ? originalTextareaValue + ' ' : '') + finalTranscript + interimTranscript;
    textarea.value = currentText;
    autoResize(textarea);
    
    // Auto scroll message area if needed
    scrollToBottom();
    
    resetSilenceTimeout();
  };

  voiceRecognition.onerror = (event) => {
    console.error('Speech recognition error:', event.error);
    if (event.error === 'not-allowed') {
      toast('Microphone access denied. Please enable microphone permissions in your browser.', 'error');
    } else if (event.error === 'no-speech') {
      console.log('No speech detected.');
    } else {
      toast(`Speech recognition error: ${event.error}`, 'error');
    }
    cleanupVoiceUI();
  };

  voiceRecognition.onend = () => {
    console.log('Voice recognition ended.');
    if (voiceCancelled) {
      cleanupVoiceUI();
      return;
    }
    
    const text = textarea.value.trim();
    if (text) {
      sendVoiceToBackend(text);
    } else {
      cleanupVoiceUI();
      toast('No speech was detected.', 'default');
    }
  };

  voiceRecognition.start();
}

function resetSilenceTimeout() {
  clearTimeout(voiceSilenceTimeout);
  voiceSilenceTimeout = setTimeout(() => {
    if (isVoiceRecording) {
      console.log('Silence timeout reached. Automatically stopping.');
      stopSpeechRecognition();
    }
  }, 4000);
}

function stopSpeechRecognition(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (voiceRecognition && isVoiceRecording) {
    isVoiceRecording = false;
    clearTimeout(voiceSilenceTimeout);
    voiceRecognition.stop();
  }
}

function cancelSpeechRecognition(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (voiceRecognition) {
    voiceCancelled = true;
    isVoiceRecording = false;
    clearTimeout(voiceSilenceTimeout);
    voiceRecognition.abort();
  }
  const textarea = document.getElementById('msg-input');
  textarea.value = originalTextareaValue;
  autoResize(textarea);
  cleanupVoiceUI();
  toast('Voice input cancelled', 'default');
}

function cleanupVoiceUI() {
  isVoiceRecording = false;
  clearTimeout(voiceSilenceTimeout);
  const micBtn = document.getElementById('mic-btn');
  const voiceOverlay = document.getElementById('voice-overlay');
  if (micBtn) micBtn.classList.remove('recording');
  if (voiceOverlay) voiceOverlay.style.display = 'none';
}

async function sendVoiceToBackend(text) {
  const statusText = document.getElementById('voice-status-text');
  const overlay = document.getElementById('voice-overlay');
  
  if (statusText) {
    statusText.innerHTML = `PilotAI is thinking <span class="voice-loading-dot"></span><span class="voice-loading-dot"></span><span class="voice-loading-dot"></span>`;
  }
  
  try {
    const roomId = STATE.activeRoom?.roomId;
    
    const textarea = document.getElementById('msg-input');
    if (textarea) {
      textarea.value = '';
      autoResize(textarea);
      document.getElementById('send-btn').disabled = true;
    }
    
    const res = await api('/ai-chat/', {
      method: 'POST',
      body: {
        message: text,
        room_id: roomId || null
      }
    });
    
    console.log('Voice chat response:', res);
    
    if (!roomId) {
      toast(res.response, 'success');
    }
  } catch (err) {
    console.error('Error sending voice to backend:', err);
    toast(err.message || 'Failed to get response from PilotAI', 'error');
  } finally {
    cleanupVoiceUI();
  }
}


// ── GitHub AI Functions ──────────────────────────────────────────────────────

const GITHUB_TRIGGERS = [
  /\b(github|repo|repository)\b/i,
  /\b(project progress|project status|project update)\b/i,
  /\b(recent commits?|latest commits?|show commits?)\b/i,
  /\b(pull requests?|open prs?|in progress)\b/i,
  /\b(open issues?|bugs?)\b/i,
  /\b(show.{0,20}progress|what.{0,20}progress|how.{0,20}project)\b/i,
  /\b(contributors?|who.{0,10}working on)\b/i,
];

function isGithubQuery(text) {
  return GITHUB_TRIGGERS.some(re => re.test(text));
}

async function showGithubCard(queryText) {
  const container = document.getElementById('messages-container');
  const ws = STATE.workspace;

  // Show a loading placeholder bubble
  const loaderId = `gh-loader-${Date.now()}`;
  container.insertAdjacentHTML('beforeend', `
    <div class="message new-sender" id="${loaderId}">
      <div class="msg-avatar" style="background:#0d1117;font-size:18px;">🐙</div>
      <div class="msg-body">
        <div class="msg-header"><span class="msg-sender">Pilot AI · GitHub</span></div>
        <div class="msg-text" style="color:#616061;font-style:italic;">Fetching project data from GitHub…</div>
      </div>
    </div>
  `);
  scrollToBottom();

  try {
    const report = await api(`/github/report/?workspace=${ws.id}`);
    const loaderEl = document.getElementById(loaderId);
    if (loaderEl) loaderEl.innerHTML = buildGithubCardHTML(report);
    scrollToBottom();
  } catch (err) {
    const loaderEl = document.getElementById(loaderId);
    if (loaderEl) {
      const msg = err.message?.includes('No GitHub repo')
        ? '⚠️ No GitHub repo is linked to this workspace yet. An admin can link one from the sidebar.'
        : `❌ ${err.message}`;
      loaderEl.querySelector('.msg-text').textContent = msg;
      loaderEl.querySelector('.msg-text').style.cssText = 'color:#e01e5a;font-style:normal;';
    }
  }
}

function buildGithubCardHTML(r) {
  const commits = (r.commits || []).map(c => `
    <div class="github-commit">
      <span class="github-commit-sha">${c.sha}</span>
      <span class="github-commit-msg" title="${c.message}">${c.message}</span>
      <span class="github-commit-author">${c.author} · ${c.date}</span>
    </div>`).join('') || '<div style="color:#8b949e;font-size:12px;">No commits found.</div>';

  const prs = (r.pull_requests?.items || []).map(p =>
    `<span class="github-pill">#${p.number} ${p.title} <em style="color:#8b949e">by ${p.user}</em></span>`
  ).join('') || '<span style="color:#8b949e;font-size:12px;">No open PRs</span>';

  const issues = (r.issues?.items || []).map(i =>
    `<span class="github-pill">#${i.number} ${i.title}</span>`
  ).join('') || '<span style="color:#8b949e;font-size:12px;">No open issues 🎉</span>';

  const contributors = (r.contributors || []).map(c =>
    `<span class="github-pill">@${c.login} (${c.contributions})</span>`
  ).join('');

  return `
    <div class="msg-avatar" style="background:#0d1117;font-size:18px;">🐙</div>
    <div class="msg-body">
      <div class="msg-header"><span class="msg-sender">Pilot AI · GitHub</span></div>
      <div class="github-card">
        <div class="github-card-header">
          <div style="font-size:28px;">📦</div>
          <div>
            <h3>${r.full_name}</h3>
            <p>${r.description || 'No description'} · <strong>${r.language}</strong> · Branch: <strong>${r.default_branch}</strong></p>
          </div>
        </div>
        <div class="github-card-stats">
          <div class="github-stat"><div class="github-stat-val">⭐ ${r.stars}</div><div class="github-stat-label">Stars</div></div>
          <div class="github-stat"><div class="github-stat-val">🍴 ${r.forks}</div><div class="github-stat-label">Forks</div></div>
          <div class="github-stat"><div class="github-stat-val">🐛 ${r.issues?.count ?? r.open_issues_count}</div><div class="github-stat-label">Issues</div></div>
          <div class="github-stat"><div class="github-stat-val">🔀 ${r.pull_requests?.count ?? 0}</div><div class="github-stat-label">Open PRs</div></div>
        </div>
        <div class="github-section"><div class="github-section-title">Recent Commits</div>${commits}</div>
        <div class="github-section"><div class="github-section-title">Open Pull Requests (${r.pull_requests?.count ?? 0})</div>${prs}</div>
        <div class="github-section"><div class="github-section-title">Open Issues (${r.issues?.count ?? 0})</div>${issues}</div>
        ${contributors ? `<div class="github-section"><div class="github-section-title">Top Contributors</div>${contributors}</div>` : ''}
        <div class="github-card-footer">
          <span>Last push: ${r.last_push || 'unknown'}</span>
          <a href="${r.url}" target="_blank">View on GitHub →</a>
        </div>
      </div>
    </div>
  `;
}

function openGithubModal() {
  const modal = document.getElementById('github-modal');
  const input = document.getElementById('github-repo-input');
  input.value = STATE.workspace?.github_repo || '';
  document.getElementById('github-modal-status').textContent = '';
  modal.classList.add('visible');
  setTimeout(() => input.focus(), 100);
}

function closeGithubModal() {
  document.getElementById('github-modal').classList.remove('visible');
}

async function saveGithubRepo() {
  const repo = document.getElementById('github-repo-input').value.trim();
  const status = document.getElementById('github-modal-status');
  if (!repo || !repo.includes('/')) {
    status.textContent = '⚠️ Please use owner/repo-name format.';
    status.style.color = '#e01e5a';
    return;
  }
  status.textContent = 'Saving…';
  status.style.color = '#616061';
  try {
    const result = await api(`/workspaces/${STATE.workspace.id}/set-repo/`, {
      method: 'PATCH',
      body: { github_repo: repo }
    });
    STATE.workspace.github_repo = result.github_repo;
    localStorage.setItem('workspace', JSON.stringify(STATE.workspace));
    const label = document.getElementById('github-link-label');
    if (label) label.textContent = `🐙 ${repo}`;
    toast(`GitHub repo linked: ${repo}`, 'success');
    closeGithubModal();
  } catch (err) {
    status.textContent = `❌ ${err.message}`;
    status.style.color = '#e01e5a';
  }
}

// ── Reactions & Emoji ──────────────────────────────────────────────────────────


const EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🎉', '🔥', '👀', '🙌', '✅', '🚀', '💯', '😍', '🤔', '👏'];

function toggleEmojiPicker(msgId) {
  const existing = document.getElementById('emoji-picker-popup');
  if (existing) {
    if (existing.dataset.for == msgId) {
      existing.remove();
      return;
    }
    existing.remove();
  }

  const msgEl = document.querySelector(`[data-id="${msgId}"]`);
  if (!msgEl) return;

  const picker = document.createElement('div');
  picker.id = 'emoji-picker-popup';
  picker.className = 'emoji-picker visible';
  picker.dataset.for = msgId;
  picker.innerHTML = EMOJIS.map(e => `
    <span class="emoji-opt" onclick="sendReaction(${msgId}, '${e}')">${e}</span>
  `).join('');

  msgEl.appendChild(picker);

  document.addEventListener('click', function removeOnClick(e) {
    if (!picker.contains(e.target)) {
      picker.remove();
      document.removeEventListener('click', removeOnClick);
    }
  }, { capture: true, once: false });
}

async function sendReaction(msgId, emoji) {
  document.getElementById('emoji-picker-popup')?.remove();
  if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
    STATE.ws.send(JSON.stringify({ type: 'reaction', message_id: msgId, emoji }));
  } else {
    try {
      await api(`/channels/${STATE.activeRoom.id}/messages/${msgId}/react/`, {
        method: 'POST',
        body: { emoji }
      });
      await loadMessages(STATE.activeRoom.roomId);
    } catch (err) {
      toast(err.message, 'error');
    }
  }
}

async function deleteMessage(msgId) {
  if (!confirm('Delete this message?')) return;
  try {
    await api(`/channels/${STATE.activeRoom.id}/messages/${msgId}/`, { method: 'DELETE' });
    await loadMessages(STATE.activeRoom.roomId);
    toast('Message deleted');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function pinMessage(msgId) {
  try {
    await api(`/channels/${STATE.activeRoom.id}/messages/${msgId}/pin/`, { method: 'POST' });
    toast('Message pinned! 📌', 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function unpinMessage(msgId) {
  try {
    await api(`/channels/${STATE.activeRoom.id}/messages/${msgId}/unpin/`, { method: 'POST' });
    toast('Message unpinned', 'success');
    showPinsModal();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function showNotesModal() {
  const room = STATE.activeRoom;
  if (room?.type !== 'channel') {
    toast('Notes only available in channels', 'error');
    return;
  }
  document.getElementById('channel-notes-text').value = room.data?.notes || '';
  document.getElementById('notes-modal').classList.add('visible');
}

async function saveChannelNotes() {
  const room = STATE.activeRoom;
  if (room?.type !== 'channel') return;
  const notes = document.getElementById('channel-notes-text').value;
  try {
    const updated = await api(`/workspaces/${STATE.workspace.id}/channels/${room.id}/`, {
      method: 'PATCH',
      body: { notes }
    });
    room.data.notes = updated.notes;
    document.getElementById('notes-modal').classList.remove('visible');
    toast('Notes saved! 📝', 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Mention Autocomplete ──────────────────────────────────────────────────────

function showMentionDropdown(partial) {
  const dropdown = document.getElementById('mention-dropdown');
  const matches = STATE.members.filter(m => {
    const name = (m.profile?.display_name || m.username).toLowerCase();
    return name.includes(partial.toLowerCase()) || m.username.toLowerCase().includes(partial.toLowerCase());
  }).slice(0, 5);

  if (matches.length === 0) {
    dropdown.classList.remove('visible');
    return;
  }

  dropdown.innerHTML = matches.map(m => {
    const displayName = m.profile?.display_name || m.username;
    const color = m.profile?.avatar_color || getAvatarColor(displayName);
    return `
      <div class="mention-option" onclick="insertMention('${m.username}')">
        <div class="dm-avatar" style="background:${color};width:24px;height:24px;font-size:11px">
          ${getInitials(displayName)}
        </div>
        <span class="m-name">${displayName}</span>
        <span class="m-username">@${m.username}</span>
      </div>
    `;
  }).join('');
  dropdown.classList.add('visible');
}

function hideMentionDropdown() {
  document.getElementById('mention-dropdown').classList.remove('visible');
}

function insertMention(username) {
  const input = document.getElementById('msg-input');
  const val = input.value;
  const cursor = input.selectionStart;
  const before = val.slice(0, cursor).replace(/@\w*$/, `@${username} `);
  const after = val.slice(cursor);
  input.value = before + after;
  input.focus();
  hideMentionDropdown();
}

// ── Threads ───────────────────────────────────────────────────────────────────

async function openThread(messageId) {
  const panel = document.getElementById('thread-panel');
  STATE.thread = { id: messageId };

  try {
    const replies = await api(`/channels/${STATE.activeRoom.id}/messages/${messageId}/thread/`);
    const parent = (STATE.messages[STATE.activeRoom.roomId] || []).find(m => m.id == messageId);

    const container = document.getElementById('thread-messages');
    container.innerHTML = '';

    if (parent) {
      container.insertAdjacentHTML('beforeend', `
        <div style="padding:8px 12px;border-bottom:1px solid #e8e8e8;margin-bottom:8px;">
          ${renderMessageHTML(parent, true)}
        </div>
      `);
    }

    replies.forEach(r => {
      container.insertAdjacentHTML('beforeend', renderMessageHTML(r, true));
    });

    panel.classList.add('open');
  } catch (err) {
    toast(err.message, 'error');
  }
}

function closeThread() {
  document.getElementById('thread-panel').classList.remove('open');
  STATE.thread = null;
}

// ── Channel Modals ────────────────────────────────────────────────────────────

async function openCreateChannelModal() {
  document.getElementById('create-channel-modal').classList.add('visible');
  document.getElementById('new-channel-name').focus();
  document.getElementById('new-channel-name').value = '';
  document.getElementById('new-channel-desc').value = '';

  const membersList = document.getElementById('channel-member-selection');
  membersList.innerHTML = '<div style="color:#616061;">Loading...</div>';

  try {
    const members = await api(`/workspaces/${STATE.workspace.id}/members/`);
    membersList.innerHTML = '';
    members.forEach(member => {
      if (member.id === STATE.user.id) return;
      const p = member.profile || {};
      const lvl = p.employee_level ? p.employee_level.charAt(0).toUpperCase() + p.employee_level.slice(1) : 'N/A';
      membersList.innerHTML += `
        <div style="display:flex; align-items:center; justify-content:space-between; padding: 6px; border-bottom: 1px solid #f0f0f0;">
          <div>
            <strong>${p.display_name || member.username}</strong><br>
            <small style="color:#616061;">Level: ${lvl} | Strong in: ${p.skill_strength || 'None'} | Reliability: ${p.reliability || 0}%</small>
          </div>
          <input type="checkbox" value="${member.id}" class="channel-member-checkbox" checked>
        </div>
      `;
    });
    if (members.length <= 1) {
      membersList.innerHTML = '<div style="color:#616061;">No other members to select.</div>';
    }
  } catch(e) {
    membersList.innerHTML = '<div style="color:#e01e5a;">Failed to load members.</div>';
  }
}

function closeCreateChannelModal() {
  document.getElementById('create-channel-modal').classList.remove('visible');
}

async function createChannel() {
  const name = document.getElementById('new-channel-name').value.trim().toLowerCase().replace(/\s+/g, '-');
  const description = document.getElementById('new-channel-desc').value.trim();
  const type = document.getElementById('new-channel-type').value;
  const isProject = document.getElementById('new-channel-is-project').checked;

  if (!name) return toast('Channel name required', 'error');

  const checkboxes = document.querySelectorAll('.channel-member-checkbox:checked');
  const selectedMembers = Array.from(checkboxes).map(cb => parseInt(cb.value));

  try {
    const ch = await api(`/workspaces/${STATE.workspace.id}/channels/`, {
      method: 'POST',
      body: { 
        name, 
        description, 
        channel_type: type, 
        members: selectedMembers,
        is_project_channel: isProject
      }
    });
    STATE.channels.push(ch);
    renderChannelList();
    closeCreateChannelModal();
    document.getElementById('new-channel-is-project').checked = false;
    openChannel(ch);
    toast(`Channel #${ch.name} created!`, 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── AI Channel Summary ────────────────────────────────────────────────────────

async function loadChannelSummary(channelId) {
  try {
    const summary = await api(`/workspaces/${STATE.workspace.id}/channels/${channelId}/summary/`);
    const badge = document.getElementById('ai-summary-badge');
    if (summary.topics?.length > 0) {
      badge.textContent = `🤖 AI Topics: ${summary.topics.slice(0, 3).join(', ')}`;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  } catch (err) {
    // Silently fail
  }
}

// ── Search ────────────────────────────────────────────────────────────────────

let searchTimeout = null;

function initSearch() {
  const input = document.getElementById('search-input');
  const results = document.getElementById('search-results');

  input.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    const q = input.value.trim();
    if (!q) {
      results.classList.remove('visible');
      return;
    }
    searchTimeout = setTimeout(() => doSearch(q), 300);
  });

  input.addEventListener('focus', () => {
    if (input.value.trim()) results.classList.add('visible');
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !results.contains(e.target)) {
      results.classList.remove('visible');
    }
  });
}

async function doSearch(query) {
  const results = document.getElementById('search-results');
  results.innerHTML = '<div style="padding:12px 16px;color:#616061;font-size:13px;">Searching with AI…</div>';
  results.classList.add('visible');

  try {
    const data = await api(`/ai/search/?q=${encodeURIComponent(query)}&workspace=${STATE.workspace.id}`);
    if (data.length === 0) {
      results.innerHTML = '<div style="padding:12px 16px;color:#616061;font-size:13px;">No results found.</div>';
      return;
    }
    results.innerHTML = data.slice(0, 8).map(msg => {
      const highlighted = msg.text.replace(
        new RegExp(query, 'gi'),
        m => `<mark>${m}</mark>`
      );
      return `
        <div class="search-result-item" onclick="jumpToMessage('${msg.channel_name}', ${msg.id})">
          <div class="sr-channel"># ${msg.channel_name || 'direct message'} <span class="sr-ai-badge">AI Search</span></div>
          <div class="sr-text">${highlighted.slice(0, 120)}</div>
          <div class="sr-sender">${msg.sender?.display_name || msg.sender?.username} · ${formatTime(msg.created_at)}</div>
        </div>
      `;
    }).join('');
  } catch (err) {
    results.innerHTML = `<div style="padding:12px 16px;color:#e01e5a;font-size:13px;">Search error: ${err.message}</div>`;
  }
}

function jumpToMessage(channelName, msgId) {
  document.getElementById('search-results').classList.remove('visible');
  const ch = STATE.channels.find(c => c.name === channelName);
  if (ch) openChannel(ch);
  setTimeout(() => {
    const el = document.querySelector(`[data-id="${msgId}"]`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.style.background = '#fff3cd';
      setTimeout(() => el.style.background = '', 2000);
    }
  }, 500);
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function initWebSocket() {}

function connectWebSocket(roomId) {
  if (STATE.ws) {
    STATE.ws.close();
    STATE.ws = null;
  }
  if (STATE.wsReconnectTimer) {
    clearInterval(STATE.wsReconnectTimer);
    STATE.wsReconnectTimer = null;
  }

  const url = `${WS_BASE}/${roomId}/?token=${STATE.token}`;
  
  try {
    const ws = new WebSocket(url);
    STATE.ws = ws;

    ws.onopen = () => {
      console.log('WebSocket connected:', roomId);
      document.getElementById('ws-status').textContent = '🟢 Live';
      document.getElementById('ws-status').style.color = '#2bac76';
    };

    ws.onclose = () => {
      if (STATE.ws === ws) {
        document.getElementById('ws-status').textContent = '🔴 Offline';
        document.getElementById('ws-status').style.color = '#e01e5a';
        STATE.ws = null;
      }
      // Continuously try to reconnect every 5 seconds for the active room only
      if (!STATE.wsReconnectTimer) {
        STATE.wsReconnectTimer = setInterval(() => {
          if (STATE.activeRoom?.roomId === roomId && !STATE.ws) {
            connectWebSocket(roomId);
          } else if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
            clearInterval(STATE.wsReconnectTimer);
            STATE.wsReconnectTimer = null;
          }
        }, 5000);
      }
    };

    ws.onerror = () => {
      if (STATE.ws === ws) {
        document.getElementById('ws-status').textContent = '🔴 Offline';
        STATE.ws = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data, roomId);
      } catch (e) {
        console.error('WS parse error:', e);
      }
    };
  } catch(e) {
    console.log('WebSocket not available, using REST only');
  }
}

function handleWebSocketMessage(data, roomId) {
  switch (data.type) {
    case 'chat_message': {
      const msg = data.message;
      if (STATE.activeRoom?.roomId === roomId) {
        // Normalize sender structure
        if (!msg.sender) {
          msg.sender = {
            id: msg.sender_id,
            username: msg.sender_username,
            profile: {
              display_name: msg.sender_display_name,
              avatar_color: msg.avatar_color,
            }
          };
        }
        msg.reactions = msg.reactions || [];
        msg.reply_count = msg.reply_count || 0;
        addMessageToView(roomId, msg);
      }
      break;
    }
    case 'typing': {
      if (STATE.activeRoom?.roomId === roomId) {
        showTypingIndicator(data.username, data.is_typing);
      }
      break;
    }
    case 'reaction_update': {
      if (STATE.activeRoom?.roomId === roomId) {
        loadMessages(roomId); // Re-render (simple approach)
      }
      break;
    }
    case 'presence': {
      updateUserPresence(data.user_id, data.status);
      break;
    }
    case 'milestone_update': {
      const chanId = parseInt(roomId.split('_')[1]);
      const chan = STATE.channels.find(c => c.id === chanId);
      if (chan) {
        // Initialize milestones if undefined
        chan.milestones = chan.milestones || [];
        const matched = chan.milestones.find(m => m.id === data.milestone_id);
        if (matched) {
          matched.is_completed = true;
          matched.completed_at = new Date().toISOString();
        }
        
        // If it is the active room, re-render the banner
        if (STATE.activeRoom?.type === 'channel' && STATE.activeRoom.id === chanId) {
          renderProjectMilestones(chan);
        }
      }
      break;
    }
  }
}

let typingTimeouts = {};

function showTypingIndicator(username, isTyping) {
  const el = document.getElementById('typing-indicator');
  if (isTyping) {
    typingTimeouts[username] = setTimeout(() => {
      delete typingTimeouts[username];
      updateTypingText();
    }, 3000);
    typingTimeouts[username + '_name'] = username;
  } else {
    clearTimeout(typingTimeouts[username]);
    delete typingTimeouts[username];
  }
  updateTypingText();
}

function updateTypingText() {
  const el = document.getElementById('typing-indicator');
  const typers = Object.keys(typingTimeouts).filter(k => !k.endsWith('_name'));
  if (typers.length === 0) {
    el.innerHTML = '';
  } else if (typers.length === 1) {
    el.innerHTML = `<strong>${typers[0]}</strong> is typing<span class="typing-dots"><span></span><span></span><span></span></span>`;
  } else {
    el.innerHTML = `<strong>${typers.slice(0, -1).join(', ')}</strong> and <strong>${typers[typers.length-1]}</strong> are typing<span class="typing-dots"><span></span><span></span><span></span></span>`;
  }
}

function updateUserPresence(userId, status) {
  const el = document.querySelector(`#dm-item-${userId} .status-dot`);
  if (el) {
    el.className = `status-dot status-${status}`;
  }
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  if (STATE.token && STATE.workspace) {
    showApp();
  } else if (STATE.token) {
    showWorkspacePage();
  } else {
    showAuthPage();
  }
});
