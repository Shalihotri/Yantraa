const CASES = [
  { industry: "Retail", decision: "Approve a product return", tag: "Built in",
    sources: ["Order", "Return policy", "Inspection"], labels: ["approve", "reject", "escalate"],
    mistake: "Wrong approval loses the refund; wrong rejection loses the customer." },
  { industry: "Insurance", decision: "Triage a property claim", tag: "Example included",
    sources: ["Coverage", "Claim history", "Adjuster report"], labels: ["pay", "deny", "refer"],
    mistake: "A wrong payout costs far more than a referral." },
  { industry: "Banking", decision: "Resolve a chargeback",
    sources: ["Transaction log", "Merchant proof", "Dispute history"], labels: ["accept", "reject", "review"],
    mistake: "Accepting fraud vs. losing a good customer." },
  { industry: "Compliance", decision: "Clear an AML / KYC alert",
    sources: ["Sanctions screen", "ID verification", "Transaction pattern"], labels: ["clear", "report", "escalate"],
    mistake: "A missed report is far costlier than an extra review." },
  { industry: "Lending", decision: "Approve a loan exception",
    sources: ["Bureau pull", "Income check", "Appraisal"], labels: ["approve", "decline", "underwrite"],
    mistake: "Default loss vs. lost revenue." },
  { industry: "Healthcare admin", decision: "Prior-authorization review",
    sources: ["Coverage rules", "Claim history", "Clinical summary"], labels: ["approve", "deny", "clinician"],
    mistake: "A wrong denial delays care; a wrong approval costs the payer." },
  { industry: "Telecom / SaaS", decision: "Billing dispute credit",
    sources: ["Invoice", "Usage logs", "Plan terms"], labels: ["credit", "decline", "escalate"],
    mistake: "Over-crediting vs. churn." },
  { industry: "Logistics", decision: "Delivery exception claim",
    sources: ["Tracking scans", "Proof of delivery", "Carrier report"], labels: ["reimburse", "deny", "investigate"],
    mistake: "Paying false claims vs. carrier disputes." },
  { industry: "Security", decision: "Access request triage",
    sources: ["Directory", "Entitlement policy", "Manager sign-off"], labels: ["grant", "deny", "escalate"],
    mistake: "Over-granting vs. blocking work." },
];

const PEOPLE = [
  ["ML engineers", "benchmark an agent's retrieval policy, not just its answers, and replay every failure step by step."],
  ["Product & operations leads", "plug in what checks and mistakes cost the business, and see whether a strategy still wins."],
  ["Risk & compliance", "verify the fallback behaviour, mistakes by label, and which evidence supported each decision."],
  ["Researchers", "start from a seeded, reproducible test bed with a locked held-out set and exportable traces."],
];

export function Fit() {
  return (
    <>
      <div className="fit-grid">
        {CASES.map((c) => (
          <article key={c.decision} className="fit-card">
            <div className="fit-top"><span className="fit-industry">{c.industry}</span>{c.tag && <span className="tag">{c.tag}</span>}</div>
            <h4>{c.decision}</h4>
            <p className="fit-line"><span className="fit-k">Checks</span>{c.sources.join(" · ")}</p>
            <p className="fit-line"><span className="fit-k">Decides</span>{c.labels.slice(0, 2).join(" · ")} · <strong>{c.labels[2]}</strong></p>
            <p className="fit-mistake">{c.mistake}</p>
          </article>
        ))}
      </div>
      <div className="people">
        {PEOPLE.map(([who, what]) => <p key={who}><strong>{who}</strong> {what}</p>)}
      </div>
    </>
  );
}
