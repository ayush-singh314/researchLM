import { useEffect, useState } from "react";
import "./landing.css";

type Props = {
  onSignIn: () => void;
  onStart: () => void;
};

export function LandingPage({ onSignIn, onStart }: Props) {
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    const onScroll = () => setCompact(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="landing">
      <header className={`landing-nav ${compact ? "is-compact" : ""}`}>
        <a className="landing-wordmark" href="#top">
          <span className="landing-mark" aria-hidden="true" />
          ResearchLM
        </a>
        <nav className="landing-nav-links" aria-label="Page">
          <a href="#product">Product</a>
          <a href="#how-it-works">How it works</a>
          <a href="#use-cases">Use cases</a>
          <a href="#features">Features</a>
        </nav>
        <div className="landing-nav-cta">
          <button type="button" className="landing-btn ghost" onClick={onSignIn}>
            Sign In
          </button>
          <button type="button" className="landing-btn primary" onClick={onStart}>
            Start Researching
          </button>
        </div>
      </header>

      <main id="top">
        <section className="landing-hero" id="product">
          <p className="landing-eyebrow">The grounded learning workspace</p>
          <h1>Turn research into knowledge you actually understand.</h1>
          <p className="landing-lead">
            ResearchLM combines grounded AI research with intelligent note-taking to help you
            learn from trusted sources, understand complex concepts, and turn scattered
            information into knowledge you can actually internalize.
          </p>
          <div className="landing-hero-cta">
            <button type="button" className="landing-btn primary lg" onClick={onStart}>
              Start Researching →
            </button>
            <a className="landing-btn ghost lg" href="#how-it-works">
              See how it works
            </a>
          </div>
          <p className="landing-trust">Grounded in your sources · Built for deep learning</p>
          <ProductMock />
        </section>

        <section className="landing-section landing-problem">
          <h2>Information is everywhere. Understanding isn’t.</h2>
          <p className="landing-lead">
            We search dozens of pages, open endless tabs, ask AI the same question multiple
            times, and take notes that eventually become forgotten documents.
          </p>
          <div className="chaos-row" aria-label="Fragmented workflow">
            {["Search", "Read", "Copy", "Chat", "Bookmark", "Note", "Forget"].map((label, i) => (
              <div key={label} className={`chaos-chip chip-${i}`}>
                <span>{label}</span>
                {i < 6 && <em aria-hidden="true">→</em>}
              </div>
            ))}
          </div>
          <div className="chaos-cards">
            <article className="chaos-card"><small>Tabs</small>12 unread papers</article>
            <article className="chaos-card"><small>PDF</small>attention_is_all_you_need.pdf</article>
            <article className="chaos-card"><small>AI chat</small>New conversation</article>
            <article className="chaos-card"><small>Docs</small>Retrieval API</article>
            <article className="chaos-card"><small>Notes</small>Untitled</article>
            <article className="chaos-card"><small>Saved</small>27 bookmarks</article>
          </div>
        </section>

        <section className="landing-section landing-solution">
          <h2>ResearchLM brings the entire learning loop into one place.</h2>
          <ol className="loop">
            <li><strong>Sources</strong><span>Papers, docs, and files you trust</span></li>
            <li><strong>Grounded research</strong><span>Ask against what you uploaded</span></li>
            <li><strong>Understanding</strong><span>Explanations with citations</span></li>
            <li><strong>Notes</strong><span>Capture the insight while it’s fresh</span></li>
            <li><strong>Personal knowledge</strong><span>A base you can return to</span></li>
          </ol>
        </section>

        <section className="landing-section" id="how-it-works">
          <h2>From source to understanding in four steps.</h2>
          <div className="steps">
            <article className="step">
              <span className="step-num">01</span>
              <h3>Bring your sources</h3>
              <p>Start with the documents, research papers, documentation, or knowledge you trust.</p>
              <div className="mini-mock">
                <div className="mini-chip">cog.pdf</div>
                <div className="mini-chip">Attention paper</div>
                <div className="mini-chip">docs.site</div>
              </div>
            </article>
            <article className="step">
              <span className="step-num">02</span>
              <h3>Ask anything</h3>
              <p>Ask questions naturally and explore the concepts hidden inside your sources.</p>
              <div className="mini-mock ask">
                How does RAG reduce hallucinations?
              </div>
            </article>
            <article className="step">
              <span className="step-num">03</span>
              <h3>Understand with context</h3>
              <p>ResearchLM retrieves relevant information and generates grounded explanations with source context.</p>
              <div className="mini-mock cite">
                Retrieval happens before generation <i>[01]</i>
              </div>
            </article>
            <article className="step">
              <span className="step-num">04</span>
              <h3>Capture what matters</h3>
              <p>Turn insights into structured notes and build a knowledge base you can return to.</p>
              <div className="mini-mock note">RAG separates retrieval from generation…</div>
            </article>
          </div>
        </section>

        <section className="landing-section" id="features">
          <h2>Four capabilities. One learning loop.</h2>
          <div className="features">
            <article className="feature">
              <h3>Answers anchored in your knowledge.</h3>
              <p>ResearchLM retrieves from trusted sources before it writes—so answers stay grounded, not generic.</p>
              <div className="feature-visual">
                <p>RAG reduces hallucination by fetching evidence first. <i>[01]</i></p>
                <div className="src-row"><span>01</span> RAG Research Paper</div>
              </div>
            </article>
            <article className="feature">
              <h3>Go beyond answers. Understand the concept.</h3>
              <p>Explore explanation, why it works, an example, a related idea, and a deeper dive—active learning, not a one-shot reply.</p>
              <div className="feature-visual pills">
                <span>Explanation</span><span>Why?</span><span>Example</span><span>Related</span><span>Deeper dive</span>
              </div>
            </article>
            <article className="feature">
              <h3>Capture understanding while you research.</h3>
              <p>Move from source to insight to note without leaving the thread.</p>
              <div className="feature-visual flow">
                <span>Source</span><em>→</em><span>Insight</span><em>→</em><span>Note</span>
              </div>
            </article>
            <article className="feature">
              <h3>Build a knowledge base, not a pile of notes.</h3>
              <p>Related concepts stay connected so you can see the system, not isolated facts.</p>
              <div className="feature-visual nodes">
                {["RAG", "Embeddings", "Vector DB", "Retrieval", "Context", "LLM"].map((n, i) => (
                  <span key={n} className={i === 0 ? "on" : ""}>{n}</span>
                ))}
              </div>
            </article>
            <article className="feature wide">
              <h3>Always know where your understanding came from.</h3>
              <p>Citations sit on the claim. Hover a marker and the source lights up—trust you can inspect.</p>
              <div className="feature-visual cites">
                <p>Attention replaces recurrence for sequence modeling. <i>[02]</i></p>
                <div className="src-row lit"><span>02</span> Attention Is All You Need</div>
              </div>
            </article>
          </div>
        </section>

        <section className="landing-section landing-diff">
          <h2>Not another chatbot. Not another notebook.</h2>
          <div className="diff-grid">
            <article>
              <h3>Search engines</h3>
              <p className="diff-verb">Find information.</p>
              <p>You still have to search, filter, read, understand, organize, and remember.</p>
            </article>
            <article>
              <h3>AI chatbots</h3>
              <p className="diff-verb">Generate answers.</p>
              <p>Replies can drift from trusted sources and from your own notes.</p>
            </article>
            <article>
              <h3>Note apps</h3>
              <p className="diff-verb">Store information.</p>
              <p>They keep text. They don’t help you understand it.</p>
            </article>
            <article className="diff-hero">
              <h3>ResearchLM</h3>
              <p className="diff-verb">Connects the entire loop.</p>
              <p>Research → Understand → Capture → Connect → Internalize</p>
            </article>
          </div>
        </section>

        <section className="landing-section" id="use-cases">
          <h2>Built for people who need to understand, not skim.</h2>
          <div className="use-grid">
            <UseCard title="Students" copy="Understand difficult subjects and turn study material into structured knowledge." mock="What is attention?" />
            <UseCard title="Researchers" copy="Explore papers and source material without losing context." mock="Compare two methods" />
            <UseCard title="Developers" copy="Learn complex technologies and documentation with grounded explanations." mock="How does pooling work?" />
            <UseCard title="Knowledge workers" copy="Research topics quickly and retain the insights that matter." mock="Key risks in the brief" />
            <UseCard title="Lifelong learners" copy="Turn curiosity into structured, reusable knowledge." mock="Explain it simply" />
          </div>
        </section>

        <section className="landing-section landing-deep">
          <h2>Don’t just collect information. Make it yours.</h2>
          <p className="landing-lead">
            ResearchLM is designed around the complete learning loop—from discovering
            information to understanding it, writing it down, connecting it with what you
            already know, and returning to it later.
          </p>
          <ol className="deep-flow">
            {["Discover", "Understand", "Explain", "Note", "Connect", "Remember"].map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ol>
        </section>

        <section className="landing-philosophy">
          <p>The goal isn’t to give you more information.</p>
          <p>It’s to help you build better understanding.</p>
        </section>

        <section className="landing-final">
          <h2>Your next deep dive starts here.</h2>
          <p>Bring your sources. Ask better questions. Build knowledge that stays with you.</p>
          <div className="landing-hero-cta">
            <button type="button" className="landing-btn primary lg" onClick={onStart}>
              Start Researching →
            </button>
            <a className="landing-btn ghost lg" href="#product">
              Explore ResearchLM
            </a>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div>
          <strong>ResearchLM</strong>
          <p>Research deeply. Understand clearly. Remember what matters.</p>
        </div>
        <nav>
          <a href="#product">Product</a>
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
          <a href="#use-cases">Use cases</a>
          <a href="#top">About</a>
          <a href="#top">Privacy</a>
          <a href="#top">Terms</a>
        </nav>
        <small>© {new Date().getFullYear()} ResearchLM</small>
      </footer>
    </div>
  );
}

function UseCard({ title, copy, mock }: { title: string; copy: string; mock: string }) {
  return (
    <article className="use-card">
      <div className="use-mock">
        <span>ResearchLM</span>
        <p>{mock}</p>
      </div>
      <h3>{title}</h3>
      <p>{copy}</p>
    </article>
  );
}

function ProductMock() {
  return (
    <div className="product-frame" aria-hidden="true">
      <div className="product-chrome">
        <i /><i /><i />
        <span>ResearchLM</span>
      </div>
      <div className="product-ui">
        <aside className="product-side">
          <strong>ResearchLM</strong>
          <button type="button">New Research</button>
          <p>Workspace</p>
          <ul>
            <li className="on">AI / Machine Learning</li>
            <li>System Design</li>
            <li>Distributed Systems</li>
            <li>Research Papers</li>
          </ul>
          <p>Sources</p>
          <div className="product-upload">
            <span>Website URL</span>
            <div className="product-field">https://arxiv.org/…</div>
            <span>Document upload</span>
            <div className="product-field file">Upload PDF or Markdown</div>
          </div>
          <ul>
            <li>attention_is_all_you_need.pdf</li>
            <li>docs.site/retrieval</li>
          </ul>
        </aside>
        <section className="product-main">
          <h4>How does Retrieval-Augmented Generation reduce hallucinations?</h4>
          <p>
            RAG retrieves relevant passages from your corpus <i className="cite" data-src="01">[01]</i> before
            the model writes. Generation is then constrained by that evidence
            <i className="cite" data-src="02">[02]</i>, so claims stay attached to sources rather than invented
            from training memory <i className="cite" data-src="03">[03]</i>.
          </p>
          <div className="product-sources">
            <span>Sources</span>
            <button type="button" className="src" data-src="01"><b>01</b> RAG Research Paper</button>
            <button type="button" className="src" data-src="02"><b>02</b> Retrieval Documentation</button>
            <button type="button" className="src" data-src="03"><b>03</b> Architecture Notes</button>
          </div>
        </section>
        <aside className="product-notes">
          <strong>My Notes</strong>
          <p>RAG separates knowledge retrieval from generation…</p>
          <ul>
            <li><em>Key insight</em> Retrieve first, then write.</li>
            <li><em>Concept</em> Grounding reduces fabrication.</li>
            <li><em>Source</em> [01] RAG paper</li>
            <li><em>Related</em> Vector databases</li>
          </ul>
        </aside>
      </div>
    </div>
  );
}
