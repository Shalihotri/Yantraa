const REPO = "https://github.com/Shalihotri/Yantraa";

const CASES = [
  { industry: "Retail / e-commerce", decision: "Approve a product return", tag: "built in",
    sources: ["Order record", "Return policy", "Inspection report"], labels: ["approve", "reject"], fallback: "escalate",
    mistake: "A wrong approval loses the refund; a wrong rejection loses the customer." },
  { industry: "Insurance", decision: "Triage a property claim", tag: "example included",
    sources: ["Policy coverage", "Claim history", "Adjuster report"], labels: ["pay", "deny"], fallback: "refer",
    mistake: "A wrong payout costs far more than an unnecessary referral." },
  { industry: "Banking / fintech", decision: "Resolve a card chargeback",
    sources: ["Transaction log", "Merchant evidence", "Customer history"], labels: ["accept", "reject"], fallback: "review",
    mistake: "Accepting fraud vs. losing a good customer." },
  { industry: "Compliance", decision: "Clear an AML or KYC alert",
    sources: ["Sanctions screening", "ID verification", "Transaction pattern"], labels: ["clear", "file report"], fallback: "escalate",
    mistake: "A missed report is far costlier than an extra review." },
  { industry: "Lending", decision: "Approve a loan exception",
    sources: ["Credit bureau pull", "Income verification", "Collateral appraisal"], labels: ["approve", "decline"],
    fallback: "manual underwriting", mistake: "Default loss vs. lost revenue." },
  { industry: "Healthcare administration", decision: "Prior-authorization review",
    sources: ["Coverage rules", "Claim history", "Clinical summary"], labels: ["approve", "deny"], fallback: "clinician review",
    mistake: "A wrong denial delays care; a wrong approval costs the payer." },
  { industry: "Telecom / SaaS", decision: "Billing dispute credit",
    sources: ["Invoice", "Usage logs", "Plan terms"], labels: ["credit", "decline"], fallback: "escalate",
    mistake: "Over-crediting vs. churn." },
  { industry: "Logistics", decision: "Delivery exception claim",
    sources: ["Tracking scans", "Proof of delivery", "Carrier report"], labels: ["reimburse", "deny"], fallback: "investigate",
    mistake: "Paying false claims vs. carrier disputes." },
  { industry: "IT / security operations", decision: "Access request or alert triage",
    sources: ["Identity directory", "Entitlement policy", "Manager attestation"], labels: ["grant", "deny"], fallback: "escalate",
    mistake: "Over-granting access vs. blocking work." },
];

const PERSONAS = [
  ["AI / ML engineer", "Benchmark an agent's retrieval policy, not just its answers, and trace every failure step by step."],
  ["Product or ops lead", "Enter what checks and mistakes cost your business and see whether a strategy still wins."],
  ["Risk / compliance", "Verify fallback behaviour, mistakes by label, and which evidence supported each decision."],
  ["App developer", "Build a review console or dashboard on plain Python objects, SQLite and CSV/JSONL exports."],
];

const SNIPPET = `from yantraa_evidence import Assessment, Domain, Experiment, Source, evaluate

class Chargebacks(Domain):
    name = "chargebacks"
    task = "Decide whether to accept a card chargeback."
    sources = (Source("get_transaction", "Transaction log", cost=0.01),
               Source("get_merchant_evidence", "Delivery proof", cost=0.20),
               Source("get_customer_history", "Prior disputes", cost=0.05))
    actions = {"accept": "...", "reject": "...", "review": "..."}
    fallback = "review"
    loss = {"accept": 80, "reject": 30, "review": 3}   # what mistakes cost you

    def assess(self, evidence):      # your rule; also builds the answer key
        ...
        return Assessment(action, conditions)

result = Experiment(domain=Chargebacks(), cases=my_cases).run()
print(evaluate(result).to_text())`;

export function UseCases() {
  return (
    <div className="usecases">
      <section className="hero compact">
        <h1>Does it fit your decision?</h1>
        <p className="lede">
          It fits if a request comes in, a few records <em>could</em> be checked at a cost, the outcome is one of a few
          labels with a safe fallback, and mistakes have different prices. One Python class describes your domain.
        </p>
      </section>
      <div className="uc-grid">
        {CASES.map((c) => (
          <article key={c.industry} className="card uc">
            <div className="uc-head"><span className="uc-industry">{c.industry}</span>{c.tag && <span className="chip">{c.tag}</span>}</div>
            <h3>{c.decision}</h3>
            <div className="uc-flow">
              <span className="uc-step">Request</span><span className="uc-arrow">→</span>
              <span className="uc-sources">{c.sources.map((s) => <span key={s} className="chip outline">{s}</span>)}</span>
              <span className="uc-arrow">→</span>
              <span className="uc-sources">
                {c.labels.map((l) => <span key={l} className="chip">{l}</span>)}
                <span className="chip fallback" title="Safe fallback">{c.fallback}</span>
              </span>
            </div>
            <p className="sub">{c.mistake}</p>
          </article>
        ))}
      </div>
      <div className="grid-2">
        <section className="card">
          <h2>Who it helps</h2>
          <dl className="personas">
            {PERSONAS.map(([p, d]) => <div key={p}><dt>{p}</dt><dd>{d}</dd></div>)}
          </dl>
        </section>
        <section className="card">
          <h2>Your domain in one class</h2>
          <pre className="code block">{SNIPPET}</pre>
          <p className="sub">
            Full example: <a href={`${REPO}/blob/main/examples/insurance_claims.py`} target="_blank" rel="noreferrer">insurance claims</a>.
            More industries: <a href={`${REPO}/blob/main/docs/use-cases.md`} target="_blank" rel="noreferrer">use cases</a>.
          </p>
        </section>
      </div>
    </div>
  );
}
