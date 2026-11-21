import { useState } from 'react';
import {
  confirmPasswordReset,
  loginUser,
  registerUser,
  requestPasswordReset,
} from '../api';

export default function AuthPanel({ onAuthSuccess, onBack }) {
  const resetToken = new URLSearchParams(window.location.search).get('reset_token');
  const [mode, setMode] = useState(resetToken ? 'reset' : 'login');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('student');
  const [facultyInviteCode, setFacultyInviteCode] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [resetLink, setResetLink] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setResetLink('');
    setLoading(true);

    try {
      if (mode === 'forgot') {
        const result = await requestPasswordReset({ email });
        setNotice(result.message);
        setResetLink(result.reset_url || '');
        return;
      }

      if (mode === 'reset') {
        await confirmPasswordReset({ token: resetToken, new_password: password });
        window.history.replaceState({}, '', window.location.pathname);
        setPassword('');
        setMode('login');
        setNotice('Password updated. Sign in with your new password.');
        return;
      }

      if (mode === 'register') {
        await registerUser({
          email,
          full_name: fullName.trim() || null,
          password,
          role,
          faculty_invite_code: role === 'faculty' ? facultyInviteCode : undefined,
        });
        const loginData = await loginUser({ email, password });
        onAuthSuccess(loginData.access_token);
        return;
      }

      const loginData = await loginUser({ email, password });
      onAuthSuccess(loginData.access_token);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark">S</div>
          <div>
            <div className="brand-name">StepWise</div>
            <div className="brand-subtitle">Socratic learning studio</div>
          </div>
        </div>

        {['login', 'register'].includes(mode) && (
          <div className="auth-mode-toggle">
            <button
              className={mode === 'login' ? 'active' : ''}
              onClick={() => { setMode('login'); setError(''); setNotice(''); setResetLink(''); }}
              type="button"
            >
              Login
            </button>
            <button
              className={mode === 'register' ? 'active' : ''}
              onClick={() => { setMode('register'); setError(''); setNotice(''); setResetLink(''); }}
              type="button"
            >
              Register
            </button>
          </div>
        )}

        <h2>
          {mode === 'login' && 'Welcome back'}
          {mode === 'register' && 'Create your account'}
          {mode === 'forgot' && 'Reset your password'}
          {mode === 'reset' && 'Choose a new password'}
        </h2>

        <form onSubmit={handleSubmit} className="auth-form">
          {mode === 'register' && (
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Full name"
              className="text-input"
            />
          )}

          {mode !== 'reset' && (
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="text-input"
              autoComplete="email"
              required
            />
          )}

          {mode === 'register' && (
            <label className="auth-field">
              <span>Account type</span>
              <select value={role} onChange={(e) => setRole(e.target.value)} className="text-input">
                <option value="student">Student</option>
                <option value="faculty">Faculty</option>
              </select>
            </label>
          )}

          {mode === 'register' && role === 'faculty' && (
            <input
              type="password"
              value={facultyInviteCode}
              onChange={(e) => setFacultyInviteCode(e.target.value)}
              placeholder="Faculty invitation code"
              className="text-input"
              autoComplete="off"
              required
            />
          )}

          {['login', 'register', 'reset'].includes(mode) && (
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === 'reset' ? 'New password (at least 8 characters)' : 'Password'}
              className="text-input"
              autoComplete={mode === 'reset' ? 'new-password' : 'current-password'}
              minLength={['reset', 'register'].includes(mode) ? 8 : undefined}
              maxLength={128}
              required
            />
          )}

          {error && <div className="auth-error">{error}</div>}
          {notice && <div className="auth-notice" role="status">{notice}</div>}
          {resetLink && (
            <a className="auth-link" href={resetLink}>
              Continue to local password reset
            </a>
          )}

          <button type="submit" className="primary-button auth-submit" disabled={loading}>
            {loading ? 'Please wait...' : {
              login: 'Login',
              register: 'Register',
              forgot: 'Send reset link',
              reset: 'Update password',
            }[mode]}
          </button>
        </form>

        {mode === 'login' && (
          <button className="auth-link" onClick={() => { setMode('forgot'); setError(''); setNotice(''); setResetLink(''); }} type="button">
            Forgot password?
          </button>
        )}
        {['forgot', 'reset'].includes(mode) && (
          <button
            className="auth-link"
            onClick={() => { setMode('login'); setError(''); setNotice(''); setResetLink(''); }}
            type="button"
          >
            Back to login
          </button>
        )}
        {onBack && !resetToken && (
          <button className="auth-link auth-back-welcome" onClick={onBack} type="button">
            Back to welcome page
          </button>
        )}
      </div>
    </div>
  );
}

