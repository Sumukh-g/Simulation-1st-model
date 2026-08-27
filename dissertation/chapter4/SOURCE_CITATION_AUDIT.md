# Source and citation audit (Chapter 4)

Harvard in-text citations in Chapter 4 map to the chapter reference list as follows.

| In-text form | Reference list entry | Used for |
|---|---|---|
| Zitzler, Deb and Thiele (2000) | Zitzler, E., Deb, K. and Thiele, L. (2000) Evolutionary Computation, 8(2), pp. 173-195. | ZDT problem family |
| Deb, Thiele, Laumanns and Zitzler (2002) | Deb, K., Thiele, L., Laumanns, M. and Zitzler, E. (2002) in Abraham, Jain and Goldberg (eds.). | DTLZ2; inexpensive population search on a spherical front |
| Knowles (2006) | Knowles, J. (2006) IEEE TEC, 10(1), pp. 50-66. | ParEGO / Chebyshev scalarisation |
| Knowles, Thiele and Zitzler (2006) | TIK Report 214, ETH Zurich. | Equal function-evaluation budget as the scarce resource |
| ISO/IEC (2023) | ISO/IEC 25010:2023 | Quality characteristics in Section 4.5 |
| NIST (2023) | NIST AI RMF 1.0 (NIST AI 100-1) | Measurement, documentation and governance |
| NIST (2024) | NIST AI 600-1 Generative AI Profile | Generative-AI risk profile cited in 4.5 framing |
| OWASP (2023) | OWASP API Security Top 10 | API identity and authorisation findings |

No citation is used to stand in for an unrun experiment. Repository documentation is named as a file path, not as a bibliographic source.

## Numbers that were not taken from papers or from `docs/`

All hypervolume, IGD, wall-time, Kruskal-Wallis and Mann-Whitney figures in Chapter 4 come from `evidence/benchmark_stats.json`, which was computed from `evidence/benchmark_campaign.json`. The research-paper drafts in this repository that report random-search p-values were not used.
