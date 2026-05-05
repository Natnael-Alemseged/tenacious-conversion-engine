**Knowledge Gap Formulation for Compounding**

*Daily Paired Gap Research, Public Explainers, and Portfolio Depth*

# **Summary**

Weeks 0 \- 11 made you ship systems. Week 12 will make you understand the different science and engineering components in them. By the end of this week you can explain the working principles inside the agents you built, defend the engineering choices you made, and teach others why the choices were the right ones among alternatives.

The mechanism is a paired daily research. Each day the cohort votes on a topic and its subtopics drawn from the engineering and scientific knowledge that underlies modern AI systems — multimodal embedding mechanics, real-time inference, agent tool-use internals, training and post-training mathematics, evaluation statistics, production patterns. You are randomly paired with a colleague. You each spend the morning identifying — through deep self-examination of your own work — the one gap in your understanding within that day's topic that genuinely warrants a colleague's day of research. You sharpen each other's questions in a morning call. You spend the day researching and writing an explainer for your partner's question. You critique each other's explainers in an evening call. Both blog posts and tweet threads ship publicly. The cohort votes on the sharpest questions; the highest-voted asker presents the next morning.

By Day 6 you have closed 10 gaps — five you named, five others named that you researched and explained. You have published five blog posts and five tweet threads under your own identity. You have committed five concrete improvements to your Weeks 10 and 11 portfolio work, each grounded in something you now actually understand. You have a personal canonical reading list of papers, tools, and engineering patterns.

# **The Shift From Weeks 0 \- 11**

This week is research and pedagogy. You are not building a new system. You are auditing the systems you already built, finding the places where you do not actually know how something works, doing the research to close those gaps, and producing artifacts that close the same gap for thousands of people on the internet who have it but cannot name it.

Three structural shifts from the prior weeks:

* **The deliverable is pedagogical.** Each day produces a blog post and a tweet thread that teach a specific concept to a specific person. Quality is judged by whether your partner's gap actually closed and by whether the artifact is rich enough to merit publication to the wider community.

* **The unit of work is the pair.** You and your partner are jointly accountable for the sharpness of each other's questions and the landing of each other's explainers. The pair changes every day.

* **The curriculum is co-authored by the cohort.** Topics and subtopics are voted by the cohort each evening from a tutor-anchored slate. Questions are voted by the cohort each morning. The week's content is what the cohort collectively decides matters most.

Your Weeks 10 and 11 artifacts remain in scope as the grounding target. Every gap you close this week must produce a concrete edit to existing work — a clarified probe, a sharper CFO memo paragraph, a corrected explanation in a Week 11 blog post, a tightened section of a model card, a refactored piece of agent code that you can now defend. The week is not theoretical. It pays back into the portfolio you have already built.

**What This Week Demands**

Both sides of the pair are doing real research every day. The structure does not work if either side treats their role as a transaction.

## **As the asker**

You are not asking a question off the top of your head. You are doing soul-searching gap analysis on the day's topic. You explore the topic and its subtopics broadly, surface multiple candidate gaps in your own understanding, and triage them honestly: which gaps are merely facts you could look up; which are vague unease that would not produce a useful explainer; which is the one non-trivial gap whose closure would meaningfully change how you think about the systems you have built.

That triage is the asker's research. It is the work of looking at your own probe library, your CFO memo, your trained judge, and asking: where am I making engineering choices that I cannot defend if pressed? Where do I use language that papers over a mechanism I do not actually understand? Which of those gaps is worth a colleague's day of research?

You commit to one question per day. The constraint forces the triage. A trainee who sends three soft questions has avoided the work.

## **As the explainer**

You are not answering the question directly. You are producing a piece of writing that closes the gap your partner named *and* connects the dots to the adjacent concepts that make the gap worth closing in the first place. A reader who lands on your blog post should leave understanding more than the literal question — they should see the question in its context, with the load-bearing mechanisms named, and with pointers to where the concept sits in the wider landscape of papers, tools, and engineering patterns.

This requires deep research on your side. You read at least two canonical papers or primary sources. You experiment with at least one engineering tool or pattern and produce code or a concrete demonstration. You judge — using your own taste — what adjacent ideas are worth connecting and which would dilute the focus. You write the blog so that it is both a useful answer to your partner's specific question and a piece of public technical writing that stands on its own merit.

