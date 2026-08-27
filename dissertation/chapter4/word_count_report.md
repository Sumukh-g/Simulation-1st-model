# Chapter 4 word count

Counts are whitespace-delimited English words from the generated Word file.
Table cells and captions are excluded from the body total, as requested.

- Body paragraphs (excluding headings, tables, captions): **3695**
- Headings: 72
- Captions: 319
- Table cell words: 1357
- Body plus headings (the narrative chapter): **3767**

Target for the chapter body was 3,500 to 5,000 words excluding tables and captions.
If the bound dissertation already contains a references chapter, the short Chapter 4
reference list should be merged rather than duplicated.

Dash check: generate_chapter4_docx.py contains no em dash or en dash characters.
Post-build scan of word/document.xml in GSIP_Dissertation_Chapter4.docx: em dash = 0, en dash = 0.
PDF export: GSIP_Dissertation_Chapter4.pdf (LibreOffice 24.2.7 writer_pdf_Export).
