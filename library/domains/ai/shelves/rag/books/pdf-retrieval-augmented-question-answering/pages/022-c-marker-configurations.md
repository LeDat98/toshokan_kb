---
id: nd_01KXJ4AK84TNNK68J2K2409KSP
title: C Marker configurations
source_ref: abcxyz.pdf
---

## **C Marker configurations** 

The Marker tool in our PDF processing pipeline is responsible for extracting and handling various types of content from PDFs, including text, images, and layouts. By default, it uses the ‘Surya’ OCR engine for efficient and accurate text recognition. The tool is configured to run OCR on all pages of a PDF, even if some text can be directly extracted, ensuring comprehensive text recognition across the entire document. 

In addition to text recognition, the Marker tool employs advanced models for layout detection and text ordering, such as the Texify model. A post-processing model further refines the data by applying a probability threshold to ensure only high-confidence predictions are retained, reducing errors and enhancing the overall quality of the output. The full settings for Marker can be found in 4.