The judgment is yours. The blog must answer the question well, but you decide what context, what analogies, what historical lineage, what production-side pitfalls belong in the piece. A blog that mechanically answers the question without context will not land your partner's gap and will not interest a public reader. A blog that wanders into adjacent material at the cost of the central question will not land your partner's gap either. The art is keeping focus while making the answer rich.

## **The negotiation pattern**

Sharpening happens in two real-time calls each day, one in the morning and one in the evening. The calls are not optional and are not substitutable by asynchronous text.

**Morning call (≥ 20 minutes).** Each partner reads the other's draft question aloud and interrogates it. "What do you mean by this?" "Are you asking about the mechanism or the consequence?" "Is this question really about X, or is it actually about Y in disguise?" The asker rewrites the question in response. By the end of the call the partner attests the question is unambiguous to them, and the asker's question is final for the day.

**Evening call (≥ 20 minutes).** Each partner reads the explainer they received and gives the writer specific feedback on what landed and what did not. "This paragraph assumes I already know X." "The analogy in tweet three does not carry the load." "You skipped the bit I was actually confused about." The writer revises. The asker then signs off — gap closed, partially closed, or not closed — on the revised version. The asker writes the grounding commit pointing to the actual edit they made to their existing portfolio work.

Either call may run longer if needed. Either partner may request a second call between the two main ones. Calls are real-time voice or video.

# **Identifying Gaps and Formulating Questions**

The hardest part of this week is naming what you do not know. Tools and patterns below help you do it well.

## **Surface gaps from your own work**

Open the day's topic. Then open one of your existing artifacts — a probe, a memo, a piece of agent code, a model card section. Read it as if you were a hostile reviewer. Where does the artifact use language that points at a mechanism you have not actually explained to yourself? Common signals:

* **Abstraction language without grounding.** "The agent maintains conversational state across turns." — Do you actually know how? Through what mechanism? At what cost?

* **Choice without defended reasoning.** "We use Qwen 3 1.7B for the judge." — Why that size? What is the speed-quality curve? What changes at 4B?

* **Citation-shaped phrases.** "As the LoRA paper shows..." — Do you know what it actually shows, or are you treating the citation as a load-bearing brick you have never inspected?

* **Numbers you cannot derive.** "p95 latency is 800 ms." — Where does that number come from? What are the components? What would change to make it 400?

* **Words that smuggle complexity.** "Embeddings," "attention," "context window," "alignment." — Each of these compresses a mechanism. Can you decompress it?

## **Use AI to surface gaps you do not know you have**

Treat the AI as an interrogator. Concrete prompt patterns that work:

*"Here is a paragraph from my \[CFO memo / model card / blog post\]: \[paste\]. List five things this paragraph asserts that I would not be able to defend if a senior engineer pushed back. For each, name the underlying mechanism I am glossing over."*

*"Today's topic is \[X\]. List the ten subtopics within X that a Forward-Deployed Engineer is most likely to have shallow understanding of. For each, give a one-sentence test question that would expose the gap."*

*"I claim I understand \[topic\]. Ask me the five questions whose answers would distinguish someone who has actually internalized the mechanism from someone who has only read about it."*

Use the AI's questions as candidates, not as your final question. Many will land near a real gap; pick the one whose closure would change something concrete in your existing work.

## **Formulate the question well**

A question worth a colleague's day of research has four properties. The same four properties drive peer voting and tutor grading.

| Property | What it means in practice |
| :---- | :---- |
| Diagnostic | The question names a specific gap. "How does multimodal embedding actually work?" is too broad. "How are vision tokens injected into the same residual stream as text tokens in a model like Qwen3-VL, and what does the cross-attention pattern between them look like during a typical inference?" is diagnostic. |
| Grounded in your work | The question connects to a specific artifact you have shipped. "Knowing this would let me revise \[the paragraph in my Week 11 model card that explains why I picked Qwen 2.5 1.5B instead of a multimodal backbone\]." The connection is named, with the artifact pointer. |
| Generalizable | The gap, if closed, helps not just you. Many FDE engagements would benefit from understanding this, not only your specific situation. |
| Resolvable in one explainer | The question is precise enough that a thoughtful colleague can produce a 600–1,000 word blog post that closes it. A question requiring a textbook chapter is too broad; one answered by reading a Wikipedia paragraph is too narrow. |

Test your question by reading it aloud to yourself before the morning call. If you cannot say what would constitute a satisfying answer in one or two sentences, the question is not yet sharp.

# **Writing the Explainer**

