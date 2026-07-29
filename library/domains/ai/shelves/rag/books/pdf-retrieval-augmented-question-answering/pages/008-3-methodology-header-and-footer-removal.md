---
id: nd_01KXJ49NXV4TPJ7WPJCSSPCNX9
title: 3 Methodology — Header and footer removal
source_ref: abcxyz.pdf
---

### **Header and footer removal** 

The removal of headers and footers is an important preprocessing step as they could interfere with the retrieval process by adding noise to the data which leads to less accurate results. Thus, by removing headers and footers, we obtain reliable cleaned pdf documents for further processing. We make an assumption that headers and footers coordinates are consistent across pages, i.e., at the top and bottom of the page, therefore by detecting this repeating pattern we will be able to remove headers and footers. As shown in Figure 2, we employ DBSCAN (Density-Based Spatial Clustering of Applications with Noise) which is well known for identifying areas of high density Fahim [2022]. We use DBSCAN to cluster the bounding box of PDF elements, then remove the most frequent clusters across pages (marked by red boxes) while keeping the rest (blue boxes). We also notice the pattern can slightly varies, especially on long documents, therefore we apply the algorithm on each 10 pages instead of the entire document at once. Let _Di_ be a PDF document. We denote the preprocessed version of _Di_ as _D_<sup>ˆ</sup> _i_ , the preprocessing involves: 



The implementation of DBSCAN clustering involves several key steps as shown in algorithm 1. Initially, the PDF parsing library extracts the bounding boxes of all elements on each page, including text blocks, images, drawings, and other graphical elements. These bounding boxes are then used as input for the DBSCAN algorithm, which clusters them based on their spatial proximity. More details of DBSCAN hyperparameters can be found in Appendix B.
