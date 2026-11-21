import { useCallback, useEffect, useState } from 'react';
import {
  fetchCurrentUser,
  getToken,
  sendChat,
  streamChat,
  listConversations,
  clearToken,
  getConversation,
  deleteConversation,
  listSyllabusMappings,
} from '../api';
import ChatInterface from './ChatInterface';
import AuthPanel from './AuthPanel';
import FacultyPanel from './FacultyPanel';
import LearningInsights from './LearningInsights';
import PeerBlindspotRoom from './PeerBlindspotRoom';
import WelcomePage from './WelcomePage';

export default function StepWiseApp() {
  const [token, setToken] = useState(getToken());
  const [user, setUser] = useState(null);
  const [loadingUser, setLoadingUser] = useState(true);
  const [conversationId, setConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [syllabusMappings, setSyllabusMappings] = useState([]);
  const [facultyPanelOpen, setFacultyPanelOpen] = useState(false);
  const [activeView, setActiveView] = useState('chat');
  const [authOpen, setAuthOpen] = useState(() => Boolean(
    getToken() || new URLSearchParams(window.location.search).get('reset_token')
  ));
  const [studioEntered, setStudioEntered] = useState(false);

  const refreshConversations = useCallback(async (activeToken = token) => {
    if (!activeToken) return;

    try {
      const items = await listConversations(activeToken);
      setConversations(items);
    } catch (err) {
      console.error('Failed to fetch conversations:', err);
    }
  }, [token]);

  const refreshSyllabusMappings = useCallback(async (activeToken = token, roleOverride = user?.role) => {
    if (!activeToken || roleOverride !== 'faculty') return;

    try {
      const items = await listSyllabusMappings(activeToken);
      setSyllabusMappings(items);
    } catch (err) {
      console.error('Failed to fetch syllabus mappings:', err);
    }
  }, [token, user?.role]);

  useEffect(() => {
    const bootstrap = async () => {
      const currentToken = getToken();
      if (!currentToken) {
        setLoadingUser(false);
        return;
      }

      try {
        const currentUser = await fetchCurrentUser();
        setUser(currentUser);
        await refreshConversations(currentToken);
        if (currentUser?.role === 'faculty') {
          await refreshSyllabusMappings(currentToken, currentUser.role);
        }
      } catch {
        clearToken();
        setToken(null);
        setAuthOpen(false);
      } finally {
        setLoadingUser(false);
      }
    };

    bootstrap();
  }, [token, refreshConversations, refreshSyllabusMappings]);

  const handleAuthSuccess = async (newToken) => {
    localStorage.setItem('stepwise_token', newToken);
    setToken(newToken);
    setAuthOpen(true);
    setStudioEntered(true);

    try {
      const currentUser = await fetchCurrentUser();
      setUser(currentUser);
      await refreshConversations(newToken);
      if (currentUser?.role === 'faculty') {
        await refreshSyllabusMappings(newToken, currentUser.role);
      }
    } catch (err) {
      console.error('Failed to load user after auth', err);
    }
  };

  const handleLogout = () => {
    clearToken();
    setToken(null);
    setUser(null);
    setConversationId(null);
    setConversations([]);
    setSyllabusMappings([]);
    setFacultyPanelOpen(false);
    setAuthOpen(false);
    setStudioEntered(false);
  };

  const openConversation = async (selectedId) => {
    if (!selectedId) {
      setConversationId(null);
      return null;
    }

    setConversationId(selectedId);
    const conversation = await getConversation(selectedId, token);
    return conversation;
  };

  const handleDeleteConversation = async (selectedId) => {
    await deleteConversation(selectedId, token);
    if (conversationId === selectedId) setConversationId(null);
    await refreshConversations();
  };

  const submitMessage = async ({ message, subject, history, parent_message_id, stream = true, onChunk }) => {
    const payload = {
      message,
      subject,
      history,
      conversation_id: conversationId,
      parent_message_id,
    };

    if (stream) {
      const response = await streamChat(
        payload,
        token,
        onChunk,
        async (completion) => {
          if (!conversationId && completion.conversation_id) {
            setConversationId(completion.conversation_id);
            await refreshConversations();
          }
        }
      );
      return { reply: response.text, ...response };
    }

    const response = await sendChat(payload, token);
    if (!conversationId && response.conversation_id) {
      setConversationId(response.conversation_id);
      await refreshConversations();
    }
    return response.reply;
  };

  if (loadingUser) {
    return <div className="loading-state">Loading StepWise...</div>;
  }

  if (!token || !user) {
    if (!authOpen && !new URLSearchParams(window.location.search).get('reset_token')) {
      return <WelcomePage onEnter={() => setAuthOpen(true)} />;
    }
    return <AuthPanel
      onAuthSuccess={handleAuthSuccess}
      onBack={() => setAuthOpen(false)}
    />;
  }

  if (!studioEntered) {
    return <WelcomePage signedIn onEnter={() => setStudioEntered(true)} />;
  }

  return (
    <div className="app-frame">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">S</div>
          <div>
            <div className="brand-name">StepWise</div>
            <div className="brand-email">{user.email}</div>
            <div className="brand-email">Role: {user.role || 'student'}</div>
          </div>
        </div>

        <div className="header-actions">
          <button className="secondary-button" onClick={() => setActiveView('chat')}>Tutor</button>
          <button className="secondary-button" onClick={() => setActiveView('insights')}>Learning insights</button>
          <button className="secondary-button" onClick={() => setActiveView('peer')}>Peer room</button>
          {user.role === 'faculty' && (
            <button className="secondary-button" onClick={() => setFacultyPanelOpen((prev) => !prev)}>
              {facultyPanelOpen ? 'Hide syllabus' : 'Syllabus mapping'}
            </button>
          )}
          <button className="logout-button" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      {user.role === 'faculty' && facultyPanelOpen && (
        <FacultyPanel token={token} mappings={syllabusMappings} onRefresh={refreshSyllabusMappings} />
      )}

      {activeView === 'chat' && <ChatInterface
        token={token}
        user={user}
        conversations={conversations}
        conversationId={conversationId}
        setConversationId={setConversationId}
        onSendMessage={submitMessage}
        onOpenConversation={openConversation}
        onDeleteConversation={handleDeleteConversation}
        onRefreshConversations={refreshConversations}
        availableSubjects={syllabusMappings.map((mapping) => mapping.subject)}
      />}
      {activeView === 'insights' && <LearningInsights token={token} />}
      {activeView === 'peer' && <PeerBlindspotRoom token={token} />}
    </div>
  );
}
