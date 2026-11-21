import { useState, useRef, useEffect, isValidElement } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { editMessage, getConversation } from '../api';
import { SUBJECTS } from '../subjects';

const MAX_ATTACHMENT_BYTES = 10 * 1024;
const MAX_PDF_BYTES = 5 * 1024 * 1024;
const MAX_ATTACHMENT_TEXT = 7_000;
const MAX_ATTACHMENT_COUNT = 5;
const MAX_PDF_PAGES = 20;

async function extractPdfText(file) {
  const [pdfjsLib, worker] = await Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
  ]);
  pdfjsLib.GlobalWorkerOptions.workerSrc = worker.default;
  const bytes = new Uint8Array(await file.arrayBuffer());
  const header = new TextDecoder().decode(bytes.subarray(0, Math.min(bytes.length, 1024)));
  if (!header.includes('%PDF-')) throw new Error('This file does not look like a valid PDF.');

  const loadingTask = pdfjsLib.getDocument({ data: bytes });
  let document;
  try {
    document = await loadingTask.promise;
    if (document.numPages > MAX_PDF_PAGES) {
      throw new Error(`PDFs are limited to ${MAX_PDF_PAGES} pages.`);
    }
    const pages = [];
    let characterCount = 0;
    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
      const page = await document.getPage(pageNumber);
      const content = await page.getTextContent();
      const pageText = content.items
        .filter((item) => typeof item.str === 'string')
        .map((item) => `${item.str}${item.hasEOL ? '\n' : ' '}`)
        .join('').trim();
      page.cleanup();
      characterCount += pageText.length;
      if (characterCount > MAX_ATTACHMENT_TEXT) {
        throw new Error('Extracted PDF text exceeds the 7,000 character attachment limit.');
      }
      if (pageText) pages.push(`[Page ${pageNumber}]\n${pageText}`);
    }
    const text = pages.join('\n\n').trim();
    if (!text) throw new Error('No selectable text was found. Scanned/image-only PDFs are not supported yet.');
    return text;
  } catch (error) {
    if (error instanceof Error && /^(PDFs are limited|Extracted PDF text|No selectable text|This file does not look)/.test(error.message)) {
      throw error;
    }
    throw new Error('Could not read this PDF. It may be damaged or password-protected.', { cause: error });
  } finally {
    if (document) await document.destroy();
    else await loadingTask.destroy();
  }
}

const TOKEN_PATTERN = /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b(?:const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|def|print|in|is|not|and|or|True|False|None|true|false|null|undefined|public|private|static|void|int|string|bool)\b|\b\d+(?:\.\d+)?\b)/g;

function HighlightedCode({ code }) {
  const parts = [];
  let lastIndex = 0;
  for (const match of code.matchAll(TOKEN_PATTERN)) {
    if (match.index > lastIndex) parts.push(code.slice(lastIndex, match.index));
    const token = match[0];
    const kind = /^(\/\/|#|\/\*)/.test(token) ? 'comment' : /^["'`]/.test(token) ? 'string' : /^\d/.test(token) ? 'number' : 'keyword';
    parts.push(<span className={`syntax-${kind}`} key={`${match.index}-${token}`}>{token}</span>);
    lastIndex = match.index + token.length;
  }
  if (lastIndex < code.length) parts.push(code.slice(lastIndex));
  return parts;
}

function activeBranch(messages, choices) {
  const children = new Map();
  messages.forEach((message) => {
    const parent = message.parent_message_id ?? null;
    children.set(parent, [...(children.get(parent) || []), message]);
  });
  const path = [];
  let parent = null;
  while (children.has(parent)) {
    const options = children.get(parent).sort((a, b) => a.id - b.id);
    const current = options.find((item) => item.id === choices[parent ?? 'root']) || options[options.length - 1];
    path.push(current);
    parent = current.id;
  }
  return { path, children };
}

function CodeBlock({ className, children, ...props }) {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : 'code';
  const code = String(children).replace(/\n$/, '');
  const [copyStatus, setCopyStatus] = useState('');

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopyStatus('Copied');
      setTimeout(() => setCopyStatus(''), 1200);
    } catch (error) {
      console.error('Copy failed:', error);
      setCopyStatus('Copy failed');
      setTimeout(() => setCopyStatus(''), 1800);
    }
  };

  return (
    <div className="code-block-shell">
      <div className="code-block-header">
        <span>{language}</span>
        <button type="button" onClick={handleCopy} className="copy-button">
          {copyStatus || 'Copy'}
        </button>
      </div>
      <pre className={className} {...props}>
        <code><HighlightedCode code={code} /></code>
      </pre>
    </div>
  );
}

