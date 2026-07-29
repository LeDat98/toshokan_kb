---
id: nd_01KXJ4AH2NFSK06JFRDTS8HVWV
title: B DBSCAN hyperparameter details
source_ref: abcxyz.pdf
---

## **B DBSCAN hyperparameter details** 

DBSCAN hyperparameter values were selected based on empirical analysis to balance the precision and recall of header/footer removal. 

- _min_  samples_ : This parameter represents the minimum number of samples in a neighborhood for a point to be considered as a core point. The value is dynamically set based on the number of pages in the PDF document: 

   - For documents with 6 pages or fewer: _min_  samples_ = 2 

   - For documents with 7 to 8 pages: _min_  samples_ = 3 

   - For documents with more than 8 pages: _min_  samples_ = 4 

This dynamic adjustment helps in better identification of headers and footers across documents of varying lengths. 

- _eps_ (epsilon): This parameter defines the maximum distance between two samples for one to be considered as in the neighborhood of the other. A smaller value of ‘0.01‘ is chosen to ensure that only closely located text blocks (typically headers and footers) are clustered together.
