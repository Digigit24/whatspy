// components/scripts.js

// Global State
let conversations = [];
let contacts = [];
let groups = [];
let currentChat = null;
let currentMessages = [];
let currentTab = 'chats';
let autoRefreshInterval = null;
let statsInterval = null;
let contactsToImport = [];

// ═══════════════════════════════════════════
// UTILITY FUNCTIONS
// ═══════════════════════════════════════════

function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideIn 0.3s ease-out reverse';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function formatTime(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;
  
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm';
  if (diff < 86400000) return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  if (diff < 604800000) return date.toLocaleDateString('en-US', { weekday: 'short' });
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ═══════════════════════════════════════════
// TAB MANAGEMENT
// ═══════════════════════════════════════════

function switchTab(tab) {
  currentTab = tab;
  
  // Update active button
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  event.target.classList.add('active');
  
  // Show/hide action buttons
  const actionButtons = document.getElementById('actionButtons');
  const btnAddContact = document.getElementById('btnAddContact');
  const btnImportContacts = document.getElementById('btnImportContacts');
  const btnCreateGroup = document.getElementById('btnCreateGroup');
  
  // Hide all action buttons first
  btnAddContact.style.display = 'none';
  btnImportContacts.style.display = 'none';
  btnCreateGroup.style.display = 'none';
  actionButtons.style.display = 'none';
  
  // Show relevant buttons based on tab
  if (tab === 'contacts') {
    actionButtons.style.display = 'flex';
    btnAddContact.style.display = 'block';
    btnImportContacts.style.display = 'block';
  } else if (tab === 'groups') {
    actionButtons.style.display = 'flex';
    btnCreateGroup.style.display = 'block';
  }
  
  // Load appropriate data
  if (tab === 'chats') {
    loadConversations();
  } else if (tab === 'contacts') {
    loadContacts();
  } else if (tab === 'groups') {
    loadGroups();
  }
}

// ═══════════════════════════════════════════
// DATA LOADING
// ═══════════════════════════════════════════

async function loadConversations() {
  try {
    const response = await fetch('/api/conversations');
    conversations = await response.json();
    renderConversations();
  } catch (error) {
    console.error('Failed to load conversations:', error);
    showToast('Failed to load conversations', 'error');
  }
}

async function loadContacts() {
  try {
    const response = await fetch('/api/contacts');
    contacts = await response.json();
    renderContacts();
  } catch (error) {
    console.error('Failed to load contacts:', error);
    showToast('Failed to load contacts', 'error');
  }
}

async function loadGroups() {
  try {
    const response = await fetch('/api/groups');
    groups = await response.json();
    renderGroups();
  } catch (error) {
    console.error('Failed to load groups:', error);
    showToast('Failed to load groups', 'error');
  }
}

async function loadStats() {
  try {
    const response = await fetch('/api/stats');
    const stats = await response.json();
    
    document.getElementById('statTotal').textContent = stats.total_messages || 0;
    document.getElementById('statIncoming').textContent = stats.incoming_messages || 0;
    document.getElementById('statOutgoing').textContent = stats.outgoing_messages || 0;
  } catch (error) {
    console.error('Failed to load stats:', error);
  }
}

// ═══════════════════════════════════════════
// RENDERING FUNCTIONS
// ═══════════════════════════════════════════

function renderConversations(filter = '') {
  const listEl = document.getElementById('conversationsList');
  
  if (conversations.length === 0) {
    listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">No conversations yet</div>';
    return;
  }

  const filtered = conversations.filter(conv => 
    conv.name.toLowerCase().includes(filter.toLowerCase()) ||
    conv.phone.includes(filter)
  );

  listEl.innerHTML = filtered.map(conv => `
    <div class="conversation-item ${currentChat === conv.phone ? 'active' : ''}" 
         onclick="openChat('${conv.phone}', '${escapeHtml(conv.name)}')">
      <div class="conversation-header">
        <span class="conversation-name">${escapeHtml(conv.name)}</span>
        <span class="conversation-time">${formatTime(conv.last_timestamp)}</span>
      </div>
      <div class="conversation-preview">
        ${escapeHtml(conv.last_message || 'No messages')}
        ${conv.message_count > 0 ? `<span class="unread-badge">${conv.message_count}</span>` : ''}
      </div>
    </div>
  `).join('');
}

