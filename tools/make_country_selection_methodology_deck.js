/* eslint-disable no-console */
const pptxgen = require("pptxgenjs");

// NOTE: pptx instance is passed in so we can use pptx.ShapeType safely.
function addTitle(pptx, slide, title, subtitle) {
  slide.addText(title, {
    x: 0.6, y: 0.7, w: 12.1, h: 0.8,
    fontFace: "Calibri", fontSize: 36, bold: true, color: "1F2937",
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.62, y: 1.55, w: 12.1, h: 0.6,
      fontFace: "Calibri", fontSize: 18, color: "374151",
    });
  }
  // bottom bar
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 7.08, w: 13.33, h: 0.42,
    fill: { color: "111827" }, line: { color: "111827" },
  });
}

function addHeader(pptx, slide, title, subtitle) {
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: 13.33, h: 0.75,
    fill: { color: "111827" }, line: { color: "111827" },
  });
  slide.addText(title, {
    x: 0.6, y: 0.15, w: 12.5, h: 0.45,
    fontFace: "Calibri", fontSize: 22, bold: true, color: "FFFFFF",
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.6, y: 0.82, w: 12.5, h: 0.4,
      fontFace: "Calibri", fontSize: 14, color: "374151",
    });
  }
}

function addBullets(slide, x, y, w, lines, opts = {}) {
  const fontSize = opts.fontSize ?? 18;
  const lineSpacing = opts.lineSpacing ?? 1.15;
  const bulletIndent = opts.bulletIndent ?? (fontSize * 0.9);
  const hanging = opts.hanging ?? (fontSize * 0.25);

  slide.addText(
    lines.map((t) => ({ text: t, options: { bullet: { indent: bulletIndent }, hanging } })),
    {
      x, y, w, h: opts.h ?? 4.8,
      fontFace: "Calibri",
      fontSize,
      color: "111827",
      valign: "top",
      lineSpacingMultiple: lineSpacing,
    }
  );
}

function addCallout(pptx, slide, x, y, w, h, title, body) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h,
    fill: { color: "F3F4F6" },
    line: { color: "D1D5DB", width: 1 },
    radius: 10,
  });
  slide.addText(title, {
    x: x + 0.25, y: y + 0.2, w: w - 0.5, h: 0.35,
    fontFace: "Calibri", fontSize: 14, bold: true, color: "111827",
  });
  slide.addText(body, {
    x: x + 0.25, y: y + 0.6, w: w - 0.5, h: h - 0.8,
    fontFace: "Calibri", fontSize: 13, color: "374151",
    valign: "top", lineSpacingMultiple: 1.15,
  });
}

