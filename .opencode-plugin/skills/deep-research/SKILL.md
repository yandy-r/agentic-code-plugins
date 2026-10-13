---
name: deep-research
description: Conducts multi-perspective strategic research. Use when investigating
  complex topics, comparing competitors, or gathering strategic intelligence.
---

# Deep Research - Asymmetric Research Squad

> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, abort before setup or dispatch and ask the caller to rerun without it. This target uses native standalone `subagent` calls only.

Strategic, multi-perspective research skill using the Asymmetric Research Squad methodology. Deploys 8 specialized persona agents to uncover insights from diverse viewpoints, followed by crucible analysis and emergent insight generation.

## Current Research Subject

**Researching**: `$ARGUMENTS`

Parse arguments (flags first, then the research subject):

- **--output-dir "..."**: Custom output directory (default: `research/[sanitized-subject]`)
- **research-subject**: Required. The topic to research (can be multi-word)

If no research subject provided, abort with usage instructions:

```
Usage: /deep-research [--output-dir "..."] [--dry-run] <research-subject>

Examples:
  /deep-research "AI model deployment strategies"
  /deep-research --output-dir docs/research/quantum "quantum computing applications"
  /deep-research --dry-run "cryptocurrency market dynamics"
```

---

## Phase 0: Research Definition & Setup

### Step 1: Parse Arguments

Extract from `$ARGUMENTS`:

2. **--output-dir**: Quoted string after flag (optional)
3. **--dry-run**: Boolean flag. Set `DRY_RUN=true` if present, else `false`.
4. **research-subject**: Remaining non-flag text (required)

Validate the research subject:

- Must be provided
- Should be a clear, focused topic
- Not too broad (e.g., "technology") or too narrow (e.g., "one specific bug")



### Step 2: Determine Output Directory

If `--output-dir` is provided, use that path.
Otherwise, create a sanitized directory name:

```bash
# Sanitize subject: lowercase, replace spaces with hyphens, remove special chars
SANITIZED=$(echo "$RESEARCH_SUBJECT" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-')
OUTPUT_DIR="research/${SANITIZED}"
```

### Step 3: Handle Dry Run

If `--dry-run` is present, display:

```markdown
# Dry Run: Deep Research on [Subject]

## Output Directory

$OUTPUT_DIR/

## Directory Structure
```

$OUTPUT_DIR/
├── objective.md
├── persona-findings/
│ ├── historian.md
│ ├── contrarian.md
│ ├── analogist.md
│ ├── systems-thinker.md
│ ├── journalist.md
│ ├── archaeologist.md
│ ├── futurist.md
│ └── negative-space.md
├── synthesis/
│ ├── crucible-analysis.md
│ └── emergent-insights.md
├── evidence/
│ └── verification-log.md
└── report.md

```

## Research Phases

### Phase 1: Asymmetric Persona Deployment (8 parallel agents)

1. **Historian** - Historical evolution, failed attempts, forgotten alternatives
2. **Contrarian** - Disconfirming evidence, expert critiques, documented failures
3. **Analogist** - Cross-domain parallels, biological/military/economic analogies
4. **Systems Thinker** - Second-order effects, stakeholder mapping, causal chains
5. **Journalist** - Current state, key players, latest developments
6. **Archaeologist** - Past solutions (10-50 years ago), obsolete approaches
7. **Futurist** - Patents, speculative research, 2030+ predictions
8. **Negative Space Explorer** - What's NOT discussed, adoption barriers

### Phase 2: The Crucible - Structured Analysis (2 parallel agents)

1. **ACH Analyst** - Analysis of Competing Hypotheses
2. **Contradiction Mapper** - Cross-persona disagreements

### Phase 3: Emergent Insight Generation (4 parallel agents)

1. **Tension Mapper** - Maximum disagreement points
2. **Pattern Recognizer** - Unexpected historical echoes
3. **Negative Space Analyst** - Unanswered questions
4. **Innovation Agent** - Novel hypotheses from persona combinations

### Phase 4: Strategic Report Synthesis

Final report consolidating all research into actionable intelligence.

## Next Steps

Remove --dry-run flag to execute the research.
```



Do not dispatch any `subagent` calls in dry-run mode.

**STOP HERE** - do not run prerequisite checks, create directories, write files, or deploy agents.

### Step 4: Create Research Infrastructure

Only run this step when `DRY_RUN=false`.

Run the prerequisite check script:

```bash
~/.config/opencode/skills/deep-research/scripts/check-prerequisites.sh "$OUTPUT_DIR"
```

Create the directory structure:

```bash
mkdir -p "$OUTPUT_DIR/persona-findings"
mkdir -p "$OUTPUT_DIR/synthesis"
mkdir -p "$OUTPUT_DIR/evidence"
```

### Step 5: Create Research Objective

Only run this step when `DRY_RUN=false`.

Write the research objective document to `$OUTPUT_DIR/objective.md`:

```markdown
# Research Objective: [Subject]

## Core Research Questions

[Generate 3-5 key questions to answer based on the subject]

## Success Criteria

- [ ] All 8 personas deployed with distinct search strategies
- [ ] Minimum 8-10 parallel searches per persona executed
- [ ] Contradictions and disagreements captured, not smoothed over
- [ ] Evidence hierarchy applied (primary > secondary > synthetic > speculative)
- [ ] Cross-domain analogies explored
- [ ] Temporal range covered (past, present, future)

## Evidence Standards

- Primary sources preferred over secondary analysis
- Citations required for all claims
- Confidence ratings assigned to findings
- Contradictions explicitly documented

## Perspectives to Consider

- Historical evolution
- Current state and trends
- Future possibilities
- Alternative viewpoints
- What's NOT being discussed

## Potential Biases to Guard Against

[List 2-3 potential biases based on the subject]
```

---

## Phase 1: Asymmetric Persona Deployment

### Step 6: Read Persona Prompts

Read the persona prompt templates:

```bash
cat ~/.config/opencode/skills/deep-research/templates/persona-prompts.md
```

### Step 7: Deploy 8 Persona Agents in Parallel

| Persona                 | Subagent Type         | Sub-agent role           | Output File                           | Search Depth |
| ----------------------- | --------------------- | ------------------------- | ------------------------------------- | ------------ |
| Historian               | `research-specialist` | `historian`               | `persona-findings/historian.md`       | 8-10 queries |
| Contrarian              | `research-specialist` | `contrarian`              | `persona-findings/contrarian.md`      | 8-10 queries |
| Analogist               | `research-specialist` | `analogist`               | `persona-findings/analogist.md`       | 8-10 queries |
| Systems Thinker         | `research-specialist` | `systems-thinker`         | `persona-findings/systems-thinker.md` | 8-10 queries |
| Journalist              | `research-specialist` | `journalist`              | `persona-findings/journalist.md`      | 8-10 queries |
| Archaeologist           | `research-specialist` | `archaeologist`           | `persona-findings/archaeologist.md`   | 8-10 queries |
| Futurist                | `research-specialist` | `futurist`                | `persona-findings/futurist.md`        | 8-10 queries |
| Negative Space Explorer | `research-specialist` | `negative-space-explorer` | `persona-findings/negative-space.md`  | 8-10 queries |

Each agent receives:

- The `objective.md` file content
- Their specific persona mandate from the template
- Instructions for SCAMPER query variation
- Output file path
- Evidence quality standards

Use the prompts from `persona-prompts.md` with variables substituted:

- `{{RESEARCH_SUBJECT}}` - The research topic
- `{{OUTPUT_DIR}}` - The output directory path

#### Path A — Standalone sub-agents (`STANDALONE_MODE=true`, default)

See `~/.config/opencode/shared/references/standalone-dispatch.md` for the full standalone-dispatch contract (Task vs Agent+team, anti-patterns, backstop policy).

**CRITICAL**: Deploy all 8 persona agents in a **SINGLE message** with **MULTIPLE native `subagent` calls**. Every call sets `background=false`, uses the configured agent model, and follows the shared result policy below.

If a child report is empty or contentless, record its `sessionID`, inspect the declared artifact or working-tree edits, preserve valid work, and make at most one retry before reporting the child result incomplete. An artifact can preserve work but does not prove a child response. Follow `~/.config/opencode/shared/references/standalone-dispatch.md`.

### Step 8: Monitor Persona Research Progress

Update todos to track persona deployment:

```
- [ ] Historian research completed
- [ ] Contrarian research completed
- [ ] Analogist research completed
- [ ] Systems Thinker research completed
- [ ] Journalist research completed
- [ ] Archaeologist research completed
- [ ] Futurist research completed
- [ ] Negative Space Explorer research completed
```

## Phase 2: The Crucible - Structured Analysis