function renderContacts(filter = '') {
  const listEl = document.getElementById('conversationsList');
  
  if (contacts.length === 0) {
    listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">No contacts yet<br><small style="color: #555;">Click "Add Contact" to get started</small></div>';
    return;
  }

  const filtered = contacts.filter(contact => 
    contact.name?.toLowerCase().includes(filter.toLowerCase()) ||
    contact.phone.includes(filter)
  );

  listEl.innerHTML = filtered.map(contact => `
    <div class="conversation-item" onclick="openChat('${contact.phone}', '${escapeHtml(contact.name || contact.phone)}')">
      <div class="conversation-header">
        <span class="conversation-name">${escapeHtml(contact.name || contact.phone)}</span>
      </div>
      <div class="conversation-preview">
        ${contact.phone}
        ${contact.is_business ? ' • 💼 Business' : ''}
        ${contact.labels && contact.labels.length > 0 ? `<br><small style="color: #888;">🏷️ ${contact.labels.join(', ')}</small>` : ''}
        ${contact.groups && contact.groups.length > 0 ? `<br><small style="color: #0f0;">👥 ${contact.groups.join(', ')}</small>` : ''}
      </div>
      <div class="item-actions">
        <button class="item-action-btn" onclick="event.stopPropagation(); openEditContactModal('${contact.phone}')">✏️ Edit</button>
        <button class="item-action-btn" onclick="event.stopPropagation(); deleteContact('${contact.phone}')">🗑️</button>
      </div>
    </div>
  `).join('');
}

function renderGroups(filter = '') {
  const listEl = document.getElementById('conversationsList');
  
  if (groups.length === 0) {
    listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">No groups yet<br><small style="color: #555;">Click "Create Group" to get started</small></div>';
    return;
  }

  const filtered = groups.filter(group => 
    group.name.toLowerCase().includes(filter.toLowerCase())
  );

  listEl.innerHTML = filtered.map(group => `
    <div class="conversation-item">
      <div class="conversation-header">
        <span class="conversation-name">👥 ${escapeHtml(group.name)}</span>
      </div>
      <div class="conversation-preview">
        ${group.participant_count} participants
        ${group.is_active ? '' : ' • ⚠️ Inactive'}
      </div>
      <div class="item-actions">
        <button class="item-action-btn" onclick="event.stopPropagation(); openEditGroupModal('${group.group_id}')">✏️ Edit</button>
        <button class="item-action-btn" onclick="event.stopPropagation(); deleteGroup('${group.group_id}')">🗑️</button>
      </div>
    </div>
  `).join('');
}

// ═══════════════════════════════════════════
// CHAT FUNCTIONS
// ═══════════════════════════════════════════

async function openChat(phone, name) {
  currentChat = phone;
  
  // Update UI
  document.getElementById('chatHeader').style.display = 'flex';
  document.getElementById('messageInputContainer').style.display = 'flex';
  document.getElementById('chatTitle').textContent = name;
  document.getElementById('chatPhone').textContent = phone;
  
  // Highlight active conversation
  if (currentTab === 'chats') {
    renderConversations(document.getElementById('searchBox').value);
  }
  
  // Load messages
  await loadMessages(phone);
  
  // Start auto-refresh
  if (autoRefreshInterval) clearInterval(autoRefreshInterval);
  autoRefreshInterval = setInterval(() => loadMessages(phone, true), 3000);
}

async function loadMessages(phone, silent = false) {
  try {
    const response = await fetch(`/api/conversations/${phone}`);
    const data = await response.json();
    currentMessages = data.messages || [];
    renderMessages(silent);
  } catch (error) {
    console.error('Failed to load messages:', error);
    if (!silent) showToast('Failed to load messages', 'error');
  }
}

