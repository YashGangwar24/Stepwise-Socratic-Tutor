import { useEffect, useState } from 'react';
import { getLearningInsights } from '../api';

const NEXT_STEPS = {
  LOOP_BOUNDS_OFF_BY_ONE: 'Try tracing a tiny list on paper, starting at index zero.',
  RECURSION_MISSING_BASE_CASE: 'Test the smallest input and decide exactly when the function should stop.',
  POINTER_NULL_DEREF: 'Check that a value exists before you access what it points to.',
  VARIABLE_SCOPE_CONFUSION: 'Check where the variable is created and whether this part of the code can see it.',
  TYPE_MISMATCH: 'Check the kind of each value before combining or comparing them.',
  CONDITIONAL_LOGIC: 'Trace one example through each branch and see which condition becomes true.',
  DATA_STRUCTURE_MISUSE: 'Review what your data structure makes easy: finding, ordering, or updating values.',
  COMPLEXITY_MISUNDERSTANDING: 'Count how many times the main step runs as the input gets larger.',
};

const FRIENDLY_LABELS = {
  LOOP_BOUNDS_OFF_BY_ONE: 'Counting one step too far',
  RECURSION_MISSING_BASE_CASE: 'Missing a stopping point',
  POINTER_NULL_DEREF: 'Using a value that may be empty',
  VARIABLE_SCOPE_CONFUSION: 'A variable is not available here',
  TYPE_MISMATCH: 'Mixing different kinds of values',
  CONDITIONAL_LOGIC: 'A condition sends the code the wrong way',
  DATA_STRUCTURE_MISUSE: 'Choosing how to store or find data',
  COMPLEXITY_MISUNDERSTANDING: 'Estimating how work grows',
};

function frequencyLabel(item) {
  if (item.is_sample) return 'Sample pattern';
  if (item.count >= 3) return 'Coming up often';
  if (item.count === 2) return 'Happened twice recently';
  return 'Worth reviewing';
}

export default function LearningInsights({ token }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    getLearningInsights(token).then((result) => active && setData(result))
      .catch(() => active && setError('Learning insights are temporarily unavailable.'));
    return () => { active = false; };
  }, [token]);
  return <section className="feature-panel">
    <p className="eyebrow">Learning insights</p><h2>Patterns in your practice</h2>
    <p>These are gentle reminders about ideas to practice. They are not grades. Sample-labeled patterns are examples; other patterns come from your recent chats.</p>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Loading your observations…</p>}
    {data && data.categories.length === 0 && <p>No practice patterns to show yet. Keep learning, and StepWise will offer a tip when a pattern is clear.</p>}
    {data?.categories?.map((item) => <article className="insight-card" key={`${item.code}-${item.is_sample ? 'sample' : 'learner'}`}>
      <div className="insight-card-heading">
        <h3>{FRIENDLY_LABELS[item.code] || item.label}</h3>
        <span className={`insight-frequency ${item.is_sample ? 'sample' : ''}`}>{frequencyLabel(item)}</span>
      </div>
      <div className="insight-bar" role="img" aria-label={`${frequencyLabel(item)}: ${item.count} observations`}>
        <i style={{ width: `${Math.max(8, item.count / Math.max(1, ...data.categories.map((x) => x.count)) * 100)}%` }} />
      </div>
      <p className="insight-tip"><strong>Next step:</strong> {NEXT_STEPS[item.code] || 'Try explaining your approach in small steps, then test it with a simple example.'}</p>
    </article>)}
    {data && <small>These suggestions refresh as you keep practicing.</small>}
  </section>;
}
