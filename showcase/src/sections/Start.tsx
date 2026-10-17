import { REPO } from "../data";

const DOMAIN = `from yantraa_evidence import Assessment, Domain, Experiment, Source, evaluate

class Chargebacks(Domain):
    name = "chargebacks"
    task = "Decide whether to accept a card chargeback."
    sources = (Source("get_transaction", "Transaction log", cost=0.01),
               Source("get_merchant_proof", "Delivery proof", cost=0.20),
               Source("get_dispute_history", "Prior disputes", cost=0.05))
    actions = {"accept": "...", "reject": "...", "review": "..."}
    fallback = "review"
    loss = {"accept": 80, "reject": 30, "review": 3}  # what mistakes cost you

    def assess(self, evidence):  # your rule; it also builds the answer key
        ...

result = Experiment(domain=Chargebacks(), cases=my_cases).run()
print(evaluate(result).to_text())`;

export function Start() {
  return (
    <div className="start">
      <div className="start-steps">
        <div className="start-step"><span className="step-k">1 · Overview</span><pre>pip install yantraa-evidence{"\n"}yantraa overview</pre>
          <p>Domains, evidence sources and costs, strategies, decision-makers.</p></div>
        <div className="start-step"><span className="step-k">2 · Experiment</span><pre>yantraa experiment --limit 40</pre>
          <p>Offline and free by default. Add <code>--provider openai</code> for a real model. Check <code>--estimate-only</code> first.</p></div>
        <div className="start-step"><span className="step-k">3 · Evaluate</span><pre>yantraa evaluate</pre>
          <p>Paired intervals against checking everything, and against your previous runs.</p></div>
      </div>
      <figure className="code-figure">
        <div className="term-bar"><span /><span /><span /> <em>your_domain.py</em></div>
        <pre>{DOMAIN}</pre>
      </figure>
      <div className="cta-row center">
        <a className="btn primary" href={REPO} target="_blank" rel="noreferrer">View on GitHub</a>
        <a className="btn" href="https://pypi.org/project/yantraa-evidence/" target="_blank" rel="noreferrer">PyPI</a>
        <a className="btn" href={`${REPO}/blob/main/docs/design.md`} target="_blank" rel="noreferrer">Read the method</a>
      </div>
    </div>
  );
}
