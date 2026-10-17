import { useState } from "react";
import { evidenceFor, judgements, topLabel } from "../data";
import { humanize, labelColor, money, pct, payloadLines, sourceName } from "../format";
import type { DomainData, GraphNode, LiveCase, LiveRun } from "../types";

interface Props {
  domain: DomainData;
  caseData: LiveCase;
  run: LiveRun;
  position: number; // number of timeline events shown; === timeline.length means decided
}

type Row =
  | { type: "record"; source: string; cost: number; order: number; ev: GraphNode; rel: string }
  | { type: "ghost"; source: string; cost: number; text: string; problem: boolean };

const W = 920;
const COL = { req: { x: 0, w: 214 }, subj: { x: 254, w: 112 }, rec: { x: 410, w: 230 }, dec: { x: 756, w: 164 } };
const ROW_H = 68;
const GAP = 14;
const TOP = 34;

function wrap(text: string, max: number, lines: number): string[] {
  const words = text.split(/\s+/);
  const out: string[] = [];
  let cur = "";
  for (const w of words) {
    if (`${cur} ${w}`.trim().length > max && cur) {
      out.push(cur.trim());
      cur = w;
    } else cur = `${cur} ${w}`;
  }
  if (cur.trim()) out.push(cur.trim());
  if (out.length > lines) {
    out.length = lines;
    out[lines - 1] = out[lines - 1].replace(/\s*\S*$/, "") + "…";
  }
  return out;
}

const curve = (x1: number, y1: number, x2: number, y2: number) => {
  const dx = (x2 - x1) / 2;
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
};

const REL: Record<string, { cls: string; text: string }> = {
  supports: { cls: "rel-supports", text: "✓ supports" },
  contradicts: { cls: "rel-contradicts", text: "✗ contradicts" },
  informs: { cls: "rel-informs", text: "informs" },
};

