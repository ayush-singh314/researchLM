# OpenClaw Dense Retrieval Evaluation Report

## Overview
This report documents the current dense-retrieval evaluation result for the `openclaw` dataset in `text_only` mode using the `text-embedding-3-small` embedding model. The evaluation setup is based on the repository's existing `evaluate.py` flow, which uses cached goldens, runs the current RAG graph, and scores outputs with DeepEval metrics including contextual precision, contextual recall, contextual relevancy, answer relevancy, and faithfulness. [1]

The recorded result row is: `num_questions=10`, `pass_rate=0.4`, `avg_contextual_precision=1.0`, `avg_contextual_recall=0.9333`, `avg_contextual_relevancy=0.6850`, `avg_answer_relevancy=0.8891`, `avg_faithfulness=0.9732`, `avg_top_k_hit=1.0`, and `avg_retrieved_context_count=4.0`. These values indicate that the current dense setup retrieves useful evidence reliably, but overall end-to-end passing performance is still limited. [1]

## Current Result

| Metric | Current value | Interpretation |
|---|---:|---|
| Dataset | openclaw | Single benchmark dataset evaluated with the current framework. |
| Strategy | dense | Dense retrieval is the current baseline under test. |
| Modality mode | text_only | The current run does not yet test multimodal retrieval. |
| Embedding model | text-embedding-3-small | Baseline embedding model for the dense setup. |
| Number of questions | 10 | Small but usable first benchmark set. |
| Pass rate | 0.40 | Only 4 out of 10 cases passed overall. |
| Avg contextual precision | 1.00 | Retrieved context was highly precise. |
| Avg contextual recall | 0.93 | Most needed information was retrieved. |
| Avg contextual relevancy | 0.69 | Context was not always tightly focused on the question. |
| Avg answer relevancy | 0.89 | Answers were generally on-topic. |
| Avg faithfulness | 0.97 | Answers stayed well grounded in retrieved evidence. |
| Avg top-k hit | 1.00 | Correct evidence appeared in retrieved results. |
| Avg retrieved context count | 4.0 | Retrieval depth is moderate and not excessively large. |

The most important pattern is that retrieval coverage looks strong while the final pass rate remains modest. This means the system is already finding the right evidence often, but the retrieved context and final answer composition are not yet consistently aligned tightly enough to pass all test cases. [1]

## Interpretation
The strongest signals in this run are `avg_contextual_precision=1.0`, `avg_contextual_recall=0.9333`, `avg_top_k_hit=1.0`, and `avg_faithfulness=0.9732`. Together, these suggest that dense retrieval is successfully surfacing relevant material and the answer generator is mostly staying grounded in that material rather than hallucinating. [1]

The weaker signal is `avg_contextual_relevancy=0.6850`, with a downstream effect on the overall `pass_rate=0.4`. In practical terms, this usually means the system is retrieving the right area of the document, but the final context bundle may still contain extra material, loosely matched chunks, or insufficiently focused evidence for some questions. [1]

`avg_answer_relevancy=0.8891` is good enough to show that answer generation is broadly working, but it is not yet strong enough to compensate for weaker context targeting. Since faithfulness is already very high, the next gains are more likely to come from improving retrieval focus and context quality rather than from changing the answer model immediately. [1]

## Likely Reasons
The current repository evaluation flow uses cached goldens, loads the document, adds it to the vector store, invokes the graph, and scores the outputs with DeepEval metrics. Because the framework is still closely tied to the original `evaluate.py` style pipeline, the current weak point is likely not missing evidence altogether, but how chunks are selected, grouped, or passed downstream for answering. [1]

The metric pattern supports this diagnosis. High precision, high recall, and high top-k hit suggest that dense retrieval is not fundamentally broken; instead, the context appears somewhat over-broad or not optimally ranked for the exact question intent, which lowers contextual relevancy and keeps pass rate lower than expected. [1]

Another factor is benchmark size. With only 10 questions, a few hard or noisy cases can depress pass rate noticeably, so this should be treated as a baseline result rather than a final judgment on system quality. [1]

## Next Steps
The next evaluation step should focus first on improving **contextual relevancy**, because that is the clearest bottleneck in the current result. The best near-term changes are:

- Review retrieved chunks for failed cases and inspect whether extra or weakly related passages are being included. [1]
- Tune chunking strategy, chunk size, or overlap so that retrieved units are more focused. [1]
- Add a lightweight reranking or filtering step before passing retrieved context to answer generation. [1]
- Keep the same dataset and cached goldens so the next run is directly comparable to this baseline. [1]

After that, the next benchmark progression should be:

1. Re-run dense retrieval after chunking or reranking improvements on the same 10 questions. [1]
2. Expand the benchmark size slightly, for example to 20 to 30 questions, to reduce variance from a very small sample. [1]
3. Compare `dense + text_only` against `dense + multimodal` once text retrieval is stable. [1]
4. Only then move to BM25 and hybrid retrieval, using this dense result as the baseline reference point. [1]

## Documentation Format Going Forward
To maintain clean evaluation documentation for resume and project tracking, each future experiment record should include:

- dataset name and version
- strategy and modality mode
- embedding model
- number of questions
- all metric averages
- key interpretation in 3 to 5 lines
- suspected failure reason
- next action item [1]

