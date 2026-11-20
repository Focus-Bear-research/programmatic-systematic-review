# TODO — AuDHD digital-interventions reviews (adult + children)

Two companion systematic reviews. Run all commands from repo root
`/Users/s3255727/dev/literature-search`. Data lives under
`search-results-from-database/adults/` and `…/children/` (shared corpus: `…/all_papers.csv`).

**AWS (AI steps only):** Bedrock SSO expires ~daily — `aws sso login --profile phd`
(inline in a session: `! aws sso login --profile phd`). Manual screening steps need no AWS.

---

## Current status (so you don't re-derive)

**ADULT review — digital interventions for adults with co-occurring AuDHD**
- **Primary result: 0 confirmed includes**, robust even after relaxing population (any enrolled
  co-occurring AuDHD adult) and broadening intervention scope (apps/games/VR/AR/neurofeedback/EEG;
  telehealth + tDCS/TMS out). The genuine AuDHD-adult digital studies are small single-case
  (employment/leisure) or telehealth — none a controlled in-scope trial.
- **3 borderline pending author contact:** Drive Smart `10.1016/j.aap.2017.10.002` (ages of the
  4 co-occurring?), Bink `10.1007/s00787-014-0655-3` (age×diagnosis — also a children include),
  CET `10.1002/aur.1913` (any comorbid-ADHD adult enrolled?).
- **Validation/IRR done:** record-level recall **0.992**, specificity 0.75, κ 0.54 (the one FN was a
  human coding slip). Per-field κ invalid (short-circuit adjudication) — don't report it.
  Write-up: `manuscript/validation-irr-results.md`.
- **Exploratory broad-corpus analysis done** (`adults/adults_fulltext_analysis.csv`).

**CHILDREN review (<18)**
- **14 confirmed includes** (15 records w/ Bink follow-up) + **2 pending author contact**
  (Kinect, Brain Balance). List: `children/FINAL_includes_narrative_2026-08-23.csv`.
- **IRR with Sebrina (blind):** 94.9% agreement, κ 0.588 (96.4% / κ 0.74 once neurofeedback counted
  in-scope). Sebrina's screen recovered 1 search-miss include (van Dongen Cogmed RCT) and 0 of her
  29 maybes survived. Write-up: `manuscript/children-irr-sebrina.md`.

---

## ADULT — next steps
1. [ ] **Author contact** (Sebrina drafting) for the 3 borderline: Drive Smart, Bink, CET — get the
   co-occurring-adult subgroup ages / comorbidity. If any confirms a co-occurring adult who received
   the intervention → it becomes the first adult include.
2. [ ] **Finish the full-text redo:** retrieve the ~67 priority studies in
   `adults/adults_fulltext_to_retrieve_2026-08-23.{csv,xlsx}` (controlled + unspecified; peer-reviewed
   only — non-PR already dropped). On RMIT network / via Sebrina, then:
   ```
   UNPAYWALL_EMAIL=jeremy@focusbear.io poetry run python retrieve-fulltext-parallel.py adults/adults_fulltext_to_retrieve_2026-08-23.csv 8
   ADULT_SCOPING=1 poetry run python screen-adults-fulltext.py 8
   ```
3. [ ] **Re-derive the "323 adults" scoping count** — it's ~40% inflated by parent/provider studies
   (has_adults over-call, now fixed in `configs/adults.json`). Re-classify has_adults or apply the
   ~57% genuine-adult rate before citing. (Full-text check found 133/232 genuine adult-direct-subject.)
4. [ ] **Manuscript updates** (`manuscript/audhd-digital-interventions-review.md`):
   - Insert validation numbers (recall 0.99 / spec 0.75) → §2.2 + §5; do NOT report per-field κ.
   - Soften "confirmed empty (n=0)" → "no confirmed includes; 3 pending author-provided subgroup data",
     and note the void is robust to population-relaxation + intervention-broadening.
   - Fix the inflated 323 adult-studies figure (step 3).
   - Fold in the exploratory broad-corpus findings (intervention mix, co-design, designs, quality).
   - **Decide whether to report the children's expanded search as a supplementary adult search.**
     Manuscript PRISMA = 14,253 identified → 424 primary adult digital studies. `all_papers.csv` now
     has 19,067 rows (rows 14,253+ = children-scoped search, broader VR/game/robot/neurofeedback terms,
     no `adult` term) → 553 primary. That search surfaced **129 extra adult primary studies** the adult
     query missed (now in scope since VR/NF are). AuDHD count unchanged (8 either way), so n=0 holds,
     but it's a search-sensitivity finding worth reporting. The NOAT deck uses the 19,067 / 553 basis.
5. [ ] Co-author sign-off (Karimi, de Courten, Conduit, Ko); confirm COI (Focus Bear); pick journal.

## CHILDREN — next steps
1. [ ] **Author-contact emails** (Sebrina drafting) — if either reports a co-occurring subgroup they
   become includes 15/16:
   - Kinect `10.1089/g4h.2015.0103` (Weerdmeester, Radboud) — how many of the 88 AD(H)D children also had autism?
   - Brain Balance `10.3389/frcha.2024.1450695` (Jackson) — how many children had BOTH ADHD and autism?
2. [ ] **Tell Sebrina neurofeedback/EEG is in-scope** (she excluded 3 NFB studies on that basis;
   aligning it lifts IRR to ~96% / κ 0.74).
3. [ ] **VR-dental `10.3390/jcm13206093`** — team call on whether VR anxiety-distraction is on-target.
4. [ ] **Into Covidence** — import `children/covidence_import_15_studies.csv` (the candidates) and
   `children/covidence_import_irr_10pct.csv` (dual-screen IRR set); un-blind via
   `children/IRR_blind_KEY_internal.csv`.
5. [ ] **Data extraction + risk-of-bias** on the 14 includes → children manuscript (to be written).
6. [ ] Consider PROSPERO registration for the children review if not already done.

## SHARED / pipeline
- [ ] (Optional) lowercase `normalize_doi` + re-dedup the children master — case-variant DOIs still
  inflate children candidate counts (does NOT affect the adult manuscript).
- [ ] (Optional) clean per-field κ for adults would need a no-short-circuit ~100-record validation pass.

---

## File map (post-reorg)
- Shared corpus: `search-results-from-database/all_papers.csv`
- Adult: `…/adults/` — `fulltext_review_master.csv`, `nd_digital_adults_intent.csv`,
  `adults_fulltext_analysis.csv`, `adults_fulltext_screen_narrative.csv`,
  `adults_fulltext_to_retrieve_2026-08-23.{csv,xlsx}`, `validation_sample.csv`, `database-csvs/`
- Children: `…/children/` — `FINAL_includes_narrative_2026-08-23.csv`, `fulltext_screen_firstpass.csv`,
  `IRR_sebrina_vs_llm.csv`, `maybe_triage_2026-09-13.csv`, `covidence_*`, `database-csvs/`
- Manuscript: `manuscript/` — `audhd-digital-interventions-review.md`, `prisma-flow.md`,
  `validation-irr-results.md`, `children-irr-sebrina.md`, `peer-review.md`
