import { useState } from "react";
import { humanize, labelColor, money, pct, payloadLines, sourceName } from "../format";
import type { DomainData, GraphNode, Run, ShowCase } from "../types";

interface Props {
  domain: DomainData;
  caseData: ShowCase;
  run: Run;
  position: number; // 0..E-1 = after that many checks, E = final decision
}

interface Detail {
  title: string;
  lines: [string, string][];
}

type Row =
  | { type: "record"; source: string; cost: number; order: number; ev: GraphNode; relToSubject: string; relToDecision: string }
  | { type: "ghost"; source: string; cost: number; text: string; problem: boolean };

const W = 900;
const COL = {
  case: { x: 8, w: 192 },
  subject: { x: 236, w: 120 },
  record: { x: 396, w: 222 },
  decision: { x: 738, w: 156 },
};
const ROW_H = 66;
const GAP = 12;
const TOP = 40;

function wrap(text: string, max: number, lines: number): string[] {
  const words = text.split(/\s+/);
  const out: string[] = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > max) {
      out.push(cur.trim());
      cur = w;
      if (out.length === lines) break;
    } else cur = `${cur} ${w}`;
  }
  if (out.length < lines && cur.trim()) out.push(cur.trim());
  if (out.length === lines && words.join(" ").length > out.join(" ").length) {
    out[lines - 1] = out[lines - 1].replace(/.{0,2}$/, "") + "…";
  }
  return out;
}