function renderMessages(silent = false) {
  const container = document.getElementById('messagesContainer');
  const wasAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 50;
  
  if (currentMessages.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">💬</div>
        <h3>No messages yet</h3>
        <p>Start the conversation by sending a message</p>
      </div>
    `;
    return;
  }

  container.innerHTML = currentMessages.map(msg => {
    const typeLabel = msg.type && msg.type !== 'text' ? `<div class="message-type">${msg.type.toUpperCase()}</div>` : '';
    return `
      <div class="message ${msg.direction}">
        ${typeLabel}
        <div>${escapeHtml(msg.text || '(media)')}</div>
        <div class="message-time">${formatTime(msg.timestamp)}</div>
      </div>
    `;
  }).join('');

  if (!silent || wasAtBottom) {
    container.scrollTop = container.scrollHeight;
  }
}

async function sendMessage() {
  const input = document.getElementById('messageInput');
  const button = document.getElementById('sendButton');
  const text = input.value.trim();
  
  if (!text || !currentChat) return;

  button.disabled = true;
  input.disabled = true;

  try {
    const response = await fetch('/api/send/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: currentChat, text: text })
    });

    if (response.ok) {
      input.value = '';
      input.style.height = 'auto';
      await loadMessages(currentChat, true);
      await loadConversations();
      showToast('Message sent successfully');
    } else {
      const error = await response.json();
      showToast(error.detail || 'Failed to send message', 'error');
    }
  } catch (error) {
    console.error('Send failed:', error);
    showToast('Failed to send message', 'error');
  } finally {
    button.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

async function refreshChat() {
  if (currentChat) {
    await loadMessages(currentChat);
    await loadConversations();
    await loadStats();
    showToast('Refreshed');
  }
}

async function clearChat() {
  if (!currentChat) return;
  
  if (!confirm('Are you sure you want to delete all messages in this conversation?')) {
    return;
  }
  
  try {
    const response = await fetch(`/api/conversations/${currentChat}`, { method: 'DELETE' });
    
    if (response.ok) {
      showToast('Conversation cleared');
      currentMessages = [];
      renderMessages();
      await loadConversations();
    } else {
      showToast('Failed to clear conversation', 'error');
    }
  } catch (error) {
    console.error('Clear failed:', error);
    showToast('Failed to clear conversation', 'error');
  }
}

async function viewContact() {
  if (!currentChat) return;
  
  try {
    const response = await fetch(`/api/contacts/${currentChat}`);
    if (response.ok) {
      const contact = await response.json();
      openEditContactModal(currentChat);
    } else {
      showToast('Contact not found', 'error');
    }
  } catch (error) {
    console.error('Failed to load contact:', error);
    showToast('Failed to load contact details', 'error');
  }
}

// ═══════════════════════════════════════════
// MODAL FUNCTIONS
// ═══════════════════════════════════════════

function openModal(modalId) {
  document.getElementById(modalId).classList.add('active');
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove('active');
}

// Contact Modals
function openAddContactModal() {
  document.getElementById('addContactForm').reset();
  openModal('addContactModal');
}

async function submitAddContact(event) {
  event.preventDefault();
  
  const phone = document.getElementById('contactPhone').value.trim();
  const name = document.getElementById('contactName').value.trim();
  const notes = document.getElementById('contactNotes').value.trim();
  const labelsText = document.getElementById('contactLabels').value.trim();
  const groupsText = document.getElementById('contactGroups').value.trim();  // ⬅️ ADD THIS
  
  const labels = labelsText ? labelsText.split(',').map(l => l.trim()).filter(l => l) : [];
  const groups = groupsText ? groupsText.split(',').map(g => g.trim()).filter(g => g) : [];  // ⬅️ ADD THIS
  
  try {
    const response = await fetch('/api/contacts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, name, notes, labels, groups })  // ⬅️ ADD groups
    });
    
    if (response.ok) {
      showToast('Contact added successfully');
      closeModal('addContactModal');
      await loadContacts();
    } else {
      const error = await response.json();
      showToast(error.detail || 'Failed to add contact', 'error');
    }
  } catch (error) {
    console.error('Failed to add contact:', error);
    showToast('Failed to add contact', 'error');
  }
}

function openImportContactsModal() {
  document.getElementById('contactsFile').value = '';
  document.getElementById('fileUploadText').textContent = 'Click to select file or drag & drop';
  document.getElementById('importPreview').style.display = 'none';
  document.getElementById('btnConfirmImport').disabled = true;
  contactsToImport = [];
  openModal('importContactsModal');
}

// In scripts.js, replace the handleContactsFile function

async function handleContactsFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  
  document.getElementById('fileUploadText').textContent = file.name;
  
  try {
    // Use SheetJS to parse Excel file
    const data = await file.arrayBuffer();
    const workbook = XLSX.read(data);
    const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
    const jsonData = XLSX.utils.sheet_to_json(firstSheet);
    
    if (jsonData.length === 0) {
      showToast('File is empty', 'error');
      return;
    }
    
    // Validate and prepare contacts
    contactsToImport = jsonData.map(row => ({
      phone: String(row.phone || '').trim(),
      name: String(row.name || '').trim(),
      notes: String(row.notes || '').trim(),
      labels: row.labels ? String(row.labels).split(',').map(l => l.trim()).filter(l => l) : [],
      groups: row.groups ? String(row.groups).split(',').map(g => g.trim()).filter(g => g) : []  // ⬅️ ADD THIS
    })).filter(c => c.phone);
    
    if (contactsToImport.length === 0) {
      showToast('No valid contacts found in file', 'error');
      return;
    }
    
    // Show preview
    document.getElementById('importPreview').style.display = 'block';
    document.getElementById('importPreviewContent').innerHTML = `
      <p style="color: #0f0; margin-bottom: 8px;">✓ Found ${contactsToImport.length} contacts</p>
      ${contactsToImport.slice(0, 5).map(c => `
        <div style="padding: 4px 0; border-bottom: 1px solid #222;">
          <strong>${escapeHtml(c.name || 'No name')}</strong> - ${c.phone}
          ${c.groups && c.groups.length > 0 ? `<br><small style="color: #888;">Groups: ${c.groups.join(', ')}</small>` : ''}
        </div>
      `).join('')}
      ${contactsToImport.length > 5 ? `<p style="color: #888; margin-top: 8px;">...and ${contactsToImport.length - 5} more</p>` : ''}
    `;
    
    document.getElementById('btnConfirmImport').disabled = false;
  } catch (error) {
    console.error('Failed to parse file:', error);
    showToast('Failed to parse file. Make sure it\'s a valid Excel file.', 'error');
  }
}

async function submitImportContacts() {
  if (contactsToImport.length === 0) return;
  
  const btnImport = document.getElementById('btnConfirmImport');
  btnImport.disabled = true;
  btnImport.textContent = 'Importing...';
  
  try {
    let imported = 0;
    let failed = 0;
    
    for (const contact of contactsToImport) {
      try {
        const response = await fetch('/api/contacts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(contact)
        });
        
        if (response.ok) {
          imported++;
        } else {
          failed++;
        }
      } catch (error) {
        failed++;
      }
    }
    
    showToast(`Imported ${imported} contacts${failed > 0 ? `, ${failed} failed` : ''}`, imported > 0 ? 'success' : 'error');
    closeModal('importContactsModal');
    await loadContacts();
  } catch (error) {
    console.error('Import failed:', error);
    showToast('Import failed', 'error');
  } finally {
    btnImport.disabled = false;
    btnImport.textContent = 'Import Contacts';
  }
}

// In scripts.js, replace the openEditContactModal function

async function openEditContactModal(phone) {
  try {
    const response = await fetch(`/api/contacts/${phone}`);
    if (!response.ok) {
      showToast('Contact not found', 'error');
      return;
    }
    
    const contact = await response.json();
    
    document.getElementById('editContactPhone').value = contact.phone;
    document.getElementById('editContactPhoneDisplay').value = contact.phone;
    document.getElementById('editContactName').value = contact.name || '';
    document.getElementById('editContactNotes').value = contact.notes || '';
    document.getElementById('editContactLabels').value = contact.labels ? contact.labels.join(', ') : '';
    document.getElementById('editContactGroups').value = contact.groups ? contact.groups.join(', ') : '';  // ⬅️ ADD THIS
    document.getElementById('editContactBusiness').checked = contact.is_business || false;
    
    openModal('editContactModal');
  } catch (error) {
    console.error('Failed to load contact:', error);
    showToast('Failed to load contact', 'error');
  }
}

// In scripts.js, replace the submitEditContact function

async function submitEditContact(event) {
  event.preventDefault();
  
  const phone = document.getElementById('editContactPhone').value;
  const name = document.getElementById('editContactName').value.trim();
  const notes = document.getElementById('editContactNotes').value.trim();
  const labelsText = document.getElementById('editContactLabels').value.trim();
  const groupsText = document.getElementById('editContactGroups').value.trim();  // ⬅️ ADD THIS
  const is_business = document.getElementById('editContactBusiness').checked;
  
  const labels = labelsText ? labelsText.split(',').map(l => l.trim()).filter(l => l) : [];
  const groups = groupsText ? groupsText.split(',').map(g => g.trim()).filter(g => g) : [];  // ⬅️ ADD THIS
  
  try {
    const response = await fetch(`/api/contacts/${phone}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, notes, labels, groups, is_business })  // ⬅️ ADD groups
    });
    
    if (response.ok) {
      showToast('Contact updated successfully');
      closeModal('editContactModal');
      await loadContacts();
    } else {
      const error = await response.json();
      showToast(error.detail || 'Failed to update contact', 'error');
    }
  } catch (error) {
    console.error('Failed to update contact:', error);
    showToast('Failed to update contact', 'error');
  }
}