function main() {
  const pptx = new pptxgen();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "Alula Teklu";
  pptx.company = "Alula / HRH";
  pptx.subject = "Comparator Country Selection Methodology (Ethiopia)";
  pptx.title = "Comparator Country Selection Methodology for Ethiopia";

  // --- Slide 1: Title ---
  {
    const s = pptx.addSlide();
    addTitle(
      pptx,
      s,
      "Comparator Country Selection Methodology for Ethiopia",
      "Global virtual benchmarking for HRH accountability, productivity & absenteeism reduction"
    );
    s.addText("Informing HRH reform and HRH-II design for HEP in Ethiopia", {
      x: 0.62, y: 2.2, w: 12.1, h: 0.5,
      fontFace: "Calibri", fontSize: 16, color: "4B5563",
    });
    s.addText("Draft methodology deck (text-only)", {
      x: 0.62, y: 2.75, w: 12.1, h: 0.4,
      fontFace: "Calibri", fontSize: 14, italic: true, color: "6B7280",
    });

    s.addNotes(`
[Sources]
1) OECD. Health at a Glance. OECD Publishing.
2) WHO. World Health Report 2000.
3) PHCPI. PHC Measurement/Indicator Framework.
4) Everitt et al. Cluster Analysis (Wiley).
5) Hastie et al. Elements of Statistical Learning (Springer).
6) OECD/JRC-EC. Handbook on Constructing Composite Indicators (OECD).
7) Bradley et al. Implementation Science (2009) 4:25.
8) Marsh et al. BMJ (2004) 329:1177–1179.
9) Saltelli et al. Global Sensitivity Analysis: The Primer (Wiley).
    `);
  }

  // --- Slide 2: Purpose & Outputs ---
  {
    const s = pptx.addSlide();
    addHeader(pptx, s, "Why this methodology?", "Goal, logic, and what the outputs are used for");

    s.addText("Overall objective", {
      x: 0.6, y: 1.35, w: 12.2, h: 0.35,
      fontFace: "Calibri", fontSize: 20, bold: true, color: "111827",
    });

    addBullets(s, 0.8, 1.8, 12.0, [
      "Identify a small set of comparator countries to support evidence-based learning for Ethiopia’s HRH priorities.",
      "Separate two learning needs: (1) ‘baseline peers’ for realism, and (2) ‘positive deviants’ for actionable improvement lessons.",
      "Make selection transparent and tunable (parameters can be sensitivity-tested).",
    ], { fontSize: 18, h: 2.6 });

    s.addText("Primary outputs", {
      x: 0.6, y: 4.55, w: 12.2, h: 0.35,
      fontFace: "Calibri", fontSize: 20, bold: true, color: "111827",
    });

    addBullets(s, 0.8, 5.0, 12.0, [
      "Similarity comparators (top K closest countries by multivariate distance).",
      "Aspirational comparators (near-peers that outperform Ethiopia on key indicators).",
      "Interpretation guidance: similarity_distance and (for aspirational) better_count.",
    ], { fontSize: 18, h: 2.2 });

    s.addNotes(`
[Sources]
Composite indicator and multivariate distance approaches: Everitt et al.; Hastie et al.; OECD/JRC Handbook.
Positive deviance framing: Bradley et al.; Marsh et al.
    `);
  }

  // --- Slide 3: 3-Step Benchmarking Funnel ---
  {
    const s = pptx.addSlide();
    addHeader(pptx, s, "Three-step benchmarking approach", "Peer grouping → Similarity scoring → Dual comparator selection");

    s.addShape(pptx.ShapeType.rect, {
      x: 0.8, y: 1.4, w: 11.75, h: 4.9,
      fill: { color: "F9FAFB" }, line: { color: "E5E7EB", width: 1 },
    });

    const boxW = 3.65, boxH = 2.2, gap = 0.4;
    const x1 = 1.1, y = 2.05;
    const xs = [x1, x1 + boxW + gap, x1 + 2 * (boxW + gap)];

    const steps = [
      { n: "1", t: "Peer grouping", b: "Filter candidates to ensure like-with-like comparison (contextual similarity)." },
      { n: "2", t: "Similarity scoring", b: "Compute standardized multivariate distance to Ethiopia using selected indicators." },
      { n: "3", t: "Dual comparator selection", b: "Produce (A) similarity peers and (B) aspirational near-peers (positive deviants)." },
    ];

    steps.forEach((st, i) => {
      s.addShape(pptx.ShapeType.roundRect, {
        x: xs[i], y, w: boxW, h: boxH,
        fill: { color: "FFFFFF" }, line: { color: "D1D5DB", width: 1 }, radius: 12,
      });
      s.addText(`Step ${st.n}`, {
        x: xs[i] + 0.25, y: y + 0.18, w: boxW - 0.5, h: 0.3,
        fontFace: "Calibri", fontSize: 12, color: "6B7280",
      });
      s.addText(st.t, {
        x: xs[i] + 0.25, y: y + 0.48, w: boxW - 0.5, h: 0.4,
        fontFace: "Calibri", fontSize: 18, bold: true, color: "111827",
      });
      s.addText(st.b, {
        x: xs[i] + 0.25, y: y + 0.95, w: boxW - 0.5, h: 1.15,
        fontFace: "Calibri", fontSize: 14, color: "374151",
        valign: "top", lineSpacingMultiple: 1.2,
      });
    });

    addCallout(
      pptx,
      s,
      0.8, 6.45, 11.75, 0.75,
      "Why dual sets?",
      "Similarity peers provide a realism baseline; aspirational near-peers support learning from better performers under broadly comparable constraints (positive deviance)."
    );

    s.addNotes(`
[Sources]
Multistage selection + composite methods: OECD/JRC Handbook; Everitt et al.
Positive deviance: Bradley et al.; Marsh et al.
    `);
  }

  // --- Slide 4: Step 1 — Peer Grouping ---
  {
    const s = pptx.addSlide();
    addHeader(pptx, s, "Step 1 — Peer grouping (context filter)", "Reduce spurious matches by enforcing comparability");

    s.addText("Peer filter criteria (where available in the dataset)", {
      x: 0.6, y: 1.25, w: 12.2, h: 0.35,
      fontFace: "Calibri", fontSize: 20, bold: true, color: "111827",
    });

    addBullets(s, 0.85, 1.75, 12.0, [
      "Income group (e.g., lower-middle income).",
      "Region / epidemiologic context (broad comparability stratum).",
      "Community Health Program (CHP) presence (program design feature).",
      "Design note: Exclude highly granular CHW taxonomy when it creates brittle filtering (e.g., ‘Types of CHW’).",
    ], { fontSize: 18, h: 2.9 });

    addCallout(
      pptx,
      s,
      0.6, 4.95, 12.1, 1.5,
      "Rationale",
      "Cross-country HRH comparisons are easiest to misread when countries differ fundamentally in resources or system architecture. A peer filter forces explicit ‘like-with-like’ comparisons before any numeric scoring."
    );

    addCallout(
      pptx,
      s,
      0.6, 6.6, 12.1, 0.75,
      "Practical output",
      "A reduced candidate pool that is sufficiently comparable to Ethiopia to justify distance-based benchmarking."
    );

    s.addNotes(`
[Sources]
Comparability constraints in system benchmarking: WHO 2000; PHCPI methodology docs; OECD benchmarking conventions.
    `);
  }

  // --- Slide 5: Step 2 — Similarity Scoring ---
  {
    const s = pptx.addSlide();
    addHeader(pptx, s, "Step 2 — Similarity scoring (Similarity Distance Score)", "Standardize indicators and compute weighted distance to Ethiopia");

    s.addText("Indicator set (numeric)", {
      x: 0.6, y: 1.25, w: 12.2, h: 0.35,
      fontFace: "Calibri", fontSize: 20, bold: true, color: "111827",
    });

    addBullets(s, 0.85, 1.7, 12.0, [
      "Outcomes / need: MMR, U5M, NMR, TFR",
      "Coverage / system performance proxies: CPR, PHC (index/proxy)",
      "Context constraints: Urbanization, GDP per capita",
    ], { fontSize: 18, h: 1.7 });

    s.addText("Standardization and distance", {
      x: 0.6, y: 3.55, w: 12.2, h: 0.35,
      fontFace: "Calibri", fontSize: 20, bold: true, color: "111827",
    });

    s.addShape(pptx.ShapeType.rect, {
      x: 0.8, y: 4.0, w: 11.8, h: 2.2,
      fill: { color: "F9FAFB" }, line: { color: "E5E7EB", width: 1 },
    });

    s.addText("Z-score per indicator j:", {
      x: 1.05, y: 4.15, w: 5.7, h: 0.3,
      fontFace: "Calibri", fontSize: 16, bold: true, color: "111827",
    });
    s.addText("zᵢⱼ = (xᵢⱼ − μⱼ) / σⱼ", {
      x: 1.05, y: 4.45, w: 5.7, h: 0.4,
      fontFace: "Calibri", fontSize: 20, color: "111827",
    });

    s.addText("Weighted Euclidean distance to Ethiopia:", {
      x: 6.1, y: 4.15, w: 6.3, h: 0.3,
      fontFace: "Calibri", fontSize: 16, bold: true, color: "111827",
    });
    s.addText("dᵢ = √( Σⱼ wⱼ ( zᵢⱼ − zᴱᵀᴴⱼ )² )", {
      x: 6.1, y: 4.45, w: 6.3, h: 0.4,
      fontFace: "Calibri", fontSize: 20, color: "111827",
    });

    addCallout(
      pptx,
      s,
      0.6, 6.35, 12.1, 1.05,
      "Missingness control",
      "Rows with excessive missingness are excluded to avoid unstable distance scores and biased comparisons."
    );

    s.addNotes(`
[Sources]
Standardization + distance methods are standard in clustering/composite indicator construction: Everitt et al.; Hastie et al.; OECD/JRC Handbook.
    `);
  }

  // --- Slide 6: Step 3 — Dual Comparator Selection ---
  {
    const s = pptx.addSlide();
    addHeader(pptx, s, "Step 3 — Dual comparator selection", "Similarity comparators vs aspirational comparators (positive deviance)");

    s.addShape(pptx.ShapeType.rect, { x: 0.7, y: 1.25, w: 5.95, h: 5.9, fill: { color: "FFFFFF" }, line: { color: "D1D5DB" } });
    s.addShape(pptx.ShapeType.rect, { x: 6.75, y: 1.25, w: 5.95, h: 5.9, fill: { color: "FFFFFF" }, line: { color: "D1D5DB" } });

    s.addText("A) Similarity comparators (baseline peers)", {
      x: 0.95, y: 1.5, w: 5.5, h: 0.45,
      fontFace: "Calibri", fontSize: 18, bold: true, color: "111827",
    });
    addBullets(s, 1.05, 2.05, 5.5, [
      "Sort countries by similarity_distance ascending.",
      "Select top K closest countries.",
      "Use as realism baseline: what’s typical under similar constraints.",
    ], { fontSize: 16, h: 2.2 });

    addCallout(
      pptx,
      s,
      0.95, 4.75, 5.5, 2.1,
      "Definition",
      "Top K countries with the smallest similarity_distance to Ethiopia."
    );

    s.addText("B) Aspirational comparators (near-peers that outperform)", {
      x: 7.0, y: 1.5, w: 5.6, h: 0.55,
      fontFace: "Calibri", fontSize: 18, bold: true, color: "111827",
    });
    addBullets(s, 7.1, 2.1, 5.6, [
      "Start from an aspirational pool: closest ~30% by similarity_distance.",
      "Compute better_count across priority indicators:",
      "• Lower is better: MMR, U5M, NMR, TFR",
      "• Higher is better: CPR, PHC",
      "Keep countries with better_count ≥ 3.",
      "Rank by better_count (desc), then similarity_distance (asc).",
    ], { fontSize: 15, h: 3.75 });

    addCallout(
      pptx,
      s,
      7.0, 6.0, 5.6, 1.15,
      "Why this works",
      "Identifies ‘positive deviants’: better performers that remain contextually close enough to yield transferable lessons."
    );

    s.addNotes(`
[Sources]
Positive deviance framing: Bradley et al. (Implementation Science, 2009); Marsh et al. (BMJ, 2004).
Parameter tunability + sensitivity checks: OECD/JRC Handbook; Saltelli et al.
    `);
  }

  // --- Slide 7: Interpretation of Outputs ---
  {
    const s = pptx.addSlide();
    addHeader(pptx, s, "How to interpret the outputs", "What ‘small’ vs ‘large’ means and how to read aspirational results");

    s.addText("Similarity distance (similarity_distance)", {
      x: 0.6, y: 1.25, w: 12.2, h: 0.35,
      fontFace: "Calibri", fontSize: 20, bold: true, color: "111827",
    });
    addBullets(s, 0.85, 1.7, 12.0, [
      "Smaller similarity_distance = more similar to Ethiopia across the full indicator set (context + outcomes).",
      "Larger similarity_distance = less similar.",
      "It is a distance (not a percentage) and is best interpreted relative to other countries in the same run.",
    ], { fontSize: 18, h: 1.6 });

    s.addText("Aspirational results (read two columns together)", {
      x: 0.6, y: 3.6, w: 12.2, h: 0.35,
      fontFace: "Calibri", fontSize: 20, bold: true, color: "111827",
    });
    addBullets(s, 0.85, 4.05, 12.0, [
      "better_count: higher = better relative to Ethiopia on priority indicators.",
      "similarity_distance: lower = closer overall to Ethiopia’s context/outcome profile.",
      "Best aspirational comparators balance BOTH: (a) multiple improvements and (b) contextual closeness (not outliers).",
    ], { fontSize: 18, h: 1.6 });

    addCallout(
      pptx,
      s,
      0.6, 5.9, 12.1, 1.3,
      "Practical use",
      "Similarity peers help set a realistic baseline; aspirational near-peers guide ‘what to emulate’ and what enabling conditions may be required to reproduce results."
    );
  }

  // --- Slide 8: References ---
  {
    const s = pptx.addSlide();
    addHeader(pptx, s, "References (for methodology slides)", "Cited works supporting benchmarking, composite indicators, and positive deviance");

    const refs = [
      "1. OECD. Health at a Glance (latest edition used). Paris: OECD Publishing.",
      "2. World Health Organization. The World Health Report 2000: Health Systems—Improving Performance. Geneva: WHO; 2000.",
      "3. Primary Health Care Performance Initiative (PHCPI). PHC Measurement/Indicator Framework and Methodology Documentation.",
      "4. Everitt BS, Landau S, Leese M, Stahl D. Cluster Analysis. 5th ed. Chichester: Wiley; 2011.",
      "5. Hastie T, Tibshirani R, Friedman J. The Elements of Statistical Learning. 2nd ed. New York: Springer; 2009.",
      "6. OECD; Joint Research Centre–European Commission. Handbook on Constructing Composite Indicators. Paris: OECD Publishing; 2008.",
      "7. Bradley EH, et al. Using positive deviance to improve quality of health care. Implementation Science. 2009;4:25.",
      "8. Marsh DR, et al. The power of positive deviance. BMJ. 2004;329:1177–1179.",
      "9. Saltelli A, et al. Global Sensitivity Analysis: The Primer. Chichester: Wiley; 2008.",
    ];

    s.addText(refs.join("\n"), {
      x: 0.8, y: 1.35, w: 12.0, h: 6.0,
      fontFace: "Calibri", fontSize: 16, color: "111827",
      valign: "top", lineSpacingMultiple: 1.2,
    });
  }

  const outPath = "Comparator_Country_Selection_Methodology_Ethiopia.pptx";
  pptx.writeFile({ fileName: outPath })
    .then(() => console.log(`Wrote ${outPath}`))
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
}

main();