function edgePath(x1: number, y1: number, x2: number, y2: number) {
  const dx = (x2 - x1) / 2;
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

const REL: Record<string, { cls: string; text: string }> = {
  supports: { cls: "rel-supports", text: "✓ supports" },
  contradicts: { cls: "rel-contradicts", text: "✗ contradicts" },
  informs: { cls: "rel-informs", text: "informs" },
};

export function DecisionGraph({ domain, caseData, run, position }: Props) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const E = run.evolution.length;
  const isFinal = position >= E;
  const stage = run.evolution[Math.min(position, E - 1)];
  const revealed = Math.min(position, E - 1);
  const fetched = run.evolution.slice(1).map((s) => ({ src: s.after as string, status: s.status as string }));
  const decisionId = run.graph.nodes.find((n) => n.kind === "Decision")?.id ?? "";
  const subject = run.graph.nodes.find((n) => n.kind === domain.subject_kind);
  const linkRel = (src: string, dst: string) => run.graph.links.find((l) => l.src === src && l.dst === dst)?.rel;

  const rows: Row[] = [];
  for (const s of domain.sources) {
    const idx = fetched.findIndex((f) => f.src === s.id);
    const shown = idx >= 0 && idx < revealed;
    if (shown && fetched[idx].status === "ok") {
      for (const ev of run.graph.nodes.filter((n) => n.kind === "Evidence" && n.data.source_id === s.id)) {
        const recId = "src_" + ev.id.slice(3);
        rows.push({
          type: "record", source: s.id, cost: s.cost, order: idx + 1, ev,
          relToSubject: (subject && linkRel(recId, subject.id)) || "unlinked",
          relToDecision: linkRel(ev.id, decisionId) || "informs",
        });
      }
    } else if (shown) {
      const text = fetched[idx].status === "unavailable" ? "Unavailable: system down" : "Rejected: another case's record";
      rows.push({ type: "ghost", source: s.id, cost: s.cost, text, problem: true });
    } else {
      const never = idx < 0;
      rows.push({
        type: "ghost", source: s.id, cost: s.cost, problem: false,
        text: isFinal && never ? `Not checked · saved ${money(s.cost)}` : "Not checked yet",
      });
    }
  }

  const n = rows.length;
  const block = n * (ROW_H + GAP) - GAP;
  const H = Math.max(TOP + block + 16, 300);
  const cy = TOP + block / 2;
  const rowY = (i: number) => TOP + i * (ROW_H + GAP);
  const caseH = 132;
  const subjH = 58;
  const decH = 116;

  const requestLines = wrap(`“${caseData.request}”`, 28, 5);
  const factLines = Object.entries(caseData.facts).slice(0, 2);
  const leading = isFinal ? run.decision : stage.leading;
  const leadingP = stage.probabilities[leading] ?? 0;

  const focus = (d: Detail) => ({
    tabIndex: 0,
    onMouseEnter: () => setDetail(d),
    onFocus: () => setDetail(d),
    onClick: () => setDetail(d),
  });

  return (
    <figure className="graph-figure">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" className="graph"
           aria-label={`Decision graph for ${caseData.scenario_label}: ${rows.filter((r) => r.type === "record").length} records checked`}>
        {[["Request", COL.case], [domain.subject_kind, COL.subject], ["Evidence", COL.record],
          [isFinal ? "Decision" : "Probable outcome", COL.decision]].map(([t, c]) => (
          <text key={t as string} x={(c as { x: number }).x} y={18} className="col-head">{(t as string).toUpperCase()}</text>
        ))}

        {/* edges first, so nodes sit on top */}
        <path d={edgePath(COL.case.x + COL.case.w, cy, COL.subject.x, cy)} className="edge rel-structure" />
        {rows.map((r, i) => {
          const y = rowY(i) + ROW_H / 2;
          const toRecord = edgePath(COL.subject.x + COL.subject.w, cy, COL.record.x, y);
          const toDecision = edgePath(COL.record.x + COL.record.w, y, COL.decision.x, cy);
          if (r.type === "ghost") return <path key={`e${i}`} d={toRecord} className="edge ghost" />;
          const rel = isFinal ? REL[r.relToDecision] ?? REL.informs : { cls: "rel-pending", text: "" };
          const mx = (COL.record.x + COL.record.w + COL.decision.x) / 2;
          const my = (y + cy) / 2;
          return (
            <g key={`e${i}-${r.ev.id}`} className="fade-in">
              <path d={toRecord} className="edge rel-structure" />
              <path d={toDecision} className={`edge ${rel.cls}`} />
              {rel.text && (
                <g transform={`translate(${mx}, ${my})`}>
                  <rect x={-rel.text.length * 3.3 - 6} y={-9} width={rel.text.length * 6.6 + 12} height={18} rx={9}
                        className="edge-label-bg" />
                  <text textAnchor="middle" y={4} className="edge-label">{rel.text}</text>
                </g>
              )}
            </g>
          );
        })}

        {/* request */}
        <g transform={`translate(${COL.case.x}, ${cy - caseH / 2})`} className="node"
           {...focus({ title: "Request (what the decision-maker reads first)", lines: [
             ["Message", caseData.request], ...Object.entries(caseData.facts).map(([k, v]) => [humanize(k), String(v)] as [string, string]),
           ] })}>
          <rect width={COL.case.w} height={caseH} rx={10} className="node-box" />
          {requestLines.map((l, i) => <text key={i} x={12} y={22 + i * 16} className="node-text">{l}</text>)}
          {factLines.map(([k, v], i) => (
            <text key={k} x={12} y={caseH - 26 + i * 14} className="node-meta">{humanize(k)}: {String(v)}</text>
          ))}
        </g>

        {/* subject */}
        <g transform={`translate(${COL.subject.x}, ${cy - subjH / 2})`} className="node"
           {...focus({ title: domain.subject_kind, lines: [["ID", subject?.id ?? "n/a"], ["Scenario (hidden from the AI)", caseData.scenario_label]] })}>
          <rect width={COL.subject.w} height={subjH} rx={10} className="node-box" />
          <text x={12} y={24} className="node-title">{domain.subject_kind}</text>
          <text x={12} y={42} className="node-meta mono">{(subject?.id ?? "").slice(0, 14)}</text>
        </g>

        {/* evidence rows */}
        {rows.map((r, i) => {
          const y = rowY(i);
          if (r.type === "ghost") {
            return (
              <g key={`g${i}-${r.source}-${r.text}`} transform={`translate(${COL.record.x}, ${y})`}
                 className={`node ghost-node ${r.problem ? "problem" : ""}`}
                 {...focus({ title: sourceName(r.source), lines: [["Status", r.text],
                   ["Cost per check", money(r.cost)], ["What it holds", domain.sources.find((s) => s.id === r.source)?.description ?? ""]] })}>
                <rect width={COL.record.w} height={ROW_H} rx={10} className="node-box" />
                <text x={14} y={26} className="node-title">{r.problem ? "⚠ " : ""}{sourceName(r.source)}</text>
                <text x={14} y={46} className="node-meta">{r.text}</text>
              </g>
            );
          }
          const payload = (r.ev.data.payload ?? {}) as Record<string, unknown>;
          const lines = payloadLines(payload, 2);
          return (
            <g key={`r${i}-${r.ev.id}`} transform={`translate(${COL.record.x}, ${y})`}>
            <g className="node fade-in"
               {...focus({ title: `${sourceName(r.source)} record (check #${r.order}, ${money(r.cost)})`,
                 lines: [...payloadLines(payload, 12), ["Linked to subject as", humanize(r.relToSubject)],
                   ...(isFinal ? [["Relation to decision", humanize(r.relToDecision)] as [string, string]] : [])] })}>
              <rect width={COL.record.w} height={ROW_H} rx={10} className="node-box" />
              <circle cx={18} cy={20} r={9} className="order-badge" />
              <text x={18} y={24} textAnchor="middle" className="order-text">{r.order}</text>
              <text x={34} y={24} className="node-title">{sourceName(r.source)}</text>
              <text x={COL.record.w - 12} y={24} textAnchor="end" className="node-meta">{money(r.cost)}</text>
              {lines.map(([k, v], j) => (
                <text key={k} x={14} y={42 + j * 14} className="node-meta">{k}: <tspan className="node-value">{v}</tspan></text>
              ))}
            </g>
            </g>
          );
        })}

        {/* outcome */}
        <g transform={`translate(${COL.decision.x}, ${cy - decH / 2})`}
           className={`node decision ${isFinal ? "final" : "pending"}`}
           {...focus({ title: isFinal ? "Final decision" : "Probable outcome so far", lines: [
             ...Object.entries(stage.probabilities).map(([k, v]) => [humanize(k), pct(v)] as [string, string]),
             ...(isFinal ? [["Answer key", humanize(caseData.answer)] as [string, string]] : []),
           ] })}>
          <rect width={COL.decision.w} height={decH} rx={10} className="node-box" />
          <rect x={0} y={0} width={6} height={decH} rx={3} fill={labelColor(domain, leading)} />
          <text x={18} y={30} className="decision-label">{humanize(leading)}</text>
          <text x={18} y={50} className="node-meta">
            {isFinal ? `confidence ${pct(leadingP)}` : `${pct(leadingP)} likely · ${revealed} check${revealed === 1 ? "" : "s"}`}
          </text>
          {isFinal && (
            <text x={18} y={decH - 22} className={`verdict ${run.correct ? "ok" : "bad"}`}>
              {run.correct ? "✓ Matches answer key" : `✗ Answer: ${humanize(caseData.answer)}`}
            </text>
          )}
          {!isFinal && <text x={18} y={decH - 22} className="node-meta">deciding…</text>}
        </g>
      </svg>
      <figcaption className="graph-detail" aria-live="polite">
        {detail ? (
          <>
            <strong>{detail.title}</strong>
            <dl>
              {detail.lines.map(([k, v]) => (
                <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
              ))}
            </dl>
          </>
        ) : (
          <span className="muted">Hover or tab to any node to see what it contains. Dashed nodes were not checked.</span>
        )}
      </figcaption>
    </figure>
  );
}
