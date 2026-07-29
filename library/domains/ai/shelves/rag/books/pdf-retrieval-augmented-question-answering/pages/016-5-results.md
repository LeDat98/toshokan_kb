---
id: nd_01KXJ4A7XWNSRD9SYYQCYY6B55
title: 5 Results
source_ref: abcxyz.pdf
---

## **5 Results** 

### **5.1 Comparison with Baseline** 

To benchmark our system, we compared it with a baseline system that employs a similar approach. The baseline system parses the PDF files into plain text and saves these text chunks into a database. The retrieval process involves fetching these chunks and including them in the LLM prompt using either GPT-3.5-turbo or GPT-4o. Unlike our system, the baseline does not incorporate preprocessing steps such as header/footer removal or markdown conversion, nor does it retrieve images, diagrams and tables. Both systems were evaluated using the same set of 100 test questions. We measured the performance using the similarity metric and the accuracy at different thresholds (accuracy@0.85, accuracy@0.9 and accuracy@0.95). 

|**System**|**LLM Agent**|**Similarity**|**Accuracy**<br>**@0.85**|**Accuracy**<br>**@0.9**|**Accuracy**<br>**@0.95**|
|---|---|---|---|---|---|
|Baseline|GPT-3.5-turbo|0.8639|0.5889|0.3667|0.060|
|Baseline|GPT-4o|0.8647|0.6444|0.4000|0.1111|
|PIER-QA|GPT-3.5-turbo|0.8666|**0.7640**|0.3708|0.1124|
|PIER-QA|GPT-4o|**0.8837**|0.7191|**0.4944**|**0.191**|



Table 1: Scores comparison with Baseline 

The results in Table 1 demonstrate a clear performance advantage of the PIER-QA system over the baseline. Notably, PIER-QA achieved higher similarity scores and accuracy across all thresholds (0.85, 0.9, and 0.95) with both GPT-3.5-turbo and GPT-4o agents. This improvement is attributed to the enhanced preprocessing steps, including header/footer removal and markdown conversion, as well as the effective retrieval and integration of images, diagrams, and tables. These advancements enabled PIER-QA to generate more accurate and relevant responses, particularly at higher accuracy thresholds, highlighting its capability to handle complex PDF-based questions comprehensively. 

### **5.2 Investigation of different LLM agents** 

To understand the impact of different language models on our system’s performance, we evaluated the system using three different LLM agents: GPT-4o, GPT-3.5-turbo and Llama3-70B-Instruct, and our RAG-Llama3-70B. Each LLM agent was integrated into our system and the same set of 100 questions are used for evaluation. It’s also worth noting that the Llama3-70B-Instruct and our RAG-Llama3-70B were quantized at 4-bit precision for efficiency. 

|**LLM Agent**|**Similarity**|**Accuracy**<br>**@0.85**|**Accuracy**<br>**@0.9**|**Accuracy**<br>**@0.95**|
|---|---|---|---|---|
|GPT-3.5-turbo|0.8666|**0.7640**|0.3708|0.1124|
|GPT-4o|0.8837|0.7191|**0.4944**|**0.1910**|
|Llama3-70B-Instruct|0.8156|0.5280|0.2921|0.1348|
|RAG-Llama3-70B|**0.8771**|0.7303|0.4719|0.2135|



Table 2: Scores comparison of different LLM agents. Best scores are highlighted in **bold** while second best scores are underlined. 

In Table 2, GPT-4o achieved the highest similarity score of 0.8837 and the best accuracy at 0.9, highlighting its strong retrieval and question-answering capabilities. However, our RAG-Llama3-70B 

7 

model demonstrated notable performance as well. It outperformed the other models in terms of accuracy at the highest threshold – 0.9, and achieved the second-best scores on the other metrics, closely trailing GPT-4o even at 4-bit precision. This underscores the effectiveness of our RAGAware finetuning in adapting the model into the document domain and our system structure. 

### **5.3 Table/Image Retrieval Performance** 

Given the importance of accurately retrieving and presenting nontextual information, we conducted experiments specifically focused on the performance of image and table retrieval. For this, we assessed the capability of the system to correctly identify and include tables and images in the generated answers. 

We created 50 questions from the two test documents asking about specific images, and another 50 questions asking about specific tables. Image and table accuracy were measured by detecting whether the output of the system contains the correct image ID and table ID, respectively. We used our finetuned RAG-Llama3-70B model as the LLM agent in this experiment. 

In Table 3, our PIER-QA system achieved considerable accuracies for image and table retrieval, at 65.66% and 48.38%, respectively. The results demonstrate the reliability of our approach in handling complex document structures with not only text but also tables and images without the use of multimodal LLMs. 

|**Task**|**Accuracy**|
|---|---|
|Image retrieval|0.6566|
|Table retrieval|0.4838|
|Table 3: Table/Image|Retrieval Performance|
