---
id: nd_01KXJ49H9VBFD1B4ZGYHYK4GNE
title: 3 Methodology — 3.2 System Design
source_ref: abcxyz.pdf
---

### **3.2 System Design** 



Figure 1: PIER-QA: PDF Integrated Enhanced Retrieval Question Answering 

Given a query _q_ and a set of PDF documents _{D_ 1 _, D_ 2 _, . . . , Dn}_ . The goal is to retrieve most accurate information from these documents and generate a precise answer _a_ . We propose PDF Integrated Enhanced Retrieval Question Answering (PIER-QA) system consisting of three main components as shown in Figure 1. 

**PDF Preprocessing.** Headers and footers are removed using DBSCAN clustering algorithm Fahim [2022] which improves accuracy, ensuring documents are formatted for further processing. They are then converted to markdown through a machine-learning-based tool – Marker Paruchur [2023]. Marker is a lightweight and easy to read format that simplifies further processing steps. In markdown format, we generate captions for images and compress markdown tables into a dictionary format for efficient storage and retrieval. 

**Embedding and Storage.** The preprocessed markdown document is segmented into chunks of 1000 characters each, embedded by GTE-large Li et al. [2023] and stored using ElasticSearch Kathare et al. [2020] for efficient retrieval. RAPTOR Sarthi et al. [2024] is used to enhance this process by indexing and clustering the chunks based on their semantics, improving the retrieval process. 

**Question answering.** Upon receiving a query from the user, ElasticEearch embeds the query, retrieves top-10 relevant chunks and uses the chunks as external knowledge to generate answers with our RAG-Aware LLM. If the LLM answer contains an image ID or a table, we recover the corresponding image and table format before displaying to the user. 

3
