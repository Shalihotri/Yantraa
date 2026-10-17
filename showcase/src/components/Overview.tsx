const REPO = "https://github.com/Shalihotri/Yantraa";

function FlowDiagram() {
  const boxes = [
    { x: 10, y: 20, w: 120, t: ["Request"], s: "message + facts" },
    { x: 170, y: 20, w: 150, t: ["Strategy picks", "the next step"], s: "check or stop" },
    { x: 170, y: 140, w: 150, t: ["Evidence sources"], s: "each check costs" },
    { x: 360, y: 20, w: 150, t: ["Shared", "decision-maker"], s: "same for every strategy" },
    { x: 550, y: 20, w: 140, t: ["Grade vs", "answer key"], s: "right or wrong" },
    { x: 730, y: 20, w: 160, t: ["Total cost"], s: "checks + AI + mistakes" },
  ];
  const H = 228;
  return (
    <svg viewBox={`0 0 900 ${H}`} className="flow" role="img"
         aria-label="Request, then a strategy repeatedly picks an evidence source to check or stops, then a shared decision-maker decides, the decision is graded against the answer key, and total cost is computed.">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head" />
        </marker>
      </defs>
      {[[130, 60, 170, 60], [320, 60, 360, 60], [510, 60, 550, 60], [690, 60, 730, 60]].map(([x1, y1, x2, y2], i) => (
        <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} className="flow-edge" markerEnd="url(#arrow)" />
      ))}
      <path d="M 225 100 L 225 140" className="flow-edge" markerEnd="url(#arrow)" />
      <path d="M 265 140 L 265 100" className="flow-edge" markerEnd="url(#arrow)" />
      <text x={190} y={124} className="flow-note">check</text>
      <text x={272} y={124} className="flow-note">evidence</text>
      <text x={326} y={50} className="flow-note">stop</text>
      {boxes.map((b) => (
        <g key={b.t.join()} transform={`translate(${b.x}, ${b.y})`}>
          <rect width={b.w} height={80} rx={12} className="flow-box" />
          {b.t.map((l, i) => (
            <text key={l} x={b.w / 2} y={(b.t.length === 1 ? 36 : 28) + i * 18} textAnchor="middle" className="flow-title">{l}</text>
          ))}
          <text x={b.w / 2} y={66} textAnchor="middle" className="flow-sub">{b.s}</text>
        </g>
      ))}
      <text x={810} y={124} textAnchor="middle" className="flow-note">compared across strategies</text>
      <text x={810} y={142} textAnchor="middle" className="flow-note">with paired 95% intervals</text>
    </svg>
  );
}

const FINDINGS = [
  {
    title: "It over-trusted the customer",
    body: "When the customer's story contradicted the records (“it never arrived”, but the order shows delivered), the model's own per-condition judgements were right, about 1.0 for delivered, in window and damaged, yet its final answer was often “reject”.",
  },
  {
    title: "“Stop when confident” never checked anything",
    body: "The model was already at least 85% sure it should escalate before seeing any evidence, so the confidence rule stopped immediately on every request.",
  },
  {
    title: "Letting the AI choose didn't save on checks",
    body: "It fetched all three records every time. Its lower total cost came from making one fewer mistake, not from checking less.",
  },
];

export function Overview({ onExplore }: { onExplore: () => void }) {
  return (
    <div className="overview">
      <section className="hero">
        <h1>Does checking less evidence make AI decisions cheaper, without making them worse?</h1>
        <p className="lede">
          Before an AI approves a refund, pays a claim or clears an alert, it checks records. Every check costs money
          and time, and every wrong decision costs more. <strong>Yantraa Evidence</strong> is an open-source Python
          package that measures which evidence-gathering strategy gives the best decisions for the money, in your domain
          and with your costs.
        </p>
        <div className="hero-actions">
          <button className="primary" onClick={onExplore}>Explore a decision →</button>
          <code className="install">pip install yantraa-evidence</code>
          <a href={REPO} target="_blank" rel="noreferrer">View on GitHub</a>
        </div>
      </section>

      <section className="card">
        <h2>How it works</h2>
        <FlowDiagram />
        <p className="sub">
          The decision-maker only sees what has been fetched, never the answer key. Every strategy shares the same
          decision-maker, instructions and limits, so differences come from which evidence was checked.
        </p>
      </section>

      <section>
        <h2>Three steps, from Python or the terminal</h2>
        <div className="steps">
          <div className="card step">
            <span className="step-n">1</span><h3>Overview</h3>
            <p>See the domain, its evidence sources and costs, the strategies and the decision-makers.</p>
            <pre className="code">yantraa overview</pre>
          </div>
          <div className="card step">
            <span className="step-n">2</span><h3>Experiment</h3>
            <p>Design a comparison with your own check costs and mistake penalties, then run it offline or with a real model.</p>
            <pre className="code">yantraa experiment --limit 40</pre>
          </div>
          <div className="card step">
            <span className="step-n">3</span><h3>Evaluate</h3>
            <p>Compare every strategy against the check-everything baseline and earlier runs, with 95% intervals.</p>
            <pre className="code">yantraa evaluate</pre>
          </div>
        </div>
      </section>

      <section className="card findings">
        <h2>First findings with a real model</h2>
        <p className="sub">
          OpenAI Decisions API, <code>gpt-6-luna</code>, retail returns, 10 practice requests. A small sample: these
          are leads for the next experiments, not conclusions.
        </p>
        <div className="finding-grid">
          {FINDINGS.map((f, i) => (
            <article key={f.title} className="finding">
              <span className="step-n">{i + 1}</span>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