The blog post is 600–1,000 words (not a hard constraint but a suggestion). The tweet thread (could be linkedin post thread) is 4–6 tweets. Both ship under your own identity, publicly, after the evening call revisions.

## **Research before you write**

Before opening a writing surface, do the research:

* **Two canonical sources minimum.** Original papers when they exist. Authoritative documentation when papers do not. Avoid second-hand summaries; they propagate errors and obscure the mechanism.

* **One tool or pattern, hands on.** Run the relevant code. Inspect the actual outputs. If the question is about KV cache, profile a real inference and look at the cache hit rate. If the question is about LoRA, train a tiny adapter and compare gradients with and without it. If the question is about attention sinks, modify a generation loop and observe the effect. The blog earns trust by showing that you ran the thing, not just read about it.

* **Adjacent concepts.** Identify the two or three ideas neighboring the gap that make it land. For multimodal embedding, the adjacent concepts might include positional encoding, modality tokens, and cross-attention. Name them in your blog with enough depth that a reader sees the connection without losing the central question.

## **Structure the blog so it lands**

A blog that closes the gap typically has this shape (this is suggestion not a format guideline):

* **Open with the question your partner asked**, in your own words, with the specific reason it matters in their (or your) work. Do not generalize the question to its abstract form yet — anchor it concretely first.

* **Name the load-bearing mechanism.** One paragraph, plain language, that describes how the thing actually works at the level a Forward-Deployed Engineer needs to know. No more abstraction than necessary, no less than required to be correct.

* **Show it.** Code, diagram, or concrete worked example. Whatever makes the mechanism visible. If you ran a tool, show the relevant output.

* **Connect the dots.** Two or three adjacent concepts that make the gap worth closing in the first place. Brief — each adjacent concept gets a paragraph, not a section.

* **Pointers.** The two papers you read, the tool you used, and one or two follow-on directions for a reader who wants to go deeper.

The tweet thread compresses the same content. Tweet 1 names the question. Tweets 2–4 deliver the load-bearing mechanism with the visualization or code snippet. Tweet 5 connects to the adjacent concept with the highest signal. Tweet 6 links the blog. Each tweet must stand alone if the reader does not click through.

## **Judgment about scope**

You decide what belongs in the blog. The constraint is that the blog must close your partner's specific gap *and* read as an interesting standalone piece of public technical writing. Anything that fails either test is removed.

If the question is narrow but the topic is rich, do not pad the blog. Keep it tight; let the tweet thread do the wider connection.

If the question is broad, narrow your scope to one mechanism inside it and name explicitly what you chose to skip. "This blog focuses on X aspect of multimodal embedding; the adjacent question of Y is the one I would write about next." Honesty about scope is itself part of the artifact's quality.

# **The Daily Loop**

Each day runs a five-act loop that mirrors the structure of Weeks 10 and 11\. Times are guidelines; the calls and submissions are firm.

### **Act I — Topic and pair (morning)**

The cohort vote from the previous evening determines the day's topic and subtopics. Pairing for the day is published. You read the topic, the subtopics, and your partner's name.

### **Act II — Question identification and morning call (morning)**

Phase 1 ( independent): explore the topic and subtopics. Surface several candidate gaps from your own work. Triage and pick the one. Draft your question with its connection to a specific existing artifact. Use AI to pressure-test the question against the four properties.

Phase 2 (30 min, morning call): real-time call with your partner. Each of you interrogates the other's draft. Each of you rewrites in response. Both questions are committed final by the end of the call. Either partner writes the morning\_call\_summary.md (3–5 sentences) recording what was ambiguous and how the question was sharpened; the other confirms it.

### **Act III — Research and explainer drafting (midday and afternoon)**

You receive your partner's final question. You read at least two canonical sources, experiment with at least one tool or pattern, and write the blog post and tweet thread. Drafts go into the day's pair folder by late afternoon.

### **Act IV — Evening call, revision, sign-off (late afternoon)**

Phase 1 (independent): each of you reads the explainer you received without speaking. Form a private judgment. Note specific feedback.

Phase 2 (45 min, evening call): real-time call. Each of you gives the writer specific feedback on what landed and what did not. The writer revises. The asker signs off (closed / partially / not closed) on the revised explainer. The asker commits the grounding paragraph pointing to the actual edit made to their existing portfolio. Either partner writes the evening\_call\_summary.md; the other confirms.

### **Act V — Vote and present (evening, next morning)**

