---
id: nd_01KXJ49WK4R7165XT99PRVBGY1
title: 3 Methodology — 3.2.2 Embedding and storage
source_ref: abcxyz.pdf
---

### **3.2.2 Embedding and storage** 

The first step involves breaking down the processed document _D_<sup>ˆ</sup> _imarkdown_ into smaller chunks _{c_ 1 _, c_ 2 _, ...cm}_ . Data consisting of text, image captions and dictionary-formatted tables into separate segments. Each chunk _Cj_ is embedded into a high-dimensional vector space using an embedding model _fembed_ : 



These embeddings are then stored in a searchable database (Elasticsearch): 



To enhance the retrieval process, we employ Recursive Abstractive Processing for Tree-Organized Retrieval (RAPTOR) for semantic indexing. It creates a tree structured index based on semantic content of the chunks for precise retrieval. 

5

### **3.2.3 Question Answering**
