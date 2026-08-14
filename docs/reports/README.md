# GSIP Reports

This folder contains comprehensive **Technical** and **Business** reports for the General Simulation Intelligence Platform (GSIP), plus a **Questions** document for FAQs, stakeholder discussions, and due diligence.

## Documents

| File | Description |
|------|-------------|
| **GSIP_Technical_Report.md** | Full technical report: architecture, data flow, components, contracts, quality gates, security, observability, deployment. |
| **GSIP_Technical_Report.pdf** | PDF export of the technical report. |
| **GSIP_Business_Report.md** | Business report: product overview, business model, market, differentiation, go-to-market, risks, strategy. |
| **GSIP_Business_Report.pdf** | PDF export of the business report. |
| **GSIP_Questions.md** | Curated questions: product/value, technical, business, compliance, roadmap, stakeholder/due diligence, discussion prompts. |
| **GSIP_Questions.pdf** | PDF export of the questions document. |

## Regenerating PDFs

From the project root:

```bash
pip install fpdf2
python scripts/generate_report_pdfs.py
```

PDFs are written to `docs/reports/` (same folder as the Markdown sources).

## Editing

Edit the `.md` files, then run the script above to refresh the PDFs.
