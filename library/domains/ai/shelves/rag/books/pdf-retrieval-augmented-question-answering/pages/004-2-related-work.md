---
id: nd_01KXJ49CCNR0TAZ7D641SF12M3
title: 2 Related Work
source_ref: abcxyz.pdf
---

## **2 Related Work** 

The rapid advancement in multimodal QA stems from integrating RAG into multi-data modality frameworks. This section reviews relevant studies and developments, highlighting their contributions, methodologies and limitations of Integration of RAG with PDF Processing for QA. 

### **2.1 Retrieval-Augmented Generation (RAG)** 

Large language models (LLMs) have advanced AI but have limitations like hallucinations and inaccuracies. RAG improves text accuracy by leveraging retrieved documents. Corrective Retrieval Augmented Generation (CRAG) introduces evaluators to assess document quality and refine retrieval actions Yan et al. [2024]. Unlike RAG, RAG-end2end Siriwardhana et al. [2023] jointly trains retrievers and generators, enhancing open-domain question answering by updating all components, including external knowledge bases. 

### **2.2 Question Answering (QA) with Language Models (LLMs)** 

Xu et al. [2023] democratizes advanced chat models, enhancing Llama’s dialogue performance through fine-tuning and Self-Distillation with Feedback (SDF) further improves its capabilities. Comparing RAG and fine-tuning with synthetic data, fine-tuning shows significant performance improvements Soudani et al. [2024]. ChatQA Liu et al. [2024] surpasses GPT-4 in retrieval-augmented generation and conversational QA. The Chain-of-Action (CoA) framework Pan et al. [2024] addresses complex questions by decomposing them into reasoning chains, effectively tackling hallucinations. 

### **2.3 Multimodal Question Answering Systems** 

Multimodal QA systems integrate diverse data modalities like text, tables, and images, improving real-world application accuracy. MMLLMs architecture Zhang et al. [2024] and the tool-interacting divide-and-conquer strategy Rajabzadeh et al. [2023] enhance reasoning and accuracy. 

### **2.4 Integration of RAG with PDF Processing for QA** 

PDFTriage Saad-Falcon et al. [2023] bridges this gap by enabling models to retrieve context based on both structure and content, but is challenged by the metadata variability, document format limitations, scalability, computational requirements, and datasets scope. A case study in the agricultural domain Gupta et al. [2024] demonstrated the approach combining RAG and Fine-Tuning exhibited superior performance when dealing with geographically specific knowledge. However, it does not fully leverage all available data types. This limitation reduces their effectiveness in scenarios that require integrated data sources, such as combining text with images and captions. 

In our approach, we make use of the existing RAG model to answer queries relevant to PDF documents and overcome the above limitations regarding metadata handling, format compatibility and integration of different data sources from previous works.

## **3 Methodology**
