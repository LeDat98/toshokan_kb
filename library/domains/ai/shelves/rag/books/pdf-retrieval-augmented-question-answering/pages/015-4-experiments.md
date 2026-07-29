---
id: nd_01KXJ4A5Q5CMB4E1Q50SRFPCNX
title: 4 Experiments
source_ref: abcxyz.pdf
---

## **4 Experiments** 

### **4.1 Data Collection** 

Our dataset consists of 8 private internal documents from a production company. We used 6 of them for finetuning our model as described in Section 3, leaving the rest for testing. From the test documents, we constructed a test set by manually prompting GPT-4o to generate questions and answers based on some specific contexts, resulting in 100 question-answer pairs. The question covers a wide range of topics and formats involving text, images, tables to assess the system’s performance effectively. 

### **4.2 Metrics** 

We employed several metrics to measure the effectiveness of our system. **Similarity** between the generated answers and the gold standard answers was assessed using embeddings from the GTE-large 

6 

model. Additionally, we used accuracy at different thresholds - **accuracy@0.85** , **accuracy@0.9** and **accuracy@0.95** to evaluate the precision of the system. An answer is considered correct if its similarity score exceeds the given threshold score. These metrics provide a nuanced view of the system’s performance.