### Step 9: Read All Persona Findings

After all 8 persona agents complete, read their outputs:

```bash
ls -la "$OUTPUT_DIR/persona-findings/"
cat "$OUTPUT_DIR/persona-findings/historian.md"
cat "$OUTPUT_DIR/persona-findings/contrarian.md"
cat "$OUTPUT_DIR/persona-findings/analogist.md"
cat "$OUTPUT_DIR/persona-findings/systems-thinker.md"
cat "$OUTPUT_DIR/persona-findings/journalist.md"
cat "$OUTPUT_DIR/persona-findings/archaeologist.md"
cat "$OUTPUT_DIR/persona-findings/futurist.md"
cat "$OUTPUT_DIR/persona-findings/negative-space.md"
```

### Step 10: Read Analysis Prompts

Read the analysis agent templates:

```bash
cat ~/.config/opencode/skills/deep-research/templates/analysis-prompts.md
```

### Step 11: Deploy Crucible Analysis Agents

| Agent                | Subagent Type               | Sub-agent role        | Output File                          | Task                               |
| -------------------- | --------------------------- | ---------------------- | ------------------------------------ | ---------------------------------- |
| ACH Analyst          | `general-purpose`           | `ach-analyst`          | `synthesis/crucible-analysis.md`     | Analysis of Competing Hypotheses   |
| Contradiction Mapper | `codebase-research-analyst` | `contradiction-mapper` | `synthesis/contradiction-mapping.md` | Map disagreements between personas |

Both agents receive:

- All 8 persona findings
- The objective.md file
- Their specific analysis mandate
- Output file path

#### Path A — Standalone sub-agents (`STANDALONE_MODE=true`, default)

**CRITICAL**: Deploy both analysis agents in a **SINGLE message** with **MULTIPLE native `subagent` calls**. Every call sets `background=false`, uses the configured agent model, and follows the shared result policy below.

If a child report is empty or contentless, record its `sessionID`, inspect the declared artifact or working-tree edits, preserve valid work, and make at most one retry before reporting the child result incomplete. An artifact can preserve work but does not prove a child response. Follow `~/.config/opencode/shared/references/standalone-dispatch.md`.

### Step 12: Evidence Triangulation

After crucible analysis completes, verify critical findings:

1. Identify claims made by multiple personas
2. Use WebFetch for primary source validation
3. Document verification results to `$OUTPUT_DIR/evidence/verification-log.md`:

```markdown
# Evidence Verification Log

## High-Confidence Findings

### [Finding 1]

- **Claimed by**: Historian, Journalist, Systems Thinker
- **Primary sources**: [URLs]
- **Verification status**: Confirmed
- **Confidence**: High

### [Finding 2]

- **Claimed by**: Contrarian
- **Primary sources**: [URLs]
- **Verification status**: Partial
- **Confidence**: Medium
- **Notes**: [Explanation]

## Contradictions Requiring Resolution

### [Contradiction 1]

- **Persona A says**: [Claim]
- **Persona B says**: [Counter-claim]
- **Evidence for A**: [Sources]
- **Evidence for B**: [Sources]
- **Resolution**: [Assessment]
```

## Phase 3: Emergent Insight Generation

### Step 13: Deploy Strategic Analysis Agents

| Agent                  | Subagent Type               | Sub-agent role          | Output File                        | Focus                              |
| ---------------------- | --------------------------- | ------------------------ | ---------------------------------- | ---------------------------------- |
| Tension Mapper         | `codebase-research-analyst` | `tension-mapper`         | `synthesis/tension-mapping.md`     | Maximum disagreement points        |
| Pattern Recognizer     | `general-purpose`           | `pattern-recognizer`     | `synthesis/pattern-recognition.md` | Unexpected historical echoes       |
| Negative Space Analyst | `codebase-research-analyst` | `negative-space-analyst` | `synthesis/negative-space.md`      | Unanswered questions               |
| Innovation Agent       | `general-purpose`           | `innovation-agent`       | `synthesis/innovation.md`          | Novel hypotheses from combinations |

> **Note on naming**: `negative-space-analyst` is deliberately distinct from Phase 1's
> `negative-space-explorer` to keep sub-agent `description` plus the role-specific `prompt` values unique across the full

All agents receive:

- All persona findings
- Crucible analysis results
- Evidence verification log
- Their specific analysis mandate

#### Path A — Standalone sub-agents (`STANDALONE_MODE=true`, default)

