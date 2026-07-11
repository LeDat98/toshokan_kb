"""Demo mini-library so the walking skeleton (P1) is testable before ingest (P2) exists.

Static, handwritten content — no LLM calls. Descriptions follow the discriminative style
(what it covers + what it does NOT cover) that routing depends on (principle P2/P9).
"""

from __future__ import annotations

from libkb.library.models import ROOT_ID, NodeStats
from libkb.library.store import LibraryStore

SEED: dict = {
    "domains": [
        {
            "title": "AI",
            "description": (
                "Artificial intelligence: machine learning, large language models, retrieval "
                "systems and computer vision. Software engineering topics live elsewhere."
            ),
            "shelves": [
                {
                    "title": "RAG",
                    "description": (
                        "Retrieval-Augmented Generation: pipelines that fetch external knowledge before "
                        "generating — chunking, indexing, retrieval, reranking, evaluation. Does NOT cover "
                        "base model architecture or prompting — see the LLM shelf."
                    ),
                    "books": [
                        {
                            "title": "RAG Fundamentals",
                            "description": (
                                "Introduction to RAG: what it is, chunking strategies, embeddings and indexing. "
                                "Post-retrieval techniques like reranking are NOT here — see Advanced RAG Techniques."
                            ),
                            "chapters": [
                                (
                                    "Contents",
                                    [
                                        {
                                            "title": "What is RAG",
                                            "one_line": "RAG definition, comparison with fine-tuning, the basic pipeline",
                                            "keywords": [
                                                "retrieval-augmented generation",
                                                "grounding",
                                                "hallucination",
                                            ],
                                            "content": (
                                                "Retrieval-Augmented Generation (RAG) grounds a language model's answer in external\n"
                                                "knowledge fetched at query time. Instead of relying on parametric memory, the system\n"
                                                "retrieves relevant documents, injects them into the prompt as context, and generates\n"
                                                "an answer conditioned on that evidence.\n\n"
                                                "The basic pipeline has three stages: **retrieve** (find candidate passages for the\n"
                                                "query), **augment** (assemble them into the prompt), and **generate** (produce the\n"
                                                "grounded answer). Compared with fine-tuning, RAG updates knowledge by editing the\n"
                                                "corpus rather than retraining, provides citations naturally, and reduces — but does\n"
                                                "not eliminate — hallucination. Its main failure modes are retrieval misses and\n"
                                                "context that contradicts the model's priors."
                                            ),
                                        },
                                        {
                                            "title": "Chunking Strategies",
                                            "one_line": "Splitting documents: fixed-size, structure-aware, semantic; size trade-offs",
                                            "keywords": [
                                                "chunking",
                                                "splitting",
                                                "overlap",
                                                "chunk size",
                                            ],
                                            "content": (
                                                "Chunking splits documents into retrievable units. **Fixed-size** chunking (e.g. 512\n"
                                                "tokens with 10–15% overlap) is simple and predictable but cuts across semantic\n"
                                                "boundaries. **Structure-aware** chunking follows headings, paragraphs and code blocks,\n"
                                                "preserving meaning at the cost of variable sizes. **Semantic** chunking groups\n"
                                                "sentences by embedding similarity, producing coherent units but at higher indexing\n"
                                                "cost.\n\n"
                                                "The trade-off: small chunks improve retrieval precision but lose surrounding context;\n"
                                                "large chunks preserve context but dilute the embedding and waste prompt budget.\n"
                                                "A common compromise is structure-aware splitting targeting 400–1200 tokens, with\n"
                                                "parent-document retrieval when more context is needed at generation time."
                                            ),
                                        },
                                        {
                                            "title": "Embeddings & Indexing",
                                            "one_line": "Vectorization, similarity search, ANN indexes (HNSW/IVF), metadata filters",
                                            "keywords": [
                                                "embeddings",
                                                "vector index",
                                                "HNSW",
                                                "ANN",
                                                "cosine similarity",
                                            ],
                                            "content": (
                                                "Dense retrieval maps text to vectors so that semantic similarity becomes geometric\n"
                                                "proximity, usually cosine similarity over L2-normalized embeddings. Quality depends\n"
                                                "on the embedding model and on task-appropriate encoding (query vs document modes).\n\n"
                                                "At scale, exact nearest-neighbor search is too slow, so approximate indexes are used:\n"
                                                "**HNSW** (graph-based, fast and accurate, memory-hungry) and **IVF** (cluster-based,\n"
                                                "cheaper, needs tuning). Most production systems combine the vector index with\n"
                                                "metadata filters (source, date, access level) applied pre- or post-search.\n"
                                                "Index freshness matters: embeddings must be recomputed when content or the\n"
                                                "embedding model changes."
                                            ),
                                        },
                                    ],
                                )
                            ],
                        },
                        {
                            "title": "Advanced RAG Techniques",
                            "description": (
                                "Techniques beyond the basic pipeline: query rewriting before retrieval, hybrid search, "
                                "and reranking with cross-encoders after retrieval. Assumes RAG Fundamentals."
                            ),
                            "chapters": [
                                (
                                    "Pre-retrieval",
                                    [
                                        {
                                            "title": "Query Rewriting & Expansion",
                                            "one_line": "HyDE, multi-query, step-back — turning questions into better queries",
                                            "keywords": [
                                                "query rewriting",
                                                "HyDE",
                                                "multi-query",
                                                "step-back prompting",
                                            ],
                                            "content": (
                                                "User questions are often poor retrieval queries: too short, ambiguous, or phrased in\n"
                                                "vocabulary that does not match the corpus. Query rewriting uses an LLM to transform\n"
                                                "the question before retrieval.\n\n"
                                                "**Multi-query** generates several paraphrases and merges their results, improving\n"
                                                "recall. **HyDE** (Hypothetical Document Embeddings) asks the model to draft a\n"
                                                "hypothetical answer and retrieves by the draft's embedding — matching document\n"
                                                "language instead of question language. **Step-back prompting** first abstracts the\n"
                                                "question ('what general topic is this about?') to retrieve background context.\n"
                                                "All add one LLM call of latency; use them when baseline recall, not precision,\n"
                                                "is the bottleneck."
                                            ),
                                        },
                                    ],
                                ),
                                (
                                    "Retrieval & Post-retrieval",
                                    [
                                        {
                                            "title": "Hybrid Search: BM25 + Dense",
                                            "one_line": "Combining lexical and semantic via RRF — each covers the other's blind spots",
                                            "keywords": [
                                                "hybrid search",
                                                "BM25",
                                                "reciprocal rank fusion",
                                                "lexical",
                                            ],
                                            "content": (
                                                "Lexical search (BM25) matches exact terms — strong for identifiers, names, and rare\n"
                                                "keywords, but blind to synonyms. Dense retrieval matches meaning — strong for\n"
                                                "paraphrases, but it can miss exact tokens like error codes or function names.\n\n"
                                                "Hybrid search runs both and fuses results, most simply with **Reciprocal Rank\n"
                                                "Fusion**: score(d) = Σ 1/(k + rank_i(d)) across the ranked lists, k≈60. RRF needs no\n"
                                                "score calibration between systems, which is why it is the default fusion choice.\n"
                                                "Hybrid + reranking is the standard recipe for technical corpora where both jargon\n"
                                                "and paraphrase queries occur."
                                            ),
                                        },
                                        {
                                            "title": "Reranking & Cross-encoders",
                                            "one_line": "Re-scoring top-k with a cross-encoder — more accurate, more expensive",
                                            "keywords": [
                                                "reranking",
                                                "cross-encoder",
                                                "bi-encoder",
                                                "two-stage retrieval",
                                            ],
                                            "content": (
                                                "Reranking is a second scoring pass over the top-k candidates from first-stage\n"
                                                "retrieval. First-stage **bi-encoders** embed query and document separately, so\n"
                                                "scoring is a cheap vector comparison — fast but approximate. A **cross-encoder**\n"
                                                "reads the query and a candidate *together* through one transformer, modeling\n"
                                                "token-level interaction between them, which is far more accurate but too expensive\n"
                                                "to run over the whole corpus.\n\n"
                                                "Hence the two-stage design: retrieve ~50–100 candidates cheaply, rerank the top\n"
                                                "10–20 with the cross-encoder, keep the best 3–5 for the prompt. Reranking typically\n"
                                                "adds 100–500 ms but is often the single highest-leverage precision upgrade in a RAG\n"
                                                "stack. Alternatives include LLM listwise reranking (prompt the model to order\n"
                                                "candidates) and late-interaction models like ColBERT, which sit between the two\n"
                                                "extremes in cost and quality."
                                            ),
                                        },
                                    ],
                                ),
                            ],
                        },
                        {
                            "title": "RAG Evaluation",
                            "description": (
                                "Measuring RAG quality: faithfulness and relevance metrics, and how to build "
                                "evaluation sets. Not about improving retrieval itself — see the other RAG books."
                            ),
                            "chapters": [
                                (
                                    "Contents",
                                    [
                                        {
                                            "title": "Faithfulness & Relevance Metrics",
                                            "one_line": "Is the answer grounded in evidence and on-question; LLM-as-judge caveats",
                                            "keywords": [
                                                "faithfulness",
                                                "relevance",
                                                "context precision",
                                                "LLM-as-judge",
                                            ],
                                            "content": (
                                                "RAG evaluation separates the pipeline into measurable parts. **Faithfulness**: is\n"
                                                "every claim in the answer supported by the retrieved context? **Answer relevance**:\n"
                                                "does the answer address the question? **Context precision/recall**: did retrieval\n"
                                                "return the right passages, and how much of it was useful?\n\n"
                                                "These are usually scored by an LLM judge given the question, context and answer.\n"
                                                "LLM-as-judge is convenient but biased: it favors fluent answers, position and\n"
                                                "verbosity. Mitigate with rubric-anchored prompts, score justification, and periodic\n"
                                                "human calibration on a sample. Track metrics per corpus segment — averages hide\n"
                                                "regressions in small but important slices."
                                            ),
                                        },
                                        {
                                            "title": "Building Evaluation Sets",
                                            "one_line": "Synthetic questions from the corpus, golden sets, regression runs",
                                            "keywords": [
                                                "eval set",
                                                "synthetic questions",
                                                "golden set",
                                                "regression",
                                            ],
                                            "content": (
                                                "An evaluation set is question–evidence pairs: a query plus the passages that answer\n"
                                                "it. The cheapest source is **synthetic generation**: for each chunk, ask an LLM to\n"
                                                "write questions that the chunk answers, phrased the way a real user would ask —\n"
                                                "this doubles as a routing test, since the ground-truth location is known by\n"
                                                "construction.\n\n"
                                                "Add a small **golden set** of real, human-verified questions for calibration, and\n"
                                                "re-run the full suite on every pipeline change (chunking, embedding model, index).\n"
                                                "Watch for leakage: if the question copies the chunk's exact wording, retrieval looks\n"
                                                "artificially perfect — paraphrase during generation."
                                            ),
                                        },
                                    ],
                                )
                            ],
                        },
                    ],
                },
                {
                    "title": "LLM",
                    "description": (
                        "Large language models themselves: transformer architecture, attention, scaling laws, "
                        "and prompting techniques. Does NOT cover document retrieval pipelines — see the RAG shelf."
                    ),
                    "books": [
                        {
                            "title": "LLM Foundations",
                            "description": (
                                "How LLMs work inside: transformer blocks, the attention mechanism, and scaling laws. "
                                "Applied prompting is NOT here — see Prompt Engineering."
                            ),
                            "chapters": [
                                (
                                    "Contents",
                                    [
                                        {
                                            "title": "Transformer Architecture",
                                            "one_line": "Decoder-only stack: embedding, attention + MLP blocks, residual, LN",
                                            "keywords": [
                                                "transformer",
                                                "decoder-only",
                                                "residual",
                                                "layer norm",
                                            ],
                                            "content": (
                                                "Modern LLMs are decoder-only transformers: a token embedding layer followed by a\n"
                                                "stack of identical blocks, each combining multi-head self-attention with a\n"
                                                "position-wise MLP, wrapped in residual connections and layer normalization.\n"
                                                "Positional information comes from schemes like RoPE rather than learned absolute\n"
                                                "positions.\n\n"
                                                "Generation is autoregressive: the model predicts one next token at a time,\n"
                                                "conditioning on everything before it. Depth gives compositional power, width gives\n"
                                                "capacity; both are bounded in practice by the memory and latency of attention over\n"
                                                "long contexts."
                                            ),
                                        },
                                        {
                                            "title": "Attention Mechanism",
                                            "one_line": "QKV, scaled dot-product, multi-head, and why the KV cache exists",
                                            "keywords": [
                                                "attention",
                                                "QKV",
                                                "multi-head",
                                                "KV cache",
                                            ],
                                            "content": (
                                                "Self-attention lets each token gather information from all previous tokens. Each\n"
                                                "token produces a query (Q), key (K) and value (V) vector; attention weights are\n"
                                                "softmax(QKᵀ/√d), and the output is the weighted sum of values. **Multi-head**\n"
                                                "attention runs several such projections in parallel so different heads can track\n"
                                                "different relations (syntax, coreference, position).\n\n"
                                                "Attention cost grows quadratically with sequence length, which is why long-context\n"
                                                "inference relies on the **KV cache**: keys and values of past tokens are stored so\n"
                                                "each new token only computes its own Q against cached K/V. The cache is also why\n"
                                                "prompt prefixes can be reused cheaply across calls."
                                            ),
                                        },
                                        {
                                            "title": "Scaling Laws",
                                            "one_line": "The loss–params–data–compute relationship; the Chinchilla lesson",
                                            "keywords": [
                                                "scaling laws",
                                                "Chinchilla",
                                                "compute-optimal",
                                            ],
                                            "content": (
                                                "Scaling laws describe how loss falls predictably as parameters, data and compute\n"
                                                "grow — power-law curves smooth enough to extrapolate. The **Chinchilla** result\n"
                                                "showed many earlier models were undertrained: for a fixed compute budget, loss is\n"
                                                "minimized by scaling parameters and training tokens together (roughly 20 tokens per\n"
                                                "parameter), not by parameters alone.\n\n"
                                                "Practical consequences: smaller models trained on much more data can match larger\n"
                                                "undertrained ones, and inference cost — not just training loss — should drive model\n"
                                                "sizing. Downstream capabilities sometimes appear 'emergent', though part of that is\n"
                                                "an artifact of discontinuous metrics."
                                            ),
                                        },
                                    ],
                                )
                            ],
                        },
                        {
                            "title": "Prompt Engineering",
                            "description": (
                                "Getting better outputs at inference time: few-shot examples, chain-of-thought, "
                                "structured JSON output. Model internals are NOT here — see LLM Foundations."
                            ),
                            "chapters": [
                                (
                                    "Contents",
                                    [
                                        {
                                            "title": "Few-shot Prompting",
                                            "one_line": "Zero/few-shot, example selection, ordering and format of demos",
                                            "keywords": [
                                                "few-shot",
                                                "in-context learning",
                                                "examples",
                                            ],
                                            "content": (
                                                "In-context examples steer a model without changing weights. **Zero-shot** relies on\n"
                                                "instructions alone; **few-shot** prepends worked examples that fix the task's format,\n"
                                                "style and edge-case handling.\n\n"
                                                "What matters most is example *selection* and *format consistency*: examples similar\n"
                                                "to the current input help; inconsistent labels or formatting actively hurt. Order\n"
                                                "effects are real — models weight later examples more. For classification, cover the\n"
                                                "label space evenly to avoid biasing the prior. Few-shot competes with instruction\n"
                                                "quality: with strong instructions and schemas, fewer examples are needed."
                                            ),
                                        },
                                        {
                                            "title": "Chain-of-Thought",
                                            "one_line": "Step-by-step reasoning; when it helps and when it just burns tokens",
                                            "keywords": [
                                                "chain-of-thought",
                                                "reasoning",
                                                "step-by-step",
                                            ],
                                            "content": (
                                                "Chain-of-thought (CoT) prompting asks the model to reason step by step before\n"
                                                "answering. It helps on tasks with multi-step structure — arithmetic, logic, planning,\n"
                                                "multi-hop questions — because intermediate tokens give the model working memory.\n\n"
                                                "On simple lookup or extraction tasks CoT mostly adds latency and cost. Verbosity is\n"
                                                "not accuracy: models can produce confident-looking reasoning that is wrong, so for\n"
                                                "high-stakes use pair CoT with verification (self-consistency voting, or a separate\n"
                                                "checker pass). Reasoning-tuned models internalize much of this, making explicit CoT\n"
                                                "prompts less necessary."
                                            ),
                                        },
                                        {
                                            "title": "Structured Output & JSON Mode",
                                            "one_line": "Schema-constrained output, constrained decoding, retry on invalid",
                                            "keywords": [
                                                "structured output",
                                                "JSON schema",
                                                "constrained decoding",
                                            ],
                                            "content": (
                                                "Programs need parseable output. **JSON mode / structured output** constrains\n"
                                                "generation to a schema — either by constrained decoding (the sampler masks tokens\n"
                                                "that would break the grammar) or by validation-and-retry at the application layer.\n\n"
                                                "Practical rules: keep schemas flat and small; describe each field, because field\n"
                                                "names and descriptions act as prompts; make enums explicit rather than free text.\n"
                                                "Even with schema enforcement, values can be semantically wrong — validate\n"
                                                "post-parse and retry once with the error message included. Structured output pairs\n"
                                                "naturally with function calling, where the schema is the tool signature."
                                            ),
                                        },
                                    ],
                                )
                            ],
                        },
                    ],
                },
                {
                    "title": "CV",
                    "description": (
                        "Computer vision: convolutional networks and object detection. "
                        "Language models and retrieval are NOT here — see the LLM and RAG shelves."
                    ),
                    "books": [
                        {
                            "title": "Computer Vision Basics",
                            "description": "CNNs and object detection fundamentals: filters, pooling, one- vs two-stage detectors.",
                            "chapters": [
                                (
                                    "Contents",
                                    [
                                        {
                                            "title": "Convolutional Neural Networks",
                                            "one_line": "Convolution filters, pooling, feature hierarchy from edges to objects",
                                            "keywords": [
                                                "CNN",
                                                "convolution",
                                                "pooling",
                                                "feature hierarchy",
                                            ],
                                            "content": (
                                                "CNNs exploit two image priors: locality and translation invariance. A convolution\n"
                                                "layer slides small learned filters over the image, producing feature maps; pooling\n"
                                                "downsamples them, growing the receptive field. Stacked layers form a hierarchy —\n"
                                                "early filters detect edges and textures, deeper ones detect parts and objects.\n\n"
                                                "Weight sharing makes CNNs far more parameter-efficient than dense networks on\n"
                                                "images. Residual connections (ResNet) enabled very deep stacks by letting gradients\n"
                                                "flow through identity paths. Vision transformers now rival CNNs at scale, but CNNs\n"
                                                "remain strong when data or compute is limited."
                                            ),
                                        },
                                        {
                                            "title": "Object Detection",
                                            "one_line": "Two-stage vs one-stage (YOLO), IoU, NMS — localize and classify at once",
                                            "keywords": ["object detection", "YOLO", "IoU", "NMS"],
                                            "content": (
                                                "Detection outputs bounding boxes plus class labels. **Two-stage** detectors (Faster\n"
                                                "R-CNN) first propose candidate regions, then classify and refine each — accurate but\n"
                                                "slower. **One-stage** detectors (YOLO, SSD) predict boxes and classes in a single\n"
                                                "dense pass — fast enough for real time, historically slightly less accurate on small\n"
                                                "objects.\n\n"
                                                "Two shared ingredients: **IoU** (intersection-over-union) measures box overlap for\n"
                                                "matching and evaluation (mAP), and **NMS** (non-maximum suppression) removes\n"
                                                "duplicate detections of the same object. Modern variants replace hand-tuned anchors\n"
                                                "and NMS with end-to-end set prediction (DETR-style)."
                                            ),
                                        },
                                    ],
                                )
                            ],
                        },
                    ],
                },
            ],
        }
    ],
    # demand-driven in production (P9); one manual example so the UI/navigator can render it
    "see_also": [
        (
            "ai/rag",
            "ai/llm",
            "for base model behavior, attention/KV-cache and prompting",
        )
    ],
}


def apply(store: LibraryStore) -> NodeStats:
    """Build the seed library. Assumes an initialized, empty library."""
    for domain_data in SEED["domains"]:
        domain = store.create(ROOT_ID, "domain", domain_data["title"], domain_data["description"])
        for shelf_data in domain_data["shelves"]:
            shelf = store.create(domain.id, "shelf", shelf_data["title"], shelf_data["description"])
            for book_data in shelf_data["books"]:
                book = store.create(shelf.id, "book", book_data["title"], book_data["description"])
                for chapter_title, pages in book_data["chapters"]:
                    for page in pages:
                        store.write_page(
                            book.id,
                            page["title"],
                            page["content"],
                            chapter=chapter_title,
                            one_line=page["one_line"],
                            keywords=page["keywords"],
                            source_ref="seed",
                        )
    for from_path, to_path, note in SEED["see_also"]:
        store.add_see_also(store.resolve_path(from_path), store.resolve_path(to_path), note)
    return store.recompute_stats(ROOT_ID)
