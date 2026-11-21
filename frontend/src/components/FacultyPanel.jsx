import { useState } from 'react';
import { createSyllabusMapping } from '../api';
import { SUBJECTS } from '../subjects';

const defaultForm = {
  subject: 'Algorithms',
  module: '',
  chapter: '',
  persona: '',
};

export default function FacultyPanel({ token, mappings, onRefresh }) {
  const [form, setForm] = useState(defaultForm);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await createSyllabusMapping(
        {
          subject: form.subject,
          module: form.module,
          chapter: form.chapter,
          persona: form.persona,
        },
        token
      );
      setForm(defaultForm);
      if (onRefresh) {
        await onRefresh();
      }
    } catch (err) {
      setError(err?.response?.data?.detail || 'Unable to save syllabus mapping');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="faculty-panel">
      <div className="faculty-header">
        <div>
          <p className="eyebrow">Faculty tools</p>
          <h3>Syllabus mapping</h3>
        </div>
      </div>

      <form className="faculty-form" onSubmit={handleSubmit}>
        <div className="faculty-grid">
          <label>
            <span>Subject</span>
            <select
              value={form.subject}
              onChange={(e) => handleChange('subject', e.target.value)}
              className="text-input"
              required
            >
              {SUBJECTS.map((subject) => <option key={subject} value={subject}>{subject}</option>)}
            </select>
          </label>

          <label>
            <span>Module</span>
            <input
              value={form.module}
              onChange={(e) => handleChange('module', e.target.value)}
              placeholder="Module 3"
              className="text-input"
              required
            />
          </label>

          <label>
            <span>Chapter</span>
            <input
              value={form.chapter}
              onChange={(e) => handleChange('chapter', e.target.value)}
              placeholder="Recursion"
              className="text-input"
              required
            />
          </label>
        </div>

        <label>
          <span>Persona guidance</span>
          <textarea
            value={form.persona}
            onChange={(e) => handleChange('persona', e.target.value)}
            placeholder="Focus on recursion trees and proof by induction."
            className="text-input faculty-textarea"
            rows={4}
          />
        </label>

        {error && <div className="auth-error">{error}</div>}

        <button type="submit" className="primary-button" disabled={loading}>
          {loading ? 'Saving...' : 'Save mapping'}
        </button>
      </form>

      <div className="mapping-list">
        <h4>Saved mappings</h4>
        {(!mappings || mappings.length === 0) ? (
          <p className="empty-note">No syllabus mappings yet.</p>
        ) : (
          <ul>
            {mappings.map((mapping) => (
              <li key={mapping.id}>
                <strong>{mapping.subject}</strong>
                <span>{mapping.module} · {mapping.chapter}</span>
                {mapping.persona && <small>{mapping.persona}</small>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
