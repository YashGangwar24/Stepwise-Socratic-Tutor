import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, createPeerRoom, generatePeerDemoModerator } from '../api';
import { SUBJECTS } from '../subjects';

export default function PeerBlindspotRoom({ token }) {
  const [invite, setInvite] = useState('');
  const [activeCode, setActiveCode] = useState('');
  const [subject, setSubject] = useState('Algorithms');
  const [participants, setParticipants] = useState([]);
  const [messages, setMessages] = useState([]);
  const [code, setCode] = useState('');
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [sampleModerator, setSampleModerator] = useState('');
  const [loadingSampleModerator, setLoadingSampleModerator] = useState(false);
  const socketRef = useRef(null);
  const codeTimer = useRef(null);

  const connect = (roomCode) => {
    socketRef.current?.close();
    const base = API_BASE_URL.replace(/^http/, 'ws').replace(/\/$/, '');
    const socket = new WebSocket(`${base}/ws/peer-room/${encodeURIComponent(roomCode)}`);
    socketRef.current = socket;
    socket.onopen = () => socket.send(JSON.stringify({ type: 'authenticate', token }));
    socket.onmessage = (event) => {
      let payload;
      try { payload = JSON.parse(event.data); } catch { return; }
      if (payload.type === 'error') setError(payload.message);
      if (payload.type === 'state') {
        setParticipants(payload.participants || []); setSubject(payload.subject || 'Algorithms');
        setCode(payload.code || ''); setMessages(payload.messages || []);
      }
      if (payload.type === 'message' || payload.type === 'facilitator') setMessages((current) => [...current, payload].slice(-40));
      if (payload.type === 'code_update') setCode(payload.code || '');
      if (payload.type === 'closed') setError('The room has been closed.');
    };
    socket.onerror = () => setError('Could not connect to the peer room. Check the server and invite code.');
    socket.onclose = () => { if (socketRef.current === socket) socketRef.current = null; };
    setActiveCode(roomCode); setError('');
  };

  useEffect(() => () => { clearTimeout(codeTimer.current); socketRef.current?.close(); }, []);

  const create = async () => {
    setError('');
    try { const room = await createPeerRoom(subject, token); connect(room.code); }
    catch (err) { setError(err.response?.data?.detail || 'Could not create a room.'); }
  };
  const join = () => { if (invite.trim()) connect(invite.trim()); };
  const generateSampleModerator = async () => {
    setLoadingSampleModerator(true);
    setError('');
    try {
      const result = await generatePeerDemoModerator(token);
      setSampleModerator(result.content);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not generate a sample moderator message. Is Ollama running?');
    } finally {
      setLoadingSampleModerator(false);
    }
  };
  const leave = () => { socketRef.current?.close(); setActiveCode(''); setParticipants([]); setMessages([]); };
  const updateCode = (value) => {
    setCode(value); clearTimeout(codeTimer.current);
    codeTimer.current = setTimeout(() => {
      if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'code_update', code: value }));
    }, 250);
  };
  const send = (event) => {
    event.preventDefault();
    if (draft.trim() && socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: 'chat', content: draft.trim() })); setDraft('');
    }
  };

  return <section className="feature-panel peer-panel">
    <p className="eyebrow">Peer blindspot room</p><h2>Debug together</h2>
    <p>Two learners can compare assumptions with a local Socratic facilitator. Rooms expire after one hour and messages/code are kept in memory only. The app still authenticates you; only Learner A/B aliases are shared. Anyone with the invite code can join, so don’t share personal or sensitive data.</p>
    <details className="peer-sample-preview">
      <summary>Preview a sample peer session</summary>
      <div className="peer-workspace">
        <pre><code>{'for i in range(len(values) + 1):\n    print(values[i])'}</code></pre>
        <div className="peer-messages">
          <p><strong>Participants:</strong> Learner A · Learner B (sample aliases)</p>
          <p><strong>Learner A:</strong> I used length as the final index.</p>
          <p><strong>Learner B:</strong> I think range stops before its end value. Can we trace a three-item list?</p>
          {sampleModerator
            ? <p><strong>StepWise moderator · local LLM:</strong> {sampleModerator}</p>
            : <p><strong>StepWise moderator:</strong> Generate a fresh local-model prompt for this sample discussion.</p>}
          <button type="button" className="secondary-button" onClick={generateSampleModerator} disabled={loadingSampleModerator}>
            {loadingSampleModerator ? 'Generating…' : 'Generate sample moderator message'}
          </button>
        </div>
      </div>
    </details>
    {!activeCode ? <div className="peer-join-controls">
      <label>Subject <select value={subject} onChange={(event) => setSubject(event.target.value)}>{SUBJECTS.map((item) => <option key={item}>{item}</option>)}</select></label>
      <button className="primary-button" onClick={create}>Create room</button>
      <label>Invite code <input value={invite} onChange={(event) => setInvite(event.target.value)} maxLength={40} /></label>
      <button className="secondary-button" onClick={join} disabled={!invite.trim()}>Join room</button>
    </div> : <>
      <div className="peer-room-meta"><strong>Invite code: {activeCode}</strong><span>{participants.length}/2 learners connected</span><button className="secondary-button" onClick={leave}>Leave room</button></div>
      <div className="peer-workspace">
        <label>Shared code draft<textarea value={code} onChange={(event) => updateCode(event.target.value)} maxLength={8000} rows={12} placeholder="Paste or write the small section you are debugging…" /></label>
        <div className="peer-chat"><div className="peer-messages" aria-live="polite">{messages.map((item, index) => <p key={`${index}-${item.type}`}><strong>{item.type === 'facilitator' ? 'StepWise' : item.alias}:</strong> {item.content}</p>)}</div>
          <form onSubmit={send}><input value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={2000} placeholder="What have you each tried?" /><button className="primary-button">Send</button></form></div>
      </div>
    </>}
    {error && <p role="alert" className="feature-error">{error}</p>}
  </section>;
}