All questions from the day, with their morning-call summaries attached, go into the cohort vote. Voters score on the four-property rubric. Top three questions advance to next morning's presentation slot; the highest-voted asker presents first.

Cohort also votes on the next-day topic from the tutor-anchored slate. Tutors prepare 4–6 candidate topics, soliciting input from the cohort and the wider audience. Write-in topics are permitted; if a write-in receives the most votes, it wins.

Next morning, the highest-voted asker takes 15 minutes before Act I to present: what their gap was, what their partner's explainer revealed, what they changed in their existing work as a result. Recorded.

# **Pairing Protocol**

Pairs are randomly assigned daily. No two trainees pair twice in the same week. For odd cohort sizes, one triad rotates through the week with three-way calls replacing the two-call pair structure on triad days.

Pair contact for the day is through a dedicated daily-rotating Slack DM thread. Calls are on the cohort's standard voice-or-video tool.

# **Topic Spine and Cohort Voting**

Each evening tutors publish a slate of 4–6 candidate topics for the next day, anchored to the engineering and scientific knowledge that underlies modern AI systems. Topics are solicited from the cohort and the wider audience. The cohort votes overnight; the winner runs the next day. Write-in topics are permitted.

The starter topic bank below is illustrative anchoring for the kinds of topics that qualify. The cohort generates and votes its own slate from Day 2 onward.

### **Multimodal and embedding mechanics**

* How multimodal LLMs unify image and text token streams; what "vision tokens" actually are inside the transformer.

* Late fusion vs early fusion architectures and what each enables and forbids.

* Embedding-space geometry; what cosine similarity actually measures and where it misleads.

* Positional encoding variants (RoPE, ALiBi) and what they imply for long-context behavior.

### **Inference-time mechanics**

* How real-time voice inference achieves sub-800 ms latency end-to-end.

* KV cache mechanics; why prefix caching matters for cost; how cache invalidation actually works.

* Speculative decoding, draft models, and where the speedup actually comes from.

* Attention sinks and streaming context; why early tokens disproportionately affect later generation.

* The actual cost of a single inference call broken into prefill and decode phases.

### **Agent and tool-use internals**

* How function-calling actually works at the token level; what the model is doing when it "chooses" a tool.

* How MCP servers expose capability; what makes a tool description that the model uses well.

* Multi-turn agent planning and where it breaks; the role of scaffolding vs the role of the model.

* Reasoning-trace tokens vs final-output tokens in modern reasoning models; what is and is not part of the answer.

### **Training and post-training mechanics**

* What LoRA actually adapts; why low rank works at all; what changes at higher rank.

* The gradient mechanics of DPO vs SimPO vs ORPO; what each penalizes and rewards differently.

* Reward model overoptimization; how it manifests in production; the role of KL regularization.

* Instruction-following vs reasoning data and how they compete during post-training.

### **Evaluation and statistics**

* What pass^k actually measures and when it diverges from pass^1.

* Bootstrap CIs for agent benchmarks; when paired-bootstrap matters and when it does not.

* LLM-as-a-judge biases (position, length, self-preference) and how to detect and mitigate them.

* Contamination tests and what they can and cannot prove; the limits of n-gram overlap.

### **Production patterns**

* Rate limiting and backpressure for LLM API integrations under bursty load.

* Structured output and constrained decoding; what happens at the token level.

* Prompt caching mechanics and when it helps versus when it just adds latency.

* Observability for agent systems; what spans should capture and what they typically miss.

# **Voting Rubrics**

## **Question vote (evening \+ next day morning, on the day's questions)**

Voters score each question 1–5 on each property. Questions are read alongside their morning-call summaries so the sharpening process is visible.

| Property | Score 5 | Score 1 |
| :---- | :---- | :---- |
| Diagnostic | Names a specific gap whose closure changes how the asker does FDE work. | Vague, theoretical, or answerable by a Wikipedia paragraph. |
| Grounded in cohort work | Names a specific artifact whose quality depends on understanding this. | Connection generic or absent. |
| Generalizable | Closing the gap helps many FDE engagements, not only the asker. | Idiosyncratic or trivial to anyone outside the asker's situation. |
| Resolvable | A thoughtful colleague can write a 600–1,000 word explainer that closes it. | Requires a textbook chapter or is answered by a sentence. |

Top three questions advance to next morning's presentation slot. Tutors retain a tiebreaker and override authority where the popular vote diverges meaningfully from the rubric; overrides are posted publicly with a one-sentence rationale.

## **Topic vote (overnight, on the next day's topic)**

