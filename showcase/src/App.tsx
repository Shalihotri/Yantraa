import { useEffect, useState, type ReactNode } from "react";
import { live, REPO } from "./data";
import { Demo } from "./sections/Demo";
import { Findings } from "./sections/Findings";
import { Fit } from "./sections/Fit";
import { Hero } from "./sections/Hero";
import { HowItWorks, Question } from "./sections/Method";
import { Scale } from "./sections/Scale";
import { Start } from "./sections/Start";

const SECTIONS = [
  { id: "question", n: "01", short: "The question" },
  { id: "demo", n: "02", short: "Watch it decide" },
  { id: "findings", n: "03", short: "What we found" },
  { id: "how", n: "04", short: "How it works" },
  { id: "scale", n: "05", short: "At scale" },
  { id: "fit", n: "06", short: "Your use case" },
  { id: "start", n: "07", short: "Get started" },
];

function Section({ id, title, kicker, children, wide = false }: {
  id: string; title: string; kicker?: ReactNode; children: ReactNode; wide?: boolean;
}) {
  const s = SECTIONS.find((x) => x.id === id)!;
  return (
    <section id={id} className={`section reveal ${wide ? "wide" : ""}`} aria-labelledby={`${id}-h`}>
      <div className="section-head">
        <span className="section-n">{s.n}</span>
        <h2 id={`${id}-h`}>{title}</h2>
        {kicker && <p className="kicker">{kicker}</p>}
      </div>
      {children}
    </section>
  );
}

export function App() {
  const [active, setActive] = useState("");
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>(".reveal");
    const reveal = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && e.target.classList.add("in")),
      { rootMargin: "0px 0px -10% 0px" });
    els.forEach((el) => reveal.observe(el));
    const spy = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && setActive(e.target.id)),
      { rootMargin: "-45% 0px -50% 0px" });
    SECTIONS.forEach((s) => { const el = document.getElementById(s.id); if (el) spy.observe(el); });
    // Content renders client-side, after the browser's own jump to #anchor, so honour shared deep links here.
    const target = window.location.hash && document.getElementById(window.location.hash.slice(1));
    if (target) {
      els.forEach((el) => el.classList.add("in")); // landing mid-page: show everything, no fade
      requestAnimationFrame(() => target.scrollIntoView({ behavior: "auto" }));
    }
    const failsafe = window.setTimeout(() => els.forEach((el) => el.classList.add("in")), 4000); // never leave content hidden
    return () => { reveal.disconnect(); spy.disconnect(); window.clearTimeout(failsafe); };
  }, []);

  return (
    <>
      <a className="skip" href="#question">Skip to content</a>
      <nav className="nav" aria-label="Site">
        <a className="wordmark" href="#top"><span className="mark" aria-hidden>✳</span>Yantraa Evidence</a>
        <div className="nav-links">
          <a href="#demo">Demo</a><a href="#findings">Findings</a><a href="#how">Method</a><a href="#fit">Use cases</a>
          <a className="nav-cta" href={REPO} target="_blank" rel="noreferrer">GitHub ↗</a>
        </div>
      </nav>

      <Hero />

      <div className="layout">
        <aside className="toc" aria-label="Contents">
          <ol>
            {SECTIONS.map((s) => (
              <li key={s.id} className={active === s.id ? "on" : ""}><a href={`#${s.id}`}><span>{s.n}</span>{s.short}</a></li>
            ))}
          </ol>
        </aside>

        <main>
          <Section id="question" title="The question nobody measures">
            <Question />
          </Section>

          <Section id="demo" wide title="Watch a real model decide"
                   kicker={<>Ten return requests, five strategies, one model: {live.model} via the {live.api}. Every
                     probability below is the model's own. Pick a request, pick a strategy, and step through it.</>}>
            <Demo />
            <p className="fig-caption"><span className="fig-n">Figure 2.</span> The evidence graph builds up as the model checks
              records. Once it decides, each record is linked to the decision as supporting or contradicting it.</p>
          </Section>

          <Section id="findings" title="What we found">
            <Findings />
          </Section>

          <Section id="how" title="How it works" kicker="One loop, five strategies, and a few rules that keep the comparison fair.">
            <HowItWorks />
          </Section>

          <Section id="scale" title="Compare strategies before spending a cent"
                   kicker="The same comparison runs offline on hundreds of synthetic requests, in seconds, for any domain you define.">
            <Scale />
          </Section>

          <Section id="fit" title="Built for decisions like yours"
                   kicker="If a request comes in, records could be checked at a cost, and mistakes have different prices, it fits. Each domain is one Python class.">
            <Fit />
          </Section>

          <Section id="start" title="Get started">
            <Start />
          </Section>
        </main>
      </div>

      <footer className="footer">
        <div>
          <span className="wordmark small"><span className="mark" aria-hidden>✳</span>Yantraa Evidence</span>
          <p>Open source under Apache-2.0. Every request on this page is synthetic. Live results: {live.n_cases} requests,
            {" "}{live.model}, {live.date}. Penalties are illustrative.</p>
        </div>
        <div className="footer-links">
          <a href={REPO} target="_blank" rel="noreferrer">GitHub</a>
          <a href="https://pypi.org/project/yantraa-evidence/" target="_blank" rel="noreferrer">PyPI</a>
          <a href={`${REPO}/blob/main/docs/use-cases.md`} target="_blank" rel="noreferrer">Use cases</a>
        </div>
      </footer>
    </>
  );
}