**CRITICAL**: Deploy all 4 strategic analysis agents in a **SINGLE message** with **MULTIPLE native `subagent` calls**. Every call sets `background=false`, uses the configured agent model, and follows the shared result policy below.

If a child report is empty or contentless, record its `sessionID`, inspect the declared artifact or working-tree edits, preserve valid work, and make at most one retry before reporting the child result incomplete. An artifact can preserve work but does not prove a child response. Follow `~/.config/opencode/shared/references/standalone-dispatch.md`.

## Phase 4: Strategic Report Synthesis

### Step 14: Read All Research Artifacts

Read all outputs to prepare for synthesis:

**Persona Findings** (8 files)
**Crucible Analysis** (2 files)
**Strategic Analysis** (4 files)
**Evidence Verification** (1 file)

### Step 15: Read Report Template

Read the report structure template:

```bash
cat ~/.config/opencode/skills/deep-research/templates/report-structure.md
```

### Step 16: Generate Final Report

Create `$OUTPUT_DIR/report.md` following the template structure.

**Synthesis Principles**:

1. **Organize by insight, not by persona** - Synthesize related findings
2. **Highlight contradictions** - Don't smooth over disagreements
3. **Evidence hierarchy** - Primary > Secondary > Synthetic > Speculative
4. **Actionable intelligence** - Focus on strategic implications
5. **Preserve uncertainty** - Mark areas requiring further research

### Step 17: Validate Research Quality

Run the validation script:

```bash
~/.config/opencode/skills/deep-research/scripts/validate-research.sh "$OUTPUT_DIR"
```

Fix any issues reported:

- Missing persona findings
- Empty synthesis files
- Insufficient evidence citations
- Formatting problems

### Step 18: Display Completion Summary

Provide comprehensive completion summary:

```markdown
# Deep Research Complete: [Subject]

## Research Overview

- **Subject**: [Research subject]
- **Output Directory**: $OUTPUT_DIR/
- **Total Files Created**: [count]

## Research Execution

### Phase 1: Persona Deployment

- Historian: [search count] queries, [findings count] findings
- Contrarian: [search count] queries, [findings count] findings
- Analogist: [search count] queries, [findings count] findings
- Systems Thinker: [search count] queries, [findings count] findings
- Journalist: [search count] queries, [findings count] findings
- Archaeologist: [search count] queries, [findings count] findings
- Futurist: [search count] queries, [findings count] findings
- Negative Space Explorer: [search count] queries, [findings count] findings

### Phase 2: Crucible Analysis

- ACH Analysis: [hypotheses count] hypotheses analyzed
- Contradiction Mapping: [contradictions count] contradictions identified

### Phase 3: Emergent Insights

- Tension Mapping: [tensions count] tensions identified
- Pattern Recognition: [patterns count] patterns discovered
- Negative Space: [gaps count] research gaps identified
- Innovation: [insights count] novel hypotheses generated

### Phase 4: Report Synthesis

- Final report: $OUTPUT_DIR/report.md

## Key Discoveries

[2-3 most surprising or valuable findings]

## Critical Contradictions

[Top 1-2 unresolved disagreements between personas]

## Evidence Quality

- **High-confidence findings**: [count]
- **Medium-confidence findings**: [count]
- **Speculative findings**: [count]
- **Primary sources cited**: [count]

## Research Gaps

[Top 3-5 areas requiring further investigation]

## Next Steps

1. **Review the report**: Read $OUTPUT_DIR/report.md
2. **Examine specific personas**: Dive into $OUTPUT_DIR/persona-findings/ for details
3. **Review synthesis**: Check $OUTPUT_DIR/synthesis/ for analysis
4. **Verify evidence**: See $OUTPUT_DIR/evidence/verification-log.md
```

---

## Quality Standards

### Research Execution Checklist

Phase 1 - Persona Deployment:

- [ ] All 8 personas deployed with distinct search strategies
- [ ] Minimum 8-10 parallel searches per persona executed
- [ ] Each persona file includes confidence ratings
- [ ] Evidence sources cited for all claims
- [ ] Contradictions within persona findings noted

Phase 2 - Crucible Analysis:

- [ ] ACH analysis generated 5+ mutually exclusive hypotheses
- [ ] Disconfirming evidence actively sought
- [ ] Cross-persona contradictions mapped
- [ ] Emergent patterns identified
- [ ] Verification log created with primary sources

