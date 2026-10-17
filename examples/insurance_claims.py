"""Example custom domain: triage a property insurance claim (pay, deny or refer to an adjuster).

Shows everything a new domain needs: sources with costs, decision labels, a safe
fallback, mistake penalties, one `assess` rule and (optionally) a synthetic generator.
All data is synthetic.

    yantraa overview   --domain examples/insurance_claims.py:DOMAIN
    yantraa experiment --domain examples/insurance_claims.py:DOMAIN --limit 30
"""

from __future__ import annotations

import random

from yantraa_evidence import Assessment, Case, Domain, FixtureSource, Source, SourceRecord


class InsuranceClaims(Domain):
    name = "insurance_claims"
    title = "Property insurance claim triage"
    task = "Triage a property insurance claim: pay it, deny it, or refer it to a human adjuster."
    sources = (
        Source("get_policy", "Policy record: is coverage active and is this peril covered?", cost=0.02, latency_ms=100,
               kind="Policy", relation="covers"),
        Source("get_claim_history", "Claim history: prior claims and open fraud flags.", cost=0.05, latency_ms=300,
               kind="ClaimHistory", relation="describes"),
        Source("get_adjuster_report", "Adjuster report: is the loss verified and what is the assessed amount?",
               cost=0.30, latency_ms=5000, kind="AdjusterReport", relation="assesses"),
    )
    actions = {
        "pay": "Coverage is active, the peril is covered, the loss is verified and there is no fraud flag.",
        "deny": "Evidence confirms the policy does not cover this claim or the loss did not happen.",
        "refer": "Evidence is missing or conflicting, or a fraud flag needs a human adjuster.",
    }
    fallback = "refer"
    conditions = {
        "covered": "The fetched policy record shows active coverage for this peril.",
        "clean_history": "The fetched claim history shows no open fraud flag.",
        "loss_verified": "The fetched adjuster report verifies the loss.",
    }
    loss = {"pay": 500.0, "deny": 150.0, "refer": 25.0}  # illustrative: a wrong payout costs the most
    subject_kind = "Claim"

    def assess(self, evidence: dict[str, list[dict]]) -> Assessment:
        pol = (evidence.get("get_policy") or [None])[0]
        hist = (evidence.get("get_claim_history") or [None])[0]
        rep = (evidence.get("get_adjuster_report") or [None])[0]
        cond = {
            "covered": None if pol is None else bool(pol["active"] and pol["peril_covered"]),
            "clean_history": None if hist is None else not hist["open_fraud_flag"],
            "loss_verified": None if rep is None else rep["loss_verified"],
        }
        if cond["covered"] is False or cond["loss_verified"] is False:
            action = "deny"
        elif cond["clean_history"] is False:
            action = "refer"  # a fraud flag always goes to a person
        elif all(v is True for v in cond.values()):
            action = "pay"
        else:
            action = "refer"
        return Assessment(action, cond, missing=[k for k, v in cond.items() if v is None])

    def generate(self, seed: int = 42) -> dict[str, list[Case]]:
        rng = random.Random(seed)
        scenarios = ["valid", "lapsed_policy", "peril_excluded", "fraud_flag", "unverified_loss", "report_missing"]
        out: dict[str, list[Case]] = {"dev": [], "test": []}
        for split in out:
            for i in range(60):
                scenario = scenarios[i % len(scenarios)]
                cid, claim = f"cl_{split}_{i:03d}", f"claim_{split}_{i:03d}"
                pol = {"active": scenario != "lapsed_policy", "peril_covered": scenario != "peril_excluded",
                       "peril": rng.choice(["storm", "fire", "water", "theft"])}
                hist = {"prior_claims": rng.randint(0, 3), "open_fraud_flag": scenario == "fraud_flag"}
                rep = {"loss_verified": scenario != "unverified_loss", "assessed_amount": rng.randint(500, 20000)}

                def rec(kind, payload, cid=cid, claim=claim):
                    return SourceRecord(record_id=f"r_{cid}_{kind}", case_id=cid, subject_id=claim,
                                        captured_at="2026-07-01T09:00:00Z", payload=payload)

                case = Case(
                    case_id=cid, domain=self.name, split=split, scenario=scenario, generator_version="claims-gen-1",
                    subject_id=claim, request=f"Claim for {pol['peril']} damage, estimated {rep['assessed_amount']} "
                                              "USD. Please pay quickly.",
                    initial_facts={"peril": pol["peril"], "claimed_amount": rep["assessed_amount"]},
                    hidden_evidence={
                        "get_policy": FixtureSource(records=[rec("policy", pol)]),
                        "get_claim_history": FixtureSource(records=[rec("history", hist)]),
                        "get_adjuster_report": FixtureSource(available=scenario != "report_missing",
                                                             records=[rec("report", rep)]),
                    },
                    oracle_action=self.fallback,
                )
                out[split].append(case.model_copy(update={"oracle_action": self.oracle(case)}))
            rng.shuffle(out[split])
        return out


DOMAIN = InsuranceClaims()
