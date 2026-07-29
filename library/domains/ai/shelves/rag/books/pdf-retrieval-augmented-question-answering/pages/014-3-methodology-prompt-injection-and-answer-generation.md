---
id: nd_01KXJ4A39607SJQAFFEHTMJ6JN
title: 3 Methodology — Prompt Injection and Answer Generation
source_ref: abcxyz.pdf
---

### **Prompt Injection and Answer Generation** 

The retrieved chunks are appended to the query in the prompt. The LLM then processes the prompt which now includes the user query and the injected chunks, to generate a response. The retrieved chunks _{cj_ 1 _, cj_ 2 _, ...cjk}_ are used as context to generate an answer _a_ using an LLM. The LLM is prompted with the query _q_ and the retrieved chunks: 



We prompt the model to include the image ID related to the answer from the retrieved context in a specific format, i.e., [image_1.png] for the later image recovery process. If the LLM answer contains image reference IDs, we retrieve the corresponding image from the database and display it to the user. In addition to handling images, if the LLM’s output includes dictionary-formatted tables, we extract and convert them back to markdown format for user display.
