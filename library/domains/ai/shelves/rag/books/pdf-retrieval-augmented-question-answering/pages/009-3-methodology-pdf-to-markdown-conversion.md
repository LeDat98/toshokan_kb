---
id: nd_01KXJ49RBZK3GZ2ZRDKK1KPQBE
title: 3 Methodology — PDF to Markdown conversion
source_ref: abcxyz.pdf
---

### **PDF to Markdown conversion** 

This step employs Marker (Venkatramana, 2023), a software utility tool designed for identifying and extracting various types of content from pdf documents helps in extracting and saving images along with markdown text and utilizes models wherever necessary to enhance speed and accuracy. We convert the cleaned document to markdown format including text _T_ , image _I_ , and tables _τ_ : 



4 

**Algorithm 1:** Header/Footer Removal Algorithm 

**1** Initialize DBSCAN parameters: **2** minPts: minimum number of points to form a dense region **3** eps: maximum distance between two points to be considered neighbors **4** Load PDF document **5** Extract text elements with spatial coordinates (x, y); **6** Cluster text elements using DBSCAN: **7** clusters = DBSCAN(text_elements, eps, minPts) **8 for** _each cluster in clusters:_ **do 9** Calculate cluster centroid **10 if** _centroid is near the top or bottom of the page:_ **then 11** Mark cluster as header or footer **12 else 13** Mark cluster as main content **14 end 15 end 16 for** _each page in PDF:_ **do 17** Remove text elements marked as header or footer **18 end 19** Save the modified PDF document 

In image extraction, Marker detects images, diagrams, graphs and optimizes them, resulting in smaller files which facilitates the extraction of images from PDFs for subsequent steps by generating a markdown file including image file name and URLs. The full configurations for Marker are described in Appendix C.
