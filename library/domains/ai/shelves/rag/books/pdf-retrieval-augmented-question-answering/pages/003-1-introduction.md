---
id: nd_01KXJ49A5W2B6E9Q15Y93197FJ
title: 1 Introduction
source_ref: abcxyz.pdf
---

## **1 Introduction** 

Recent progress in machine learning and natural language processing has remarkably improved interactions with digital documents leading to better information retrieval systems. The most important aspect is the Retrieval Augmented Generation (RAG) framework Lewis et al. [2020] for QA systems, which combines both retrieval and generation-based approaches for handling difficult questions. In our work, we enhance the existing RAG-based QA system for information extraction through text, images, vector diagrams/graphs, and tables provided in PDFs. 

RAG is designed to address the serious limitations of the large language models (LLMs) such as untruthfulness, false reasoning and hallucinations Bang et al. [2023]. RAG offers accurate and reliable solutions for generating contents and interacting with the users Sawarkar et al. [2024]. Retrieving information from PDF (Portable Document Format) has been drawing a huge attention in various academia and industries due to the data richness in PDF, from plain text, tables to high resolution images and intricate vector graphics, presenting an opportunity and a challenge at the same time. Traditional RAG-based QA systems focus primarily on text Lin [2024], Ma et al. [2023], Siriwardhana et al. [2023] while non-textual elements such as images, charts, tables and diagrams within PDFs are not thoroughly explored. Our objective is to address this gap by developing a comprehensive system capable of answering complex, multifaceted questions that necessitate the integration and interpretation of diverse data types. 

To achieve this, we introduce an end-to-end system that retrieves and processes images, diagrams, graphs, and tables embedded within PDF documents, extending beyond the capabilities of conventional text-centric RAG models. We also implement preprocessing steps including the removal of headers and footers, conversion of PDFs to markdown for easier manipulation, image captioning and table reformatting to enhance data readability and retrieval accuracy. Finally, we fine-tune language models to be RAG-aware, ensuring a better understanding of our data format and document domain. 

In the report, we discussed related work in 2, stated the objective of this project and implemention of preprocessing steps along with the model design in 3. We present our experiment in 4, results in 5 and conclude our report in 7.
