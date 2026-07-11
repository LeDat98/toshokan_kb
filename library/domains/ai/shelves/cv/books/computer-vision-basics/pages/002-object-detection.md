---
id: nd_01KX80W63CDY1FCBKFC2GT652J
title: Object Detection
source_ref: seed
---

Detection outputs bounding boxes plus class labels. **Two-stage** detectors (Faster
R-CNN) first propose candidate regions, then classify and refine each — accurate but
slower. **One-stage** detectors (YOLO, SSD) predict boxes and classes in a single
dense pass — fast enough for real time, historically slightly less accurate on small
objects.

Two shared ingredients: **IoU** (intersection-over-union) measures box overlap for
matching and evaluation (mAP), and **NMS** (non-maximum suppression) removes
duplicate detections of the same object. Modern variants replace hand-tuned anchors
and NMS with end-to-end set prediction (DETR-style).
