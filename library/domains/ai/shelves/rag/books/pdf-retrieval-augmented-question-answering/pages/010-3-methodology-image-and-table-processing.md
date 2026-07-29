---
id: nd_01KXJ49TGYT5MMQPP3F2ZEWGQK
title: 3 Methodology — Image and Table Processing
source_ref: abcxyz.pdf
---

### **Image and Table Processing** 

One key improvement is generating captions to the images which alleviates image modality and turns the input into LLM’s native domain: text. This enhances the readability of markdown and improves the accuracy of the QA system by providing additional text information which can be indexed and retrieved. The image captioning in our project utilizes the LLaVA (Large Language and Vision Assistant) model, which is a fine-tuned version of the LLaMA/Vicuna model Liu et al. [2023b,a]. Every image in the markdown is given a unique ID (e.g.: image_1.png) and the generated captions include these references, ensuring that images are identified and described. During markdown conversion, tables are represented in markdown syntax initially which can be verbose and inefficient. To enhance this, we compress markdown tables as dictionary format for efficient storage, reducing the storage space leading to easier data access, understanding and manipulation.
