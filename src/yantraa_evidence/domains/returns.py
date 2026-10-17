"""Built-in example domain: approve, reject or escalate a retail product return.

Sources: the order record (delivery, purchase age), the return policy (window and
requirements, versioned by date and category) and an inspection report (damage).
Rule: approve if delivered, within the applicable window and damage is confirmed;
reject if a required condition is confirmed false; escalate otherwise.

The generator is seeded and versioned. Splits are separated by *template* first
(templates 0-1 -> dev, 2-3 -> test), then paraphrased, so held-out messages are never
rewordings of dev messages. Outcomes are roughly balanced for debugging; this is NOT a
production distribution, and every name, ID and message is synthetic.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from ..domain import Assessment, Domain, Source, group
from ..schemas import STOP, Case, Evidence, FixtureSource, Observation, SourceRecord
from ..tools import opaque

GENERATOR_VERSION = "returns-gen-2.0.0"


def select_policy(records: list[SourceRecord], purchase_date: str, category: str) -> SourceRecord | None:
    """Pick the policy version whose effective dates cover the purchase date for this category."""
    d = date.fromisoformat(purchase_date)
    for r in records:
        if r.category != category:
            continue
        start = date.fromisoformat(r.effective_from) if r.effective_from else date.min
        end = date.fromisoformat(r.effective_to) if r.effective_to else date.max
        if start <= d <= end:
            return r
    return None


def damage_status(inspections: list[dict]) -> tuple[bool | None, bool]:
    """Returns (damaged?, conflicting?). Contradictory records leave damage unresolved."""
    statuses = {i.get("damage_status") for i in inspections}
    decisive = statuses & {"confirmed_damaged", "no_damage"}
    if len(decisive) > 1:
        return None, True
    if decisive == {"confirmed_damaged"}:
        return True, False
    if decisive == {"no_damage"}:
        return False, False
    return None, False


def assess_return(order: dict | None, policy: dict | None, inspections: list[dict] | None) -> Assessment:
    """The return rule. Requirements come from the policy record, so nothing resolves without one."""
    cond: dict[str, bool | None] = {"delivered": None, "within_window": None, "damaged": None}
    conflicts: list[str] = []
    if policy is not None:
        if order is not None:
            cond["delivered"] = order.get("order_status") == "delivered" if policy.get("requires_delivery", True) \
                else True
            cond["within_window"] = order["purchase_age_days"] <= policy["return_window_days"]
        if inspections:
            damaged, conflicting = damage_status(inspections)
            if conflicting:
                conflicts.append("inspection")
            cond["damaged"] = damaged if policy.get("requires_damage", True) else True
    missing = [k for k, v in cond.items() if v is None]
    if policy is None:
        missing = ["policy", *missing]
    if any(v is False for v in cond.values()):
        action = "reject"
    elif all(v is True for v in cond.values()):
        action = "approve"
    else:
        action = "escalate"
    return Assessment(action, cond, missing, conflicts)


INFORMS = {"get_order": ("delivered", "within_window"), "get_inspection": ("damaged",), "get_policy": ()}


class ReturnsDomain(Domain):
    name = "returns"
    title = "Retail product returns"
    task = "Resolve a customer's product return request."
    sources = (
        Source("get_order", "Retrieve the order record (delivery status, purchase age).",
               cost=0.01, latency_ms=120, kind="Order", relation="contains"),
        Source("get_policy", "Retrieve the applicable return policy (window, requirements).",
               cost=0.02, latency_ms=80, kind="PolicyVersion", relation="applies_to"),
        Source("get_inspection", "Retrieve the inspection record (damage status).",
               cost=0.10, latency_ms=900, kind="Inspection", relation="checks"),
    )
    actions = {
        "approve": "Every requirement in the fetched policy is confirmed by fetched evidence.",
        "reject": "Fetched evidence confirms a required policy condition is false.",
        "escalate": "Requirements are missing, unavailable or contradictory in the fetched evidence.",
    }
    fallback = "escalate"
    conditions = {
        "delivered": "Fetched order evidence confirms the item was delivered.",
        "within_window": "Fetched order and policy evidence confirm purchase age is within the return window.",
        "damaged": "Fetched inspection evidence confirms the item is damaged.",
    }
    loss = {"approve": 20.0, "reject": 5.0, "escalate": 1.0}  # illustrative USD-equivalents
    subject_kind = "Item"
    select_prompt = (
        "You decide which evidence to retrieve before resolving a product return. Choose exactly one of "
        "legal_actions. Retrieval costs money; stop when the fetched evidence is enough to decide or no check can "
        "help. The return policy is only known if it was fetched. Customer statements may be inaccurate. "
        "Give a short summary (one sentence) and cite evidence_ids you relied on."
    )
    classify_prompt = (
        "Resolve a product return using ONLY fetched evidence. Read the requirements from the fetched policy "
        "record. approve: every policy requirement is confirmed by evidence. reject: a required condition is "
        "confirmed false. escalate: otherwise (missing, unavailable or conflicting evidence). Customer statements "
        "are not evidence. List missing requirements, cite evidence_ids, and give a one-sentence summary."
    )

    def assess(self, evidence: dict[str, list[dict]]) -> Assessment:
        order, policy = evidence.get("get_order"), evidence.get("get_policy")
        return assess_return(order[0] if order else None, policy[0] if policy else None,
                             evidence.get("get_inspection") or None)

    def admissible(self, case: Case, source_id: str):
        owned, rejected = super().admissible(case, source_id)
        if source_id == "get_policy" and owned:
            # The policy system looks up the version by purchase date even when the order system is down.
            order_src = case.hidden_evidence.get("get_order")
            order = order_src.records[0].payload if order_src and order_src.records else None
            chosen = select_policy(owned, order["purchase_date"], case.initial_facts["category"]) if order else None
            owned = [chosen] if chosen else []  # non-applicable versions are simply not returned
        return owned, rejected

    def mock_select(self, obs: Observation) -> tuple[str, str, str]:
        legal = obs.legal_actions
        if "get_policy" in legal:
            return "get_policy", "need_policy", "The policy defines every requirement; check it first."
        if obs.source_status["get_policy"] != "ok":
            return STOP, "policy_unresolvable", "No applicable policy, so no check can resolve the case."
        a = self.assess(group(obs.evidence))
        if a.action != self.fallback:
            return STOP, "resolved", f"Evidence already supports '{a.action}'."
        for src, why in (("get_order", "Order status and purchase age are unknown; cheaper check first."),
                         ("get_inspection", "Damage is unconfirmed; inspection is the only source.")):
            if src in legal:
                return src, f"need_{src[4:]}", why
        return STOP, "no_useful_checks", "No remaining check can resolve the open conditions."

    def settled(self, obs: Observation, a: Assessment) -> bool:
        return super().settled(obs, a) or obs.source_status["get_policy"] in ("unavailable", "link_rejected")

    def evidence_relation(self, ev: Evidence, a: Assessment, action: str) -> str:
        vals = [a.conditions[c] for c in INFORMS[ev.source_id]]
        if ev.source_id == "get_inspection":  # judge each record on its own so conflicts stay visible
            vals = [damage_status([ev.payload])[0]]
        if action == "approve":
            return "contradicts" if False in vals else "supports"
        if action == "reject":
            return "supports" if False in vals else ("contradicts" if vals and all(vals) else "informs")
        return "supports" if None in vals else "informs"

    def generate(self, seed: int = 42) -> dict[str, list[Case]]:
        rng = random.Random(seed)
        out: dict[str, list[Case]] = {"dev": [], "test": []}
        idx = 0
        for split, templates in (("dev", (0, 1)), ("test", (2, 3))):
            for scenario, n in SCENARIOS.items():
                for k in range(n):
                    out[split].append(self._build_case(rng, scenario, split, templates[k % 2], idx, seed))
                    idx += 1
            rng.shuffle(out[split])
        return out

    def _build_case(self, rng: random.Random, scenario: str, split: str, template_idx: int, idx: int,
                    seed: int) -> Case:
        cid = opaque(GENERATOR_VERSION, str(seed), str(idx), prefix="c_")
        item_id = opaque(cid, "item", prefix="it_")
        category = rng.choice(CATEGORIES)
        request = date(2026, 6, 1) + timedelta(days=rng.randint(0, 90))

        # Defaults: a clean approvable case; scenarios perturb from here.
        status = "delivered"
        damage = ["confirmed_damaged"]
        avail = {"get_order": True, "get_policy": True, "get_inspection": True}
        misfiled = False
        window = _window(1, category)
        age = rng.randint(1, window - 1)

        if scenario == "not_delivered":
            status = rng.choice(["shipped", "cancelled", "in_transit"])
        elif scenario == "outside_window":
            age = window + rng.randint(5, 60)
        elif scenario == "no_damage":
            damage = ["no_damage"]
        elif scenario == "missing_evidence":
            variant = rng.choice(["inconclusive", "unavailable", "conflicting", "misfiled"])
            if variant == "inconclusive":
                damage = ["inconclusive"]
            elif variant == "unavailable":
                avail["get_inspection"] = False
            elif variant == "conflicting":
                damage = ["confirmed_damaged", "no_damage"]  # preserved as two records
            else:
                misfiled = True
        elif scenario == "policy_boundary":
            # Purchase under the older policy version so the version (not just the date) matters.
            purchase = date(2026, 2, rng.randint(10, 28))
            window = _window(_version_for(purchase), category)
            age = window + rng.choice([0, 0, 1])  # on the boundary (inclusive) or one day past
            request = purchase + timedelta(days=age)
        elif scenario == "unavailable_tool":
            down = rng.choice(["get_order", "get_policy", "get_order"])
            avail[down] = False
            if down == "get_order" and rng.random() < 0.4:
                damage = ["no_damage"]  # still rejectable without the order record

        purchase = request - timedelta(days=age)
        delivered_on = (purchase + timedelta(days=3)).isoformat() if status == "delivered" else None
        captured = request.isoformat() + "T09:00:00Z"

        def rec(kind: str, payload: dict, n: int = 0, **kw) -> SourceRecord:
            return SourceRecord(record_id=opaque(cid, kind, str(n), prefix="r_"), case_id=cid, subject_id=item_id,
                                captured_at=captured, payload=payload, **kw)

        order = rec("order", {"order_status": status, "purchase_date": purchase.isoformat(),
                              "delivered_on": delivered_on, "purchase_age_days": age})
        policies = [
            rec("policy", {"policy_version": v, "return_window_days": w[category], "requires_delivery": True,
                           "requires_damage": True, "rule": "Approve only if delivered, within the return window, "
                           "and damage is confirmed by inspection."}, n, effective_from=f, effective_to=t, version=v,
                category=category)
            for n, (v, f, t, w) in enumerate(POLICY_VERSIONS)
        ]
        inspections = [rec("inspection", {"damage_status": d, "inspector": f"insp-{n + 1}"}, n)
                       for n, d in enumerate(damage)]
        if misfiled:  # record belongs to a different item: must be rejected, never trusted
            other = opaque(cid, "other-item", prefix="it_")
            inspections = [r.model_copy(update={"subject_id": other}) for r in inspections]

        # Customer statements may be inaccurate (especially in conflicting_messages).
        claimed_days = age if scenario != "conflicting_messages" else age + rng.randint(30, 120)
        msg = rng.choice(OPENERS) + TEMPLATES[scenario][template_idx].format(item=rng.choice(ITEMS[category])) \
            + rng.choice(CLOSERS)
        case = Case(
            case_id=cid, domain=self.name, split=split, scenario=scenario, template_id=f"{scenario}#{template_idx}",
            generator_version=GENERATOR_VERSION, subject_id=item_id, request=msg,
            initial_facts={"category": category, "request_date": request.isoformat(),
                           "customer_claimed_days_since_purchase": claimed_days},
            hidden_evidence={
                "get_order": FixtureSource(available=avail["get_order"], records=[order]),
                "get_policy": FixtureSource(available=avail["get_policy"], records=policies),
                "get_inspection": FixtureSource(available=avail["get_inspection"], records=inspections),
            },
            oracle_action=self.fallback,
        )
        return case.model_copy(update={"oracle_action": self.oracle(case)})


# ------------------------------------------------------------------ synthetic data tables
CATEGORIES = ("electronics", "apparel", "home")
# (version, effective_from, effective_to, window days by category)
POLICY_VERSIONS = [
    ("RP-2025", "2025-01-01", "2026-02-28", {"electronics": 30, "apparel": 45, "home": 30}),
    ("RP-2026", "2026-03-01", None, {"electronics": 21, "apparel": 30, "home": 28}),
]
SCENARIOS = {  # scenario: cases per split
    "clean_approve": 20, "not_delivered": 10, "outside_window": 10, "no_damage": 10,
    "missing_evidence": 20, "conflicting_messages": 20, "policy_boundary": 15, "unavailable_tool": 15,
}
TEMPLATES = {
    "clean_approve": ["My {item} arrived broken. Can I return it?",
                      "The {item} I got is damaged out of the box, I'd like a refund.",
                      "Received the {item} with a cracked part. Requesting a return.",
                      "Unfortunately the {item} came damaged. What are my options?"],
    "not_delivered": ["I want to return the {item}, it's damaged.",
                      "Please refund my {item}, it is defective.",
                      "Return request: the {item} doesn't work.",
                      "I need to send back the {item}, it has a defect."],
    "outside_window": ["I bought the {item} recently and it's broken now.",
                       "The {item} just stopped working, I'd like to return it.",
                       "My {item} is damaged. I purchased it not long ago.",
                       "Can I return the {item}? It broke and it's fairly new."],
    "no_damage": ["The {item} is badly damaged, I want my money back.",
                  "My {item} arrived smashed, please refund.",
                  "The {item} is defective, I'm returning it.",
                  "Damaged {item}, need a return label."],
    "missing_evidence": ["I think the {item} is damaged, can I return it?",
                         "Something is wrong with my {item}. Return please.",
                         "My {item} seems faulty. How do I return it?",
                         "Not sure what happened but the {item} looks damaged."],
    "conflicting_messages": ["My {item} never arrived and also it's broken??",
                             "I got the {item} months ago, it's damaged, refund me.",
                             "The courier lost my {item}, but the box I got was crushed.",
                             "I never ordered this {item} but it came damaged."],
    "policy_boundary": ["I bought the {item} about a month ago and it arrived damaged.",
                        "The {item} was damaged on arrival a few weeks back.",
                        "Damaged {item} from my order a while ago. Still returnable?",
                        "Is it too late to return my damaged {item}?"],
    "unavailable_tool": ["Return request for a damaged {item}.",
                         "Please process a return, the {item} is damaged.",
                         "My {item} is broken, I want to return it.",
                         "The {item} came damaged, I'd like a refund."],
}
OPENERS = ["", "Hi, ", "Hello, ", "Hey there. ", "Good morning. "]
CLOSERS = ["", " Thanks.", " Thank you!", " Please help.", " Order details should be on file."]
ITEMS = {"electronics": ["headphones", "tablet", "speaker"], "apparel": ["jacket", "pair of boots", "sweater"],
         "home": ["lamp", "kettle", "chair"]}


def _window(version_idx: int, category: str) -> int:
    return POLICY_VERSIONS[version_idx][3][category]


def _version_for(purchase: date) -> int:
    return 0 if purchase <= date(2026, 2, 28) else 1