export default function ChatInterface({
  token,
  conversations,
  conversationId,
  setConversationId,
  onSendMessage,
  onOpenConversation,
  onDeleteConversation,
  onRefreshConversations,
  availableSubjects = [],
}) {
  const [messages, setMessages] = useState([]);
  const [branchChoices, setBranchChoices] = useState({});
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [voiceListening, setVoiceListening] = useState(false);
  const [subject, setSubject] = useState('Algorithms');
  const [loading, setLoading] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [sendError, setSendError] = useState('');
  const [supportLevel, setSupportLevel] = useState(1);
  const [deletingConversationId, setDeletingConversationId] = useState(null);
  const [readingAttachments, setReadingAttachments] = useState(false);
  const [conversationTitle, setConversationTitle] = useState('');
  const [sampleStream, setSampleStream] = useState(null);
  const sampleStreamTimer = useRef(null);

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const recognitionRef = useRef(null);
  const { path: visibleMessages, children: messageChildren } = activeBranch(messages, branchChoices);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, streamText]);

  useEffect(() => {
    let isCurrentConversation = true;

    const loadConversation = async () => {
      clearInterval(sampleStreamTimer.current);
      if (!conversationId) {
        setMessages([]);
        setBranchChoices({});
        setConversationTitle('');
        setSampleStream(null);
        return;
      }

      try {
        const data = await getConversation(conversationId, token);
        if (!isCurrentConversation) return;
        setSubject(data.subject || 'Uncategorized');
        setConversationTitle(data.title || '');
        setSupportLevel(data.support_level || 1);
        setMessages(data.messages || []);
        setSampleStream(null);
      } catch (err) {
        if (!isCurrentConversation) return;
        console.error('Could not load conversation history:', err);
        setMessages([]);
      }
    };

    loadConversation();

    return () => {
      isCurrentConversation = false;
    };
  }, [conversationId, token]);

  useEffect(() => () => clearInterval(sampleStreamTimer.current), []);

  const replaySampleStream = (message) => {
    clearInterval(sampleStreamTimer.current);
    setSampleStream({ messageId: message.id, text: '', complete: false });
    let position = 0;
    sampleStreamTimer.current = setInterval(() => {
      position = Math.min(message.content.length, position + 8);
      setSampleStream({ messageId: message.id, text: message.content.slice(0, position), complete: position >= message.content.length });
      if (position >= message.content.length) clearInterval(sampleStreamTimer.current);
    }, 90);
  };

  const startNewChat = async () => {
    recognitionRef.current?.stop();
    setVoiceListening(false);
    setMessages([]);
    setBranchChoices({});
    setInput('');
    setAttachments([]);
    setSupportLevel(1);
    setConversationId(null);
  };

  const handleSelectConversation = async (selectedId) => {
    recognitionRef.current?.stop();
    setVoiceListening(false);
    setInput('');
    setAttachments([]);
    setBranchChoices({});
    const selectedConversation = conversations.find((conversation) => conversation.id === selectedId);
    if (selectedConversation) {
      setSubject(selectedConversation.subject || 'Uncategorized');
    }
    setConversationId(selectedId);
    if (onOpenConversation) {
      await onOpenConversation(selectedId);
    }
  };

  const handleDeleteConversation = async (conversation) => {
    if (loading || deletingConversationId) return;
    const title = conversation.title || 'Untitled chat';
    if (!window.confirm(`Delete “${title}”? This will permanently remove its messages and sample insights.`)) return;
    setDeletingConversationId(conversation.id);
    setSendError('');
    try {
      await onDeleteConversation(conversation.id);
      if (conversation.id === conversationId) {
        setMessages([]);
        setBranchChoices({});
      }
    } catch (error) {
      setSendError(error.response?.data?.detail || error.message || 'Could not delete this chat. Try again.');
    } finally {
      setDeletingConversationId(null);
    }
  };

  const handleSubjectChange = (nextSubject) => {
    recognitionRef.current?.stop();
    setVoiceListening(false);
    setSubject(nextSubject);
    setConversationId(null);
    setMessages([]);
    setBranchChoices({});
    setInput('');
    setAttachments([]);
    setSupportLevel(1);
  };

  const subjectOptions = Array.from(new Set([
    ...SUBJECTS,
    ...conversations.map((conversation) => conversation.subject).filter(Boolean),
    ...availableSubjects,
  ]));

  const subjectConversations = conversations.filter(
    (conversation) => (conversation.subject || 'Uncategorized') === subject
  );

  const sendMessage = async () => {
    if ((!input.trim() && attachments.length === 0) || loading || readingAttachments) return;
    clearInterval(sampleStreamTimer.current);
    setSampleStream(null);
    const submittedInput = input;
    const submittedAttachments = attachments;
    const messageText = [input.trim(), ...attachments.map(({ name, content }) => `Attached file: ${name}\n\n\`\`\`\n${content}\n\`\`\``)]
      .filter(Boolean).join('\n\n');
    if (messageText.length > 10_000) {
      setSendError('This message and its attachments exceed the 10,000 character limit. Remove a file or shorten the message.');
      return;
    }
    const { path } = activeBranch(messages, branchChoices);
    const priorHistory = path.map((msg) => ({ role: msg.role === 'assistant' ? 'model' : 'user', text: msg.content }));
    setSendError('');
    setLoading(true);
    setStreamText('');
    setInput('');
    setAttachments([]);
    let messageSubmitted = false;

    try {
      const result = await onSendMessage({
        message: messageText,
        subject,
        history: priorHistory,
        parent_message_id: path.at(-1)?.id ?? null,
        stream: true,
        onChunk: (chunk) => {
          setStreamText((previous) => previous + chunk);
        },
      });
      messageSubmitted = true;
      const conversation = await getConversation(result.conversation_id, token);
      setMessages(conversation.messages || []);
      setBranchChoices({});
      setSendError(result.error || '');
      if (result.support_level) setSupportLevel(result.support_level);
      if (onRefreshConversations) {
        await onRefreshConversations();
      }
    } catch (error) {
      console.error('Error communicating with backend:', error);
      if (!messageSubmitted) {
        setInput(submittedInput);
        setAttachments(submittedAttachments);
      }
      setSendError(error.message || 'Could not send the message. Check that StepWise is running and try again.');
    } finally {
      setLoading(false);
      setStreamText('');
    }
  };

  const addAttachments = async (event) => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) return;
    setReadingAttachments(true);
    setSendError('');
    const additions = [];
    let totalCharacters = attachments.reduce((total, file) => total + file.content.length, 0);
    try {
    for (const file of files) {
      if (attachments.length + additions.length >= MAX_ATTACHMENT_COUNT) {
        setSendError(`Attach no more than ${MAX_ATTACHMENT_COUNT} files at once.`);
        break;
      }
      const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
      const fileSizeLimit = isPdf ? MAX_PDF_BYTES : MAX_ATTACHMENT_BYTES;
      if (file.size > fileSizeLimit) {
        setSendError(isPdf
          ? `${file.name} is larger than 5 MB. Choose a smaller PDF.`
          : `${file.name} is larger than 10 KB. Choose a smaller text or code file.`);
        continue;
      }
      try {
        const content = isPdf ? await extractPdfText(file) : await file.text();
        if (totalCharacters + content.length > MAX_ATTACHMENT_TEXT) {
          setSendError('Attachments are limited to 7,000 extracted characters in total. Remove a file or choose smaller files.');
          continue;
        }
        additions.push({ name: file.name, content });
        totalCharacters += content.length;
      } catch (error) {
        setSendError(error.message || `Could not read ${file.name}.`);
      }
    }
    setAttachments((current) => [...current, ...additions]);
    } finally {
      setReadingAttachments(false);
    }
  };

  const toggleVoiceInput = () => {
    if (voiceListening) {
      recognitionRef.current?.stop();
      setVoiceListening(false);
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSendError('Voice input is not supported in this browser. Try Chrome or Edge.');
      return;
    }
    let recognition;
    try {
      recognition = new SpeechRecognition();
    } catch {
      setSendError('Voice input could not start in this browser.');
      return;
    }
    recognition.lang = navigator.language || 'en-US';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).slice(event.resultIndex)
        .filter((result) => result.isFinal)
        .map((result) => result[0].transcript).join('');
      if (transcript) setInput((current) => `${current}${current && !current.endsWith(' ') ? ' ' : ''}${transcript}`);
    };
    recognition.onerror = (event) => {
      setVoiceListening(false);
      if (event.error !== 'aborted' && event.error !== 'no-speech') {
        setSendError('Voice input failed. Check microphone permission and try again.');
      }
    };
    recognition.onend = () => setVoiceListening(false);
    recognitionRef.current = recognition;
    try {
      recognition.start();
      setSendError('');
      setVoiceListening(true);
    } catch {
      setSendError('Voice input could not start. Try again after closing any other microphone session.');
    }
  };

  useEffect(() => () => recognitionRef.current?.stop(), []);

  const handleEditMessage = async (message) => {
    const edited = window.prompt('Edit your message', message.content);
    if (edited === null || !edited.trim() || edited.trim() === message.content) return;
    setLoading(true);
    try {
      const result = await editMessage(message.id, {
        content: edited.trim(),
        regenerate: true,
      }, token);
      const data = await getConversation(conversationId, token);
      setMessages(data.messages || []);
      setBranchChoices((current) => ({ ...current, [message.id]: result.id }));
    } catch (error) {
      console.error('Could not create edited branch:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span>Recent chats</span>
          <button className="secondary-button" onClick={startNewChat}>New</button>
        </div>

        <div className="conversation-list">
          {subjectConversations.length === 0 ? (
            <div className="no-chats">No {subject} chats yet</div>
          ) : (
            subjectConversations.map((conversation) => (
              <div className="conversation-row" key={conversation.id}>
              <button
                className={`conversation-item ${conversation.id === conversationId ? 'active' : ''}`}
                onClick={() => handleSelectConversation(conversation.id)}
                disabled={Boolean(deletingConversationId)}
              >
                <span className="conversation-title">{conversation.title || 'Untitled chat'}</span>
                <small>{new Date(conversation.updated_at).toLocaleDateString()}</small>
              </button>
              <button
                type="button"
                className="conversation-delete"
                aria-label={`Delete ${conversation.title || 'chat'}`}
                title="Delete chat"
                disabled={deletingConversationId === conversation.id || loading}
                onClick={() => handleDeleteConversation(conversation)}
              >{deletingConversationId === conversation.id ? '…' : '×'}</button>
              </div>
            ))
          )}
        </div>
      </aside>

      <main className="chat-shell">
        <div className="chat-header">
          <div>
            <p className="eyebrow">Learning Studio</p>
            <h2>{conversationId ? 'StepWise Socratic Tutor' : 'StepWise Socratic Tutor'}</h2>
          </div>

          <div className="header-actions">
            <label className="subject-picker">
              <span>Subject</span>
              <select value={subject} onChange={(e) => handleSubjectChange(e.target.value)}>
                {subjectOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>

            <button className="secondary-button" onClick={startNewChat}>
              New Chat
            </button>
          </div>
        </div>

        <div className="support-indicator" title="This is a rough learning-support estimate from recent messages, not a diagnosis.">
          <span>Guidance style</span>
          <strong>{supportLevel >= 5 ? 'Step by step' : supportLevel >= 3 ? 'More structured' : 'Gentle prompts'}</strong>
          <small>Adjusts hints from your recent messages; not a score.</small>
        </div>

        <div className="message-panel">
          {(messageChildren.get(null) || []).length > 1 && (
            <label className="branch-picker">
              Conversation branch
              <select
                value={branchChoices.root ?? (messageChildren.get(null) || []).at(-1)?.id}
                onChange={(event) => setBranchChoices((current) => ({ ...current, root: Number(event.target.value) }))}
              >
                {(messageChildren.get(null) || []).map((branch, index) => (
                  <option key={branch.id} value={branch.id}>Path {index + 1}: {branch.content.slice(0, 48)}</option>
                ))}
              </select>
            </label>
          )}
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">✦</div>
              <h3>Ask a question and learn by thinking.</h3>
              <p>StepWise will guide you with short, focused questions instead of giving away the answer.</p>
            </div>
          ) : null}

          {visibleMessages.map((msg) => (
            <div key={msg.id}>
            <div className={`message-bubble ${msg.role === 'user' ? 'user' : 'assistant'} ${sampleStream?.messageId === msg.id ? 'streaming-response' : ''}`}>
              {sampleStream?.messageId === msg.id && <small className="sample-stream-status">{sampleStream.complete ? 'Sample stream finished' : 'Streaming sample preview…'}</small>}
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  pre({ children }) {
                    if (isValidElement(children)) {
                      return <CodeBlock className={children.props.className}>{children.props.children}</CodeBlock>;
                    }
                    return <pre>{children}</pre>;
                  },
                  code({ className, children, ...props }) {
                    return <code className={className} {...props}>{children}</code>;
                  },
                }}
              >
                {sampleStream?.messageId === msg.id ? sampleStream.text : msg.role === 'assistant' && !msg.content?.trim()
                  ? 'No reply was received. Use “Edit and branch” on your question to try again.'
                  : msg.content}
              </ReactMarkdown>
              {msg.role === 'user' && (
                <button type="button" className="message-action" onClick={() => handleEditMessage(msg)}>Edit and branch</button>
              )}
            </div>
            {conversationTitle === 'Sample demo: Rich chat rendering' && msg.role === 'assistant' && (
              <button
                type="button"
                className="sample-replay-button"
                onClick={() => replaySampleStream(msg)}
                title="Visual preview of the streamed sample; live tutor messages use SSE."
              >Replay streamed sample</button>
            )}
            {(messageChildren.get(msg.id) || []).length > 1 && (
              <label className="branch-picker">
                Branch
                <select
                  value={branchChoices[msg.id] ?? (messageChildren.get(msg.id) || []).at(-1)?.id}
                  onChange={(event) => setBranchChoices((current) => ({ ...current, [msg.id]: Number(event.target.value) }))}
                >
                  {(messageChildren.get(msg.id) || []).map((branch, index) => (
                    <option key={branch.id} value={branch.id}>Option {index + 1}: {branch.content.slice(0, 48)}</option>
                  ))}
                </select>
              </label>
            )}
            </div>
          ))}

          {loading && streamText && (
            <div className="message-bubble assistant streaming-response" aria-live="polite">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>{streamText}</ReactMarkdown>
            </div>
          )}

          {loading && (
            <div className="typing-indicator">
              <span />
              <span />
              <span />
              <small>StepWise is formulating a guiding question...</small>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="composer">
          <input ref={fileInputRef} className="file-input-hidden" type="file" multiple accept="application/pdf,.pdf,.txt,.md,.csv,.json,.py,.js,.jsx,.ts,.tsx,.html,.css,.java,.c,.cpp,.h,.sql,.xml,.yaml,.yml,.log" onChange={addAttachments} />
          <button type="button" className="composer-tool" onClick={() => fileInputRef.current?.click()} disabled={loading || readingAttachments} aria-label="Attach PDF, text, or code files" title="Attach PDF, text, or code files">{readingAttachments ? 'Reading…' : 'Add'}</button>
          <button type="button" className={`composer-tool ${voiceListening ? 'voice-active' : ''}`} onClick={toggleVoiceInput} disabled={loading} aria-label={voiceListening ? 'Stop voice input' : 'Start voice input'} title={voiceListening ? 'Stop voice input' : 'Voice input'}>{voiceListening ? 'Stop' : 'Mic'}</button>
          <input
            type="text"
            maxLength={10_000}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                sendMessage();
              }
            }}
            disabled={loading}
            placeholder="Ask a question or paste your code..."
          />
          <button onClick={sendMessage} disabled={loading || readingAttachments || (!input.trim() && attachments.length === 0)}>
            {loading ? 'Thinking...' : 'Send'}
          </button>
        </div>
        {sendError && <div className="chat-error" role="alert">{sendError}</div>}
        {attachments.length > 0 && <div className="attachment-list">{attachments.map((file, index) => <span className="attachment-chip" key={`${file.name}-${index}`}>{file.name}<button type="button" aria-label={`Remove ${file.name}`} onClick={() => setAttachments((current) => current.filter((_, itemIndex) => itemIndex !== index))}>×</button></span>)}</div>}
      </main>
    </div>
  );
}
