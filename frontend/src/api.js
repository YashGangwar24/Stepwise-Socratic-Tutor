import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const API = axios.create({
  baseURL: API_BASE_URL,
});

export function setToken(token) {
  localStorage.setItem('stepwise_token', token);
}

export function getToken() {
  return localStorage.getItem('stepwise_token');
}

export function clearToken() {
  localStorage.removeItem('stepwise_token');
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function registerUser(payload) {
  const response = await API.post('/api/auth/register', payload);
  return response.data;
}

export async function loginUser(payload) {
  const response = await API.post('/api/auth/login', payload);
  setToken(response.data.access_token);
  return response.data;
}

export async function requestPasswordReset(payload) {
  const response = await API.post('/api/auth/password-reset/request', payload);
  return response.data;
}

export async function confirmPasswordReset(payload) {
  const response = await API.post('/api/auth/password-reset/confirm', payload);
  return response.data;
}

export async function fetchCurrentUser() {
  const token = getToken();
  if (!token) return null;

  const response = await API.get('/api/users/me', {
    headers: authHeaders(),
  });

  return response.data;
}

export async function createConversation(title, token = getToken(), subject = 'Uncategorized') {
  const response = await API.post(
    '/api/conversations',
    { title, subject },
    { headers: { Authorization: `Bearer ${token}` } }
  );

  return response.data;
}

export async function listConversations(token = getToken()) {
  const response = await API.get('/api/conversations', {
    headers: { Authorization: `Bearer ${token}` },
  });

  return response.data;
}

export async function getConversation(id, token = getToken()) {
  const response = await API.get(`/api/conversations/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return response.data;
}

export async function deleteConversation(id, token = getToken()) {
  const response = await API.delete(`/api/conversations/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response.data;
}

export async function listSyllabusMappings(token = getToken()) {
  const response = await API.get('/api/syllabus/mappings', {
    headers: { Authorization: `Bearer ${token}` },
  });

  return response.data;
}

export async function getLearningInsights(token = getToken()) {
  const response = await API.get('/api/learning-insights', { headers: { Authorization: `Bearer ${token}` } });
  return response.data;
}

export async function createPeerRoom(subject, token = getToken()) {
  const response = await API.post('/api/peer-rooms', { subject }, { headers: { Authorization: `Bearer ${token}` } });
  return response.data;
}

export async function generatePeerDemoModerator(token = getToken()) {
  const response = await API.post('/api/peer-rooms/demo-moderator', {}, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response.data;
}

export async function createSyllabusMapping(payload, token = getToken()) {
  const response = await API.post('/api/syllabus/mappings', payload, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return response.data;
}

export async function sendChat(payload, token = getToken()) {
  const response = await API.post('/api/chat', payload, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return response.data;
}

export async function streamChat(payload, token = getToken(), onChunk = () => {}, onComplete = () => {}) {
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = '';
    try {
      detail = (await response.json())?.detail || '';
    } catch {
      // The server may return a non-JSON error page.
    }
    throw new Error(detail || `Streaming chat failed (${response.status})`);
  }

  if (!response.body) throw new Error('The server did not provide a response stream.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let fullText = '';
  let completion = null;
  let streamError = '';
  let buffer = '';

  const handleEvent = (eventText) => {
    const data = eventText
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.replace(/^data:\s?/, ''))
      .join('\n');
    if (!data) return;
    try {
      const payloadData = JSON.parse(data);
      if (typeof payloadData.chunk === 'string') {
        fullText += payloadData.chunk;
        onChunk(payloadData.chunk);
      }
      if (payloadData.done && payloadData.conversation_id) {
        completion = { ...payloadData, error: payloadData.error || streamError };
        onComplete(completion);
      }
      if (typeof payloadData.error === 'string') streamError = payloadData.error;
    } catch (error) {
      if (error instanceof SyntaxError) {
        console.warn('Skipping non-JSON SSE payload:', data, error);
        return;
      }
      throw error;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let boundary;
    while ((boundary = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const eventText = buffer.slice(0, boundary);
      const delimiter = buffer.slice(boundary).match(/^\r?\n\r?\n/)[0];
      buffer = buffer.slice(boundary + delimiter.length);
      handleEvent(eventText);
    }
    if (done) break;
  }
  if (buffer.trim()) handleEvent(buffer);

  if (!completion && streamError) throw new Error(streamError);
  if (!completion) throw new Error('The response stream ended before the tutor finished. Please try again.');
  return { text: fullText, ...completion };
}

export async function editMessage(messageId, payload, token = getToken()) {
  const response = await API.post(`/api/messages/${messageId}/edit`, payload, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return response.data;
}

export default API;