Phase 3 - Strategic Analysis:

- [ ] Tension mapping identifies maximum disagreement
- [ ] Pattern recognition finds unexpected connections
- [ ] Negative space documents unanswered questions
- [ ] Innovation synthesis generates novel hypotheses

Phase 4 - Report Synthesis:

- [ ] Executive synthesis is information-dense (not summary)
- [ ] Multi-perspective analysis preserves persona insights
- [ ] Evidence portfolio includes confidence ratings
- [ ] Strategic implications address second/third-order effects
- [ ] Research gaps explicitly documented

### Persona Quality Checklist

Each persona finding should:

- [ ] Focus on its unique perspective
- [ ] Execute 8-10 diverse search queries
- [ ] Apply SCAMPER method for query variation
- [ ] Include confidence ratings on findings
- [ ] Cite primary sources
- [ ] Document uncertainties
- [ ] Capture contradictions with other sources

### Evidence Quality Checklist

- [ ] Primary sources > Secondary sources > Synthetic > Speculative
- [ ] All major claims have citations
- [ ] Contradictions explicitly documented
- [ ] Confidence ratings assigned
- [ ] Verification log maintained
- [ ] Sources are authoritative and current

---

## Best Practices

### SCAMPER Query Variation

When deploying personas, encourage diverse search strategies using SCAMPER:

- **Substitute**: What if we replace X with Y?
- **Combine**: How does X interact with Y?
- **Adapt**: How has this been done in other domains?
- **Modify**: What if we change the scale/scope?
- **Put to other uses**: What else could this be used for?
- **Eliminate**: What if we remove X?
- **Reverse**: What if we do the opposite?

### Evidence Hierarchy

Prioritize sources by quality:

1. **Primary**: Original research, official documentation, first-hand accounts
2. **Secondary**: Expert analysis, peer-reviewed synthesis, authoritative commentary
3. **Synthetic**: General media, aggregated data, secondary interpretations
4. **Speculative**: Predictions, opinion pieces, unverified claims

### Contradiction Management

When personas disagree:

- **Document**: Capture both viewpoints with evidence
- **Don't smooth**: Preserve the tension
- **Investigate**: Search for additional evidence
- **Assess**: Determine which is better supported
- **Report**: Include in final synthesis with confidence ratings

### Temporal Coverage

Ensure research spans:

- **Past** (10-50 years ago): Historical evolution, forgotten alternatives
- **Recent past** (1-10 years ago): Recent developments, failed attempts
- **Present**: Current state, key players, latest trends
- **Near future** (1-5 years): Emerging patterns, predictions
- **Far future** (5+ years): Speculative research, long-term implications

---

## Troubleshooting

### Issue: Persona findings are too similar

**Cause**: Personas not sufficiently differentiated
**Solution**: Re-read persona mandates, ensure distinct search strategies, add SCAMPER variation

### Issue: Too many speculative findings, not enough evidence

**Cause**: Insufficient primary source research
**Solution**: Use WebFetch to access primary sources, prioritize authoritative documentation

### Issue: Contradictions not being captured

**Cause**: Smooth-over tendency, lack of critical analysis
**Solution**: Explicitly instruct personas to find disconfirming evidence, deploy Contrarian first

### Issue: Research too shallow

**Cause**: Not enough search queries per persona
**Solution**: Ensure minimum 8-10 diverse queries per persona, use SCAMPER for variation

### Issue: Report is just a summary

**Cause**: Missing synthesis and analysis
**Solution**: Read all artifacts before writing report, focus on insights not summaries, highlight contradictions

### Issue: Research gaps not identified

**Cause**: Insufficient negative space analysis
**Solution**: Deploy Negative Space Explorer and Negative Space Agent, explicitly look for what's NOT discussed

---

## Important Notes

- **You are the research orchestrator** - coordinate persona agents, synthesize findings
- **Deploy in parallel** - single message per phase. Default uses multiple native `subagent` calls (standalone sub-agents).

- **Preserve contradictions** - don't smooth over disagreements
- **Evidence quality matters** - prioritize primary sources
- **Temporal coverage** - past, present, future perspectives
- **SCAMPER variation** - diverse search strategies per persona
- **Quality over quantity** - 8-10 well-crafted queries better than 20 generic ones
- **Strategic intelligence** - focus on actionable insights and implications
- **Document uncertainty** - mark areas requiring further research
