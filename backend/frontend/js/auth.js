// ── Authentication ──────────────────────────────────────────────────────────

function initAuth() {
  document.querySelectorAll('.auth-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(`form-${tab.dataset.tab}`)?.classList.add('active');
    });
  });

  document.getElementById('login-btn')?.addEventListener('click', handleLogin);
  document.getElementById('login-password')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') handleLogin();
  });
  document.getElementById('register-btn')?.addEventListener('click', handleRegister);
  document.getElementById('register-password')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') handleRegister();
  });
}

async function handleLogin() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.classList.remove('visible');

  if (!username || !password) {
    errEl.textContent = 'Please enter username and password.';
    errEl.classList.add('visible');
    return;
  }

  const btn = document.getElementById('login-btn');
  btn.textContent = 'Signing in…';
  btn.disabled = true;

  try {
    const data = await api('/auth/login/', {
      method: 'POST',
      body: { username, password },
    });
    STATE.token = data.token;
    STATE.user = data.user;
    localStorage.setItem('token', data.token);
    localStorage.setItem('user', JSON.stringify(data.user));
    showWorkspacePage();
  } catch (err) {
    errEl.textContent = err.message || 'Login failed. Check your credentials.';
    errEl.classList.add('visible');
  } finally {
    btn.textContent = 'Sign In';
    btn.disabled = false;
  }
}

async function handleRegister() {
  const username = document.getElementById('reg-username').value.trim();
  const email = document.getElementById('reg-email').value.trim();
  const display_name = document.getElementById('reg-displayname').value.trim();
  const password = document.getElementById('reg-password').value;
  const errEl = document.getElementById('register-error');
  errEl.classList.remove('visible');

  if (!username || !password) {
    errEl.textContent = 'Username and password are required.';
    errEl.classList.add('visible');
    return;
  }

  const btn = document.getElementById('register-btn');
  btn.textContent = 'Creating account…';
  btn.disabled = true;

  try {
    const data = await api('/auth/register/', {
      method: 'POST',
      body: { username, email, password, display_name },
    });
    STATE.token = data.token;
    STATE.user = data.user;
    localStorage.setItem('token', data.token);
    localStorage.setItem('user', JSON.stringify(data.user));
    toast('Account created! Welcome 🎉', 'success');
    showWorkspacePage();
  } catch (err) {
    errEl.textContent = err.message || 'Registration failed.';
    errEl.classList.add('visible');
  } finally {
    btn.textContent = 'Create Account';
    btn.disabled = false;
  }
}

function logout() {
  api('/auth/logout/', { method: 'POST' }).catch(() => {});
  STATE.token = null;
  STATE.user = null;
  STATE.workspace = null;
  localStorage.clear();
  if (STATE.ws) STATE.ws.close();
  location.reload();
}
