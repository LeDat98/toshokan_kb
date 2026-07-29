---
id: nd_01KXJ4AEXXGH383K4FPVZSG6GP
title: A Training data generation prompts
source_ref: abcxyz.pdf
---

## **A Training data generation prompts** 

The data generation consists of two steps: question generation and answer generation. We split the preprocessed training documents into chunks (note that these chunks are longer than the retrieved chunks during inference) and put them into the ‘context’ slot of the question generation prompt as shown in Figure 3. 



Figure 3: Question generation prompt 

11 

In the next step, we put generated questions and their corresponding context into answer generation template (Figure 4), resulting to question-answer pairs for the given context. The instruction in this template is also used for training and inference. 



Figure 4: Answer generation prompt
