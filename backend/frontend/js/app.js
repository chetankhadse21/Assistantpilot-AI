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
    if (workspaces.length === 0) {
      list.innerHTML = '<p style="color:#616061;font-size:13px;">No workspaces yet. Create one below!</p>';
      return;
    }
    list.innerHTML = workspaces.map(ws => `
      <div class="workspace-item" onclick="selectWorkspace(${ws.id}, '${ws.name}')">
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

function selectWorkspace(id, name) {
  const ws = { id, name };
  STATE.workspace = ws;
  localStorage.setItem('workspace', JSON.stringify(ws));
  showApp();
}

async function createWorkspace() {
  const name = document.getElementById('ws-name').value.trim();
  if (!name) return toast('Please enter a workspace name', 'error');
  try {
    const ws = await api('/workspaces/', { method: 'POST', body: { name } });
    selectWorkspace(ws.id, ws.name);
    toast(`Workspace "${ws.name}" created! 🎉`, 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── App Init ─────────────────────────────────────────────────────────────────

async function initApp() {
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

  await Promise.all([loadChannels(), loadDMs(), loadMembers()]);
  initMessageInput();
  initSearch();
  initWebSocket();
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
  document.getElementById('channel-description').textContent = channel.description || '';
  document.getElementById('msg-placeholder').textContent = `Message #${channel.name}`;

  closeThread();
  await loadMessages(roomId);
  connectWebSocket(roomId);
  loadChannelSummary(channel.id);
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
  if (STATE.dms.length === 0) {
    list.innerHTML = '<div style="padding:4px 16px;color:rgba(255,255,255,0.4);font-size:12px;">No DMs yet</div>';
    return;
  }
  list.innerHTML = STATE.dms.map(dm => {
    const other = dm.participants.find(p => p.id !== STATE.user.id) || dm.participants[0];
    const profile = other.profile || {};
    const name = profile.display_name || other.username;
    const color = profile.avatar_color || getAvatarColor(name);
    const status = profile.status || 'offline';
    return `
      <div class="dm-item ${STATE.activeRoom?.id == dm.id ? 'active' : ''}"
           id="dm-item-${dm.id}"
           onclick="openDM(${dm.id})">
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

  document.getElementById('channel-name').textContent = name;
  document.getElementById('channel-description').textContent = '';
  document.getElementById('msg-placeholder').textContent = `Message ${name}`;

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
    const members = await api(`/workspaces/${STATE.workspace.id}/members/`);
    STATE.members = members.map(m => m.user);
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

  const threadHTML = msg.reply_count > 0 ? `
    <div class="thread-indicator" data-thread="${msg.id}">
      <span>${msg.reply_count} repl${msg.reply_count !== 1 ? 'ies' : 'y'}</span>
      <span style="color:#616061;font-size:12px;">View thread</span>
    </div>
  ` : '';

  return `
    <div class="message ${isNewSender ? 'new-sender' : ''}" data-id="${msg.id}">
      <div class="msg-avatar ${!isNewSender ? 'hidden' : ''}" style="background:${color}">
        ${getInitials(displayName)}
      </div>
      <div class="msg-body">
        ${isNewSender ? `
          <div class="msg-header">
            <span class="msg-sender">${displayName}</span>
            <span class="msg-time">${formatTime(msg.created_at)}</span>
            ${intentBadge(msg.ai_intent)}
          </div>
        ` : ''}
        <div class="msg-text ${msg.is_deleted ? 'deleted' : ''}">
          ${msg.is_deleted ? 'This message was deleted.' : renderMsgText(msg.text)}
          ${msg.is_edited ? '<span class="msg-edited">(edited)</span>' : ''}
        </div>
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
    document.getElementById('send-btn').disabled = !val.trim();

    // Typing indicator
    if (STATE.ws && STATE.activeRoom) {
      STATE.ws.send(JSON.stringify({ type: 'typing', is_typing: true }));
      clearTimeout(typingTimeout);
      typingTimeout = setTimeout(() => {
        STATE.ws?.send(JSON.stringify({ type: 'typing', is_typing: false }));
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
  if (!text || !STATE.activeRoom) return;

  input.value = '';
  document.getElementById('send-btn').disabled = true;

  if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
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

function openCreateChannelModal() {
  document.getElementById('create-channel-modal').classList.add('visible');
  document.getElementById('new-channel-name').focus();
}

function closeCreateChannelModal() {
  document.getElementById('create-channel-modal').classList.remove('visible');
  document.getElementById('new-channel-name').value = '';
  document.getElementById('new-channel-desc').value = '';
}

async function createChannel() {
  const name = document.getElementById('new-channel-name').value.trim().toLowerCase().replace(/\s+/g, '-');
  const description = document.getElementById('new-channel-desc').value.trim();
  const type = document.getElementById('new-channel-type').value;

  if (!name) return toast('Channel name required', 'error');

  try {
    const ch = await api(`/workspaces/${STATE.workspace.id}/channels/`, {
      method: 'POST',
      body: { name, description, channel_type: type }
    });
    STATE.channels.push(ch);
    renderChannelList();
    closeCreateChannelModal();
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

  const url = `${WS_BASE}/${roomId}/?token=${STATE.token}`;
  const ws = new WebSocket(url);
  STATE.ws = ws;

  ws.onopen = () => {
    console.log('WebSocket connected:', roomId);
    document.getElementById('ws-status').textContent = '🟢 Live';
    document.getElementById('ws-status').style.color = '#2bac76';
  };

  ws.onclose = () => {
    document.getElementById('ws-status').textContent = '🔴 Offline';
    document.getElementById('ws-status').style.color = '#e01e5a';
    // Reconnect after 3s
    setTimeout(() => {
      if (STATE.activeRoom?.roomId === roomId) connectWebSocket(roomId);
    }, 3000);
  };

  ws.onerror = () => {
    document.getElementById('ws-status').textContent = '🟡 Error';
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleWebSocketMessage(data, roomId);
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };
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
