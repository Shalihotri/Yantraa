# Use cases and personas

Yantraa Evidence fits any decision with this shape:

1. A **request** arrives (a message, a claim, an alert, an application).
2. Several **records can be checked** before deciding, each with a cost (fees, API calls, analyst time, latency).
3. The decision is one of a few **labels**, with a **safe fallback** (refer to a person, hold, escalate).
4. **Mistakes have different prices** (a wrong approval usually costs more than a wrong referral).

If that describes your problem, write a `Domain` (one class, see the
[insurance example](../examples/insurance_claims.py)), and compare strategies on your own costs.

> Every example below is a *template for synthetic or anonymised data*. Do not put personal, health or account data
> into case files you commit or share.

## By industry

| Industry | Decision | Evidence sources (example costs) | Labels (fallback in bold) | What a wrong choice costs |
|---|---|---|---|---|
| **Retail / e-commerce** *(built in: `returns`)* | Approve a product return | order record, return policy, inspection report | approve, reject, **escalate** | wrong approval loses the refund; wrong rejection loses the customer |
| **Insurance** *(example: `insurance_claims`)* | Triage a property claim | policy coverage, claim history and fraud flags, adjuster report (expensive, slow) | pay, deny, **refer** | wrong payout ≫ wrong denial > unnecessary referral |
| **Banking / fintech** | Resolve a card chargeback | transaction log, merchant evidence, customer history, device signals | accept, reject, **review** | accepting fraud vs. losing a good customer |
| **Banking / compliance** | Clear an AML or KYC alert | sanctions screening, ID verification, transaction pattern report | clear, file report, **escalate** | a missed report is far costlier than an extra review |
| **Lending** | Approve a loan exception | credit bureau pull (fee), income verification, collateral appraisal | approve, decline, **manual underwriting** | default loss vs. lost revenue |
| **Healthcare administration** | Prior-authorization review | coverage rules, claim history, clinical documentation summary | approve, deny, **clinician review** | wrong denial delays care; wrong approval costs the payer |
| **Telecom / SaaS** | Billing dispute credit | invoice, usage logs, plan terms, support history | credit, decline, **escalate** | over-crediting vs. churn |
| **Logistics** | Delivery exception claim | tracking scans, proof-of-delivery photo, carrier report | reimburse, deny, **investigate** | paying false claims vs. carrier disputes |
| **IT / security operations** | Access request or alert triage | identity directory, entitlement policy, manager attestation, recent activity | grant / close, deny / contain, **escalate** | over-granting access vs. blocking work |
| **Public sector** | Benefits eligibility pre-check | application form, registry lookups, income records | eligible, ineligible, **caseworker review** | wrongful denial vs. improper payment |

## By persona

| You are… | You want to know… | Start with |
|---|---|---|
| **AI / ML engineer** | Does my agent's *retrieval policy* save money without losing accuracy, and where does it fail? | `Experiment(...).run()` → `evaluate(...).mistakes`, then a traced `run_case` per failure |
| **Product or operations lead** | Does a strategy win *with my costs*, and how sure are we? | Put your check costs and mistake penalties in `overrides` or `config/default.yaml`; read the paired verdict and penalty sensitivity |
| **Risk / compliance officer** | Can the system ever skip a check it must not skip, and does it fall back safely? | Fallback rate, `wrong_<label>` counts, stop reasons, the evidence graph per decision |
| **Researcher** | A controlled, reproducible test bed for selective evidence gathering | Seeded generator, locked `test` split, paired bootstrap, JSONL traces |
| **Platform / app developer** | Build a review console, dashboard or API on top | `overview()`, `Experiment`, `evaluate()` all return plain dicts / dataclasses; results also live in SQLite and CSV/JSONL exports |
| **Data / analytics team** | Compare this week's prompt or model with last week's | `compare_to_baseline(new_batch, old_batch)` or `yantraa evaluate NEW --against OLD` |

## Typical workflow

1. **Overview**: check the domain, sources, costs, penalties and data (`yantraa overview`).
2. **Experiment**: run Practice (mock) first to check the mechanics for free, then a *small* live run to check
   behaviour; always look at `estimate()` first.
3. **Evaluate**: read the paired verdict against `fetch_all`, the penalty sensitivity and every mistake. Compare
   with your previous saved experiment before changing anything else.
4. Tune on `dev`; run `test` once at the end.
