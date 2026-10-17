export function Question() {
  return (
    <div className="prose-block">
      <p>
        Every automated decision about money (a refund, a claim, a chargeback, an alert) has the same shape. A request comes in.
        A few records <em>could</em> be checked. Each check costs something: an API fee, a vendor lookup, an analyst's minutes,
        seconds of latency. And each kind of mistake has its own price: a wrong approval loses money, a wrong rejection loses a
        customer, and handing every case to a person defeats the point of automating.
      </p>
      <p>
        Checking everything is safe but wasteful. Checking nothing is cheap but reckless. Most teams pick a point in between by
        intuition, because they can't measure retrieval cost, model cost and decision quality <em>together</em>.
      </p>
      <div className="equation" role="img" aria-label="Total cost equals checks plus model calls plus mistake penalties">
        <div className="term total"><span className="term-k">Total cost</span><span className="term-d">per decision</span></div>
        <span className="op">=</span>
        <div className="term"><span className="term-k">Checks</span><span className="term-d">what each record lookup costs</span></div>
        <span className="op">+</span>
        <div className="term"><span className="term-k">Model calls</span><span className="term-d">tokens, at published prices</span></div>
        <span className="op">+</span>
        <div className="term"><span className="term-k">Mistakes</span><span className="term-d">your penalty for each wrong call</span></div>
      </div>
      <p>
        Yantraa Evidence makes that one number measurable, and compares <strong>strategies</strong> for gathering evidence on
        the same requests, under the same rules, with intervals that tell you whether a difference is real.
      </p>
    </div>
  );
}

function Flow() {
  const box = (x: number, y: number, w: number, title: string[], sub: string, accent = false) => (
    <g transform={`translate(${x}, ${y})`}>
      <rect width={w} height={84} rx={14} className={`flow-box ${accent ? "accent" : ""}`} />
      {title.map((t, i) => <text key={t} x={w / 2} y={(title.length === 1 ? 40 : 32) + i * 19} textAnchor="middle" className="flow-title">{t}</text>)}
      <text x={w / 2} y={70} textAnchor="middle" className="flow-sub">{sub}</text>
    </g>
  );
  return (
    <svg viewBox="0 0 920 236" className="flow" role="img"
         aria-label="A request goes to a strategy, which repeatedly checks an evidence source or stops. A shared decision-maker then decides; the decision is graded against an answer key and priced.">
      <defs>
        <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" className="flow-head" />
        </marker>
      </defs>
      {[[128, 168], [330, 368], [530, 568], [730, 768]].map(([a, b]) => (
        <line key={a} x1={a} x2={b} y1={50} y2={50} className="flow-line" markerEnd="url(#ah)" />
      ))}
      <line x1={226} x2={226} y1={92} y2={142} className="flow-line" markerEnd="url(#ah)" />
      <line x1={272} x2={272} y1={142} y2={92} className="flow-line" markerEnd="url(#ah)" />
      <text x={218} y={122} textAnchor="end" className="flow-note">check</text>
      <text x={280} y={122} className="flow-note">evidence</text>
      <text x={349} y={40} textAnchor="middle" className="flow-note">stop</text>
      {box(0, 8, 128, ["Request"], "message + facts")}
      {box(168, 8, 162, ["Strategy"], "check, or stop?", true)}
      {box(168, 146, 162, ["Evidence sources"], "each check costs")}
      {box(368, 8, 162, ["Decision-maker"], "same for every strategy")}
      {box(568, 8, 162, ["Answer key"], "right or wrong?")}
      {box(768, 8, 152, ["Total cost"], "all three, added up")}
      <text x={844} y={124} textAnchor="middle" className="flow-note">compared across</text>
      <text x={844} y={142} textAnchor="middle" className="flow-note">strategies, paired</text>
      <text x={844} y={160} textAnchor="middle" className="flow-note">by request, 95% CIs</text>
    </svg>
  );
}

export function HowItWorks() {
  return (
    <>
      <figure className="wide-figure">
        <Flow />
        <figcaption><span className="fig-n">Figure 6.</span> The loop every strategy runs. Only the strategy changes; the
          decision-maker, its instructions and its limits are shared, so differences come from which evidence was checked.</figcaption>
      </figure>
      <div className="principles">
        <div><h4>A strict information boundary</h4><p>The decision-maker sees only what has been fetched. Never the answer
          key, never unchecked records, never the case's label. Tests enforce it.</p></div>
        <div><h4>Fails safe, and says why</h4><p>Limits on checks, calls, time and spend are enforced before each call.
          Any failure falls back to a person, with the reason recorded. No silent retries.</p></div>
        <div><h4>Honest numbers</h4><p>Paired bootstrap intervals, penalty-sensitivity analysis, and unknown prices reported
          as unknown, never as zero. Every run is reproducible from its config hash and trace.</p></div>
      </div>
    </>
  );
}
