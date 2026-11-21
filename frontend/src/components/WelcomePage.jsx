import { useState } from 'react';

const DEMOS = [
  {
    topic: 'Algorithms',
    prompt: 'Why does binary search need sorted data?',
    hints: [
      'Binary search removes half the possibilities after each comparison.',
      'That only works when the values on each side of the midpoint tell you where the target can be.',
      'What would happen if a smaller value could appear to the right of the midpoint?',
    ],
  },
  {
    topic: 'LAW',
    prompt: 'Why are fundamental rights important?',
    hints: [
      'They set important protections for people and limits on public power.',
      'Think about what could happen if a person had no way to challenge unfair treatment.',
      'Which protection do you think matters most in the example you have in mind?',
    ],
  },
  {
    topic: 'Biology',
    prompt: 'How do plants make their own food?',
    hints: [
      'Plants use light energy, water, and carbon dioxide in this process.',
      'A green pigment in leaves helps capture energy from sunlight.',
      'What useful substance do you think a plant makes from these ingredients?',
    ],
  },
  {
    topic: 'DBMS',
    prompt: 'Why does a database table need a primary key?',
    hints: [
      'A table can contain many rows with similar information.',
      'The database needs a reliable way to tell one row apart from every other row.',
      'What value could uniquely identify each student in a student table?',
    ],
  },
  {
    topic: 'Mathematics',
    prompt: 'Why does multiplying two negative numbers give a positive?',
    hints: [
      'Look for a pattern: three times negative two, then two, one, and zero times negative two.',
      'Each time the first number drops by one, the product changes by the same amount.',
      'What product must come next to keep that pattern consistent?',
    ],
  },
];

function Mark() {
  return <span className="welcome-mark" aria-hidden="true"><i /><b /></span>;
}

export default function WelcomePage({ onEnter, signedIn = false }) {
  const [activeDemo, setActiveDemo] = useState(0);
  const [hintIndex, setHintIndex] = useState(0);
  const demo = DEMOS[activeDemo];

  const selectDemo = (index) => {
    setActiveDemo(index);
    setHintIndex(0);
  };

  return (
    <main className="welcome-page">
      <div className="welcome-noise" aria-hidden="true" />
      <nav className="welcome-nav" aria-label="Main navigation">
        <a className="welcome-brand" href="#top" aria-label="StepWise home">
          <Mark /><span>StepWise</span>
        </a>
        <div className="welcome-nav-links">
          <a href="#approach">Our approach</a>
          <a href="#preview">Try a preview</a>
        </div>
        <button className="welcome-signin" onClick={onEnter}>{signedIn ? 'Open workspace' : 'Sign in'} <span aria-hidden="true">&#8599;</span></button>
      </nav>

      <section className="welcome-hero" id="top">
        <div className="welcome-copy">
          <div className="welcome-kicker"><span className="live-dot" /> A LOCAL SOCRATIC LEARNING STUDIO</div>
          <h1>Make the next<br />step <em>your own.</em></h1>
          <p className="welcome-lede">A thoughtful AI tutor that helps you work it out, one good question at a time.</p>
          <div className="welcome-actions">
            <button className="welcome-primary" onClick={onEnter}>{signedIn ? 'Continue to your studio' : 'Enter the studio'} <span aria-hidden="true">&#8599;</span></button>
            <a className="welcome-secondary" href="#preview"><span className="play-icon">&#9654;</span> Explore a sample</a>
          </div>
          <div className="welcome-proof">
            <span><i className="proof-orbit">&#10022;</i> Guided, not answer-first</span>
            <span><i className="proof-lock">&#9673;</i> Runs with your local model</span>
          </div>
        </div>

        <div className="welcome-visual" id="preview">
          <div className="orbit orbit-one" aria-hidden="true" />
          <div className="orbit orbit-two" aria-hidden="true" />
          <div className="orbit-core" aria-hidden="true"><span>&#10022;</span><i /></div>
          <span className="orbit-label orbit-label-top">THINK IT THROUGH</span>
          <span className="orbit-label orbit-label-bottom">YOUR PACE &middot; YOUR PATH</span>

          <article className="demo-card">
            <div className="demo-card-top">
              <div className="demo-card-brand"><Mark /><span>StepWise <small>guided preview</small></span></div>
              <span className="demo-live"><i /> LIVE DEMO</span>
            </div>
            <div className="demo-topic-tabs" role="tablist" aria-label="Choose a sample topic">
              {DEMOS.map((item, index) => <button
                key={item.topic}
                type="button"
                role="tab"
                aria-selected={activeDemo === index}
                className={activeDemo === index ? 'active' : ''}
                onClick={() => selectDemo(index)}
              >{item.topic}</button>)}
            </div>
            <div className="demo-conversation" aria-live="polite">
              <div className="demo-question"><span className="demo-avatar student-avatar">Y</span><p>{demo.prompt}</p></div>
              <div className="demo-answer">
                <span className="demo-avatar tutor-avatar"><Mark /></span>
                <div><small>STEPWISE ASKS</small><p>{demo.hints[hintIndex]}</p></div>
              </div>
            </div>
            <div className="demo-card-bottom">
              <span><i /> {hintIndex + 1} of {demo.hints.length} gentle hints</span>
              <button type="button" onClick={() => setHintIndex((index) => (index + 1) % demo.hints.length)}>
                Next thought <span aria-hidden="true">&#8594;</span>
              </button>
            </div>
          </article>
        </div>
        <a className="welcome-scroll" href="#approach"><span /> SCROLL TO EXPLORE</a>
      </section>

      <section className="welcome-approach" id="approach">
        <div className="approach-heading">
          <p className="welcome-kicker">A DIFFERENT KIND OF HELP</p>
          <h2>Less direct answers.<br /><em>More &quot;what do you notice?&quot;</em></h2>
          <p>StepWise gives you a nudge, then lets your reasoning do the work.</p>
        </div>
        <div className="approach-grid">
          <article><span className="approach-icon">&#8599;</span><small>01 / THINK</small><h3>Start with a question</h3><p>Break unfamiliar ideas into smaller, manageable steps.</p></article>
          <article><span className="approach-icon">&#43;</span><small>02 / EXPLORE</small><h3>Bring your real work</h3><p>Ask about code, attach notes, or talk through a tricky concept.</p></article>
          <article><span className="approach-icon">&#9673;</span><small>03 / GROW</small><h3>Notice your progress</h3><p>Revisit practice patterns and learn alongside a peer.</p></article>
        </div>
      </section>

      <footer className="welcome-footer">
        <a className="welcome-brand" href="#top"><Mark /><span>StepWise</span></a>
        <span>Learning, one thoughtful step at a time.</span>
        <button onClick={onEnter}>{signedIn ? 'Open workspace' : 'Get started'} <span aria-hidden="true">&#8599;</span></button>
      </footer>
    </main>
  );
}