export function Graph({ domain, caseData, run, position }: Props) {
  const [detail, setDetail] = useState<{ title: string; lines: [string, string][] } | null>(null);
  const T = run.timeline.length;
  const decided = position >= T;
  const shown = run.timeline.slice(0, position);
  const checks = shown.flatMap((e, i) => (e.type === "check" ? [{ ...e, order: i }] : []));
  const allChecks = run.timeline.filter((e) => e.type === "check").map((e) => (e.type === "check" ? e.source : ""));
  const last = judgements(run, position).at(-1)?.event;
  const decisionId = run.graph.nodes.find((n) => n.kind === "Decision")?.id ?? "";
  const subject = run.graph.nodes.find((n) => n.kind === domain.subject_kind);
  const rel = (src: string) => run.graph.links.find((l) => l.src === src && l.dst === decisionId)?.rel ?? "informs";

  const rows: Row[] = [];
  for (const s of domain.sources) {
    const k = checks.findIndex((c) => c.source === s.id);
    if (k >= 0 && checks[k].status === "ok") {
      for (const ev of evidenceFor(run, s.id)) rows.push({ type: "record", source: s.id, cost: s.cost, order: k + 1, ev, rel: rel(ev.id) });
    } else if (k >= 0) {
      rows.push({ type: "ghost", source: s.id, cost: s.cost, problem: true,
        text: checks[k].status === "unavailable" ? "Unavailable: system down" : "Rejected: another case's record" });
    } else {
      const never = !allChecks.includes(s.id);
      rows.push({ type: "ghost", source: s.id, cost: s.cost, problem: false,
        text: decided && never ? `Never checked · saved ${money(s.cost)}` : "Not checked yet" });
    }
  }

  const n = rows.length;
  const block = n * (ROW_H + GAP) - GAP;
  const H = TOP + block + 8;
  const cy = TOP + block / 2;
  const y = (i: number) => TOP + i * (ROW_H + GAP);
  const reqLines = wrap(`“${caseData.request}”`, 27, 5);
  const reqH = 34 + reqLines.length * 19 + 30;
  const decH = 120;
  const [lean, leanP] = last ? topLabel(last.probabilities) : ["", 0];
  const outcome = decided ? run.decision : lean;

  const focus = (title: string, lines: [string, string][]) => ({
    tabIndex: 0, role: "button", "aria-label": title,
    onMouseEnter: () => setDetail({ title, lines }), onFocus: () => setDetail({ title, lines }),
    onClick: () => setDetail({ title, lines }),
  });

  return (
    <figure className="graph-figure">
      <svg viewBox={`-2 0 ${W + 4} ${H}`} className="graph" role="img"
           aria-label={`Decision graph: ${checks.length} of ${domain.sources.length} sources checked${decided ? `, decided ${run.decision}` : ""}`}>
        {(["Request", domain.subject_kind, "Evidence", decided ? "Decision" : "Leaning"] as const).map((t, i) => (
          <text key={i} x={[COL.req, COL.subj, COL.rec, COL.dec][i].x} y={12} className="col-head">{t.toUpperCase()}</text>
        ))}

        <path d={curve(COL.req.x + COL.req.w, cy, COL.subj.x, cy)} className="edge structure" />
        {rows.map((r, i) => {
          const ry = y(i) + ROW_H / 2;
          if (r.type === "ghost") return <path key={`e${i}`} d={curve(COL.subj.x + COL.subj.w, cy, COL.rec.x, ry)} className="edge ghost" />;
          const style = decided ? REL[r.rel] ?? REL.informs : { cls: "pending", text: "" };
          const mx = (COL.rec.x + COL.rec.w + COL.dec.x) / 2;
          return (
            <g key={`e${i}-${r.ev.id}`} className="appear">
              <path d={curve(COL.subj.x + COL.subj.w, cy, COL.rec.x, ry)} className="edge structure" />
              <path d={curve(COL.rec.x + COL.rec.w, ry, COL.dec.x, cy)} className={`edge ${style.cls}`} />
              {style.text && (
                <g transform={`translate(${mx}, ${(ry + cy) / 2})`}>
                  <rect x={-style.text.length * 3.4 - 8} y={-10} width={style.text.length * 6.8 + 16} height={20} rx={10} className="edge-pill" />
                  <text textAnchor="middle" y={4} className="edge-text">{style.text}</text>
                </g>
              )}
            </g>
          );
        })}

        <g transform={`translate(${COL.req.x}, ${cy - reqH / 2})`}>
          <g className="node" {...focus("The request", [["Message", caseData.request],
            ...Object.entries(caseData.facts).map(([k, v]) => [humanize(k), String(v)] as [string, string])])}>
            <rect width={COL.req.w} height={reqH} rx={12} className="box" />
            {reqLines.map((l, i) => <text key={i} x={16} y={30 + i * 19} className="quote">{l}</text>)}
            <text x={16} y={reqH - 16} className="meta">Customer says · may be wrong</text>
          </g>
        </g>

        <g transform={`translate(${COL.subj.x}, ${cy - 30})`}>
          <g className="node" {...focus(domain.subject_kind, [["ID", subject?.id ?? "n/a"], ["Situation (hidden from the model)", caseData.scenario_label]])}>
            <rect width={COL.subj.w} height={60} rx={12} className="box" />
            <text x={16} y={26} className="title">{domain.subject_kind}</text>
            <text x={16} y={44} className="meta mono">{(subject?.id ?? "").slice(0, 13)}</text>
          </g>
        </g>

        {rows.map((r, i) => (
          <g key={`n${i}-${r.type === "record" ? r.ev.id : r.text}`} transform={`translate(${COL.rec.x}, ${y(i)})`}>
            {r.type === "ghost" ? (
              <g className={`node ghost ${r.problem ? "problem" : ""}`} {...focus(sourceName(r.source), [["Status", r.text],
                ["Cost per check", money(r.cost)], ["Holds", domain.sources.find((s) => s.id === r.source)?.description ?? ""]])}>
                <rect width={COL.rec.w} height={ROW_H} rx={12} className="box" />
                <text x={16} y={28} className="title">{r.problem ? "⚠ " : ""}{sourceName(r.source)}</text>
                <text x={16} y={48} className="meta">{r.text}</text>
              </g>
            ) : (
              <g className="node appear" {...focus(`${sourceName(r.source)} record · check #${r.order} · ${money(r.cost)}`,
                payloadLines((r.ev.data.payload ?? {}) as Record<string, unknown>, 12))}>
                <rect width={COL.rec.w} height={ROW_H} rx={12} className="box solid" />
                <circle cx={22} cy={22} r={10} className="badge" />
                <text x={22} y={26} textAnchor="middle" className="badge-text">{r.order}</text>
                <text x={40} y={27} className="title">{sourceName(r.source)}</text>
                <text x={COL.rec.w - 14} y={27} textAnchor="end" className="meta">{money(r.cost)}</text>
                {payloadLines((r.ev.data.payload ?? {}) as Record<string, unknown>, 2).map(([k, v], j) => (
                  <text key={k} x={16} y={46 + j * 14} className="meta">{k}: <tspan className="value">{v}</tspan></text>
                ))}
              </g>
            )}
          </g>
        ))}

        <g transform={`translate(${COL.dec.x}, ${cy - decH / 2})`}>
          <g className={`node outcome ${decided ? "decided" : "pending"}`}
             {...focus(decided ? "Decision" : "What the model leans towards", [
               ...Object.entries((last?.probabilities ?? {})).map(([k, v]) => [humanize(k), pct(v)] as [string, string]),
               ["Answer key", decided ? humanize(caseData.answer) : "hidden until the end"]])}>
            <rect width={COL.dec.w} height={decH} rx={12} className="box" />
            {outcome && <rect x={0} y={14} width={4} height={decH - 28} rx={2} fill={labelColor(domain, outcome)} />}
            <text x={18} y={34} className="outcome-label">{outcome ? humanize(outcome) : "…"}</text>
            <text x={18} y={54} className="meta">{last ? `${pct(leanP)} sure` : "no judgement yet"}</text>
            {decided ? (
              <text x={18} y={decH - 20} className={`verdict ${run.correct ? "ok" : "bad"}`}>
                {run.correct ? "✓ Right" : `✗ Answer: ${humanize(caseData.answer)}`}
              </text>
            ) : <text x={18} y={decH - 20} className="meta">thinking…</text>}
          </g>
        </g>
      </svg>
      <figcaption className="graph-detail" aria-live="polite">
        {detail ? (
          <><strong>{detail.title}</strong>
            <dl>{detail.lines.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></>
        ) : <span>Hover or tab to any node to see what it holds. Dashed sources haven't been checked.</span>}
      </figcaption>
    </figure>
  );
}
