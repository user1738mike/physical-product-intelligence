import Link from "next/link";

export default function Home() {
  return (
    <main>
      <header className="masthead">
        <Link
          href="/"
          className="brand"
          aria-label="Physical Product Intelligence Cloud home"
        >
          <span className="mark" aria-hidden="true">
            P
          </span>
          <span>
            PHYSICAL PRODUCT
            <br />
            INTELLIGENCE CLOUD
          </span>
        </Link>
        <Link href="/account" className="stage">
          Sign in / Account
        </Link>
      </header>
      <section className="hero" aria-labelledby="title">
        <div className="copy">
          <p className="eyebrow">PHYSICAL COMMERCE / STRUCTURED KNOWLEDGE</p>
          <h1 id="title">
            Understand the product.
            <br />
            <span>Inform the handling.</span>
          </h1>
          <p className="intro">
            Building a traceable foundation for product and packaging
            intelligence, beginning with warehouse automation.
          </p>
          <p className="status">
            <span aria-hidden="true" />
            Platform foundation in development
          </p>
        </div>
        <div className="diagram" aria-hidden="true">
          <div className="diagram-grid" />
          <div className="dimension top">PRODUCT / PACKAGING</div>
          <div className="parcel">
            <div className="parcel-seam" />
            <span>01</span>
          </div>
          <div className="dimension bottom">
            EVIDENCE → CONSTRAINTS → ASSESSMENT
          </div>
          <span className="coordinate">X / Y / Z</span>
        </div>
      </section>
      <section className="principles" aria-label="Design direction">
        <article>
          <span className="index">01 /</span>
          <h2>Structured inputs</h2>
          <p>
            Designed to preserve product measurements, packaging context and
            their sources.
          </p>
        </article>
        <article>
          <span className="index">02 /</span>
          <h2>Explicit constraints</h2>
          <p>
            A planned workflow grounded in configurable handling requirements.
          </p>
        </article>
        <article>
          <span className="index">03 /</span>
          <h2>Traceable outcomes</h2>
          <p>
            Evidence, uncertainty and reproducibility guide the assessment
            design.
          </p>
        </article>
      </section>
      <footer>
        <span>Physical Product Intelligence Cloud</span>
        <p>
          Product records and packaging APIs are available. Uploads and
          assessments are not yet available.
        </p>
      </footer>
    </main>
  );
}