async function deleteContact(phone) {
  if (!confirm(`Delete contact ${phone}?`)) return;
  
  try {
    const response = await fetch(`/api/contacts/${phone}`, { method: 'DELETE' });
    
    if (response.ok) {
      showToast('Contact deleted');
      await loadContacts();
    } else {
      showToast('Failed to delete contact', 'error');
    }
  } catch (error) {
    console.error('Failed to delete contact:', error);
    showToast('Failed to delete contact', 'error');
  }
}

// Group Modals
function openCreateGroupModal() {
  document.getElementById('createGroupForm').reset();
  openModal('createGroupModal');
}

async function submitCreateGroup(event) {
  event.preventDefault();
  
  const group_id = document.getElementById('groupId').value.trim();
  const name = document.getElementById('groupName').value.trim();
  const description = document.getElementById('groupDescription').value.trim();
  const participantsText = document.getElementById('groupParticipants').value.trim();
  const adminsText = document.getElementById('groupAdmins').value.trim();
  
  const participants = participantsText ? participantsText.split('\n').map(p => p.trim()).filter(p => p) : [];
  const admins = adminsText ? adminsText.split('\n').map(a => a.trim()).filter(a => a) : [];
  
  try {
    const response = await fetch('/api/groups', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id, name, description, participants, admins })
    });
    
    if (response.ok) {
      showToast('Group created successfully');
      closeModal('createGroupModal');
      await loadGroups();
    } else {
      const error = await response.json();
      showToast(error.detail || 'Failed to create group', 'error');
    }
  } catch (error) {
    console.error('Failed to create group:', error);
    showToast('Failed to create group', 'error');
  }
}

