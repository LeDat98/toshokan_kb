---
id: nd_01KXJ49YYEVS4ZHR9PCXZ41R5Z
title: 3 Methodology — RAG-Aware LLM Finetuning
source_ref: abcxyz.pdf
---

### **RAG-Aware LLM Finetuning** 

To make the LLM adapt to the document domain as well as being aware of our Markdown format, image, and table structure, we trained RAG-Llama3-70B using a systematic process. We applied the same preprocessing steps of our system for training PDF documents, and then split the text into chunks of 5000 characters each. Using GPT-4, we generated relevant and comprehensive questions for each context chunk. These questions, along with their respective context, were fed back into GPT-4 to generate detailed answers, resulting to approximately 2000 question-answer pairs. To reflect the inference scenario where 10 chunks of 1000 characters were retrieved and appended to the prompt, we split the original context into five 1000-character chunks, mixed randomly with additional five 1000-character chunks from other documents, and appended as context to the question. The prompt details can be found in Appendix A. This also helps enhance robustness of the model on assessing relevance of the retrieved context. We finetune Llama3-70B-Instruct Grattafiori et al. [2024] with Low-Rank Adaptation (LoRA) Hu et al. [2021] over 2 epochs, batch size of 8 and learning rate of 0.00008. All training hyperparameters can be found in Appendix D. The training took 8 hours on a single A100 80GB.