Voters select one topic from the tutor-anchored slate, or write in an alternative. The winning topic and its subtopics are published before the next day's Act I.

# **Daily Deliverables**

Submitted to Github repo by 23hr UTC each day, organized in a pair\_DAY\_N folder.

| File | Contents |
| :---- | :---- |
| question.md | Your final sharpened question with the named connection to a specific Week 10 or 11 artifact. |
| morning\_call\_summary.md | 3–5 sentences from either partner, confirmed by the other, recording what was ambiguous in the original drafts and how each question was sharpened. |
| explainer.md | The 600–1,000 word blog post you wrote for your partner, post-evening-call revision. |
| thread.md | The 4–6 tweet thread, post-revision, ready to publish. |
| evening\_call\_summary.md | 3–5 sentences recording what feedback the asker gave and what the writer revised. |
| signoff.md | The asker's gap-closure judgment (closed / partially / not closed) with one paragraph naming what they understand now that they did not before. |
| grounding\_commit.md | Pointer to the actual edit the asker made to a Week 10 or 11 artifact, with one paragraph explaining what changed and why. |
| sources.md | The two papers or canonical sources the explainer cited, plus the tool or pattern the writer used. |

# **Final Submission: Saturday, 21hr UTC**

Submit: Github repo final state, public artifact URLs, portfolio update.

### **Githiub repo (cumulative)**

* Five pair\_DAY\_N folders, each with the full daily deliverable set.

* synthesis.md — your 1,500-word week synthesis: the ten gaps closed (five you named, five you researched), the most surprising thing you learned, the canonical reading list and tool list you contributed to the cohort.

* canonical\_list.md — your annotated contribution to the cohort canon: the papers, tools, and patterns worth other Forward-Deployed Engineers reading.

* portfolio\_update.md — a one-page summary of how the five grounding commits collectively improve your Weeks 10 and 11 portfolio, written for an FDE hiring manager.

### **Public artifacts \- to be included in your repository README**

* Five blog post URLs published under your identity (HuggingFace blog, personal site, or Substack).

* Five tweet thread URLs published under your identity.

# **Public-Artifact Quality Bar**

Each blog post and tweet thread must pass the publication checklist before it ships under your identity.

| Check | Pass condition |
| :---- | :---- |
| Two canonical sources cited with links | Original papers when they exist; authoritative documentation otherwise. No second-hand summaries as load-bearing citations. |
| Code or concrete demonstration | A reader can run, inspect, or directly verify the central mechanism the blog claims. |
| No factual errors caught at tutor pre-publication review | Tutor reads each blog and thread before it ships; clears or returns with a single revision request. |
| Tweet thread reads standalone | A reader who never clicks through to the blog still gets a coherent and correct compressed explanation. |
| Asker sign-off received | Original asker has confirmed the post-revision explainer landed and is technically correct. |
| Attribution clean | Every cited paper, tool, and source credited. No fabricated or hallucinated references. |

# **Evidence-Graph Grading**

| Observable | Week 12 manifestation |
| :---- | :---- |
| Reproduction fidelity | Every technical claim in every blog and thread traces to a cited canonical source or to runnable code in the Github repo. A reader can verify each claim. |
| Question and explainer originality | Question quality scores from peer, tutor, and cohort vote. Explainer quality scores from asker sign-off and tutor. Trajectory across the week — does diagnosticity improve from Day 1 to Day 5? |
| Mechanism attribution | Grounding commits are real improvements to existing portfolio work. Call summaries show real interrogation, not perfunctory exchange. A tutor reviewing the artifact diff can name what the trainee learned from the explainer they received. |
| Cost-quality Pareto | Time-to-explainer and quality per blog. The trainee compresses without losing the load-bearing point and avoids padding when the topic is narrow. |
| Evidence-graph integrity | Every blog paragraph, every tweet, every grounding commit, every synthesis claim resolves to a source, an artifact, or a partner sign-off. |
| Public-artifact quality | Pre-publication checklist passed for every shipped artifact. Synthesis memo, canonical list, and portfolio update are coherent and defensible. |

The trajectory across Weeks 10, 11, and 12 is the cumulative diagnostic. A trainee who shipped a system in Week 10, built a benchmark and trained an adapter in Week 11, and can explain what they did with depth and teach others in Week 12 has the FDE-grade portfolio the program is designed to produce.

 

*Find the gap. Sharpen the question. Teach what you just learned. Edit what you already shipped.*