async function openEditGroupModal(groupId) {
  try {
    const response = await fetch(`/api/groups/${groupId}`);
    if (!response.ok) {
      showToast('Group not found', 'error');
      return;
    }
    
    const group = await response.json();
    
    document.getElementById('editGroupId').value = group.group_id;
    document.getElementById('editGroupName').value = group.name || '';
    document.getElementById('editGroupDescription').value = group.description || '';
    document.getElementById('editGroupActive').checked = group.is_active !== false;
    
    openModal('editGroupModal');
  } catch (error) {
    console.error('Failed to load group:', error);
    showToast('Failed to load group', 'error');
  }
}

async function submitEditGroup(event) {
  event.preventDefault();
  
  const group_id = document.getElementById('editGroupId').value;
  const name = document.getElementById('editGroupName').value.trim();
  const description = document.getElementById('editGroupDescription').value.trim();
  const is_active = document.getElementById('editGroupActive').checked;
  
  try {
    const response = await fetch(`/api/groups/${group_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description, is_active })
    });
    
    if (response.ok) {
      showToast('Group updated successfully');
      closeModal('editGroupModal');
      await loadGroups();
    } else {
      const error = await response.json();
      showToast(error.detail || 'Failed to update group', 'error');
    }
  } catch (error) {
    console.error('Failed to update group:', error);
    showToast('Failed to update group', 'error');
  }
}

async function deleteGroup(groupId) {
  if (!confirm(`Delete this group?`)) return;
  
  try {
    const response = await fetch(`/api/groups/${groupId}`, { method: 'DELETE' });
    
    if (response.ok) {
      showToast('Group deleted');
      await loadGroups();
    } else {
      showToast('Failed to delete group', 'error');
    }
  } catch (error) {
    console.error('Failed to delete group:', error);
    showToast('Failed to delete group', 'error');
  }
}

// ═══════════════════════════════════════════
// EVENT LISTENERS
// ═══════════════════════════════════════════

document.getElementById('searchBox').addEventListener('input', (e) => {
  const filter = e.target.value;
  if (currentTab === 'chats') {
    renderConversations(filter);
  } else if (currentTab === 'contacts') {
    renderContacts(filter);
  } else if (currentTab === 'groups') {
    renderGroups(filter);
  }
});

document.getElementById('messageInput').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

document.getElementById('messageInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ═══════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════

// Initial load
loadConversations();
loadStats();

// Refresh intervals
setInterval(loadConversations, 10000);
statsInterval = setInterval(loadStats, 30000);

// Cleanup
window.addEventListener('beforeunload', () => {
  if (autoRefreshInterval) clearInterval(autoRefreshInterval);
  if (statsInterval) clearInterval(statsInterval);
});