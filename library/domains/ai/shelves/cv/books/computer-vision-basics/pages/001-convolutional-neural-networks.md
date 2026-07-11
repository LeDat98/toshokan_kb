---
id: nd_01KX80W62ZX68MW4002EVF6WPJ
title: Convolutional Neural Networks
source_ref: seed
---

CNNs exploit two image priors: locality and translation invariance. A convolution
layer slides small learned filters over the image, producing feature maps; pooling
downsamples them, growing the receptive field. Stacked layers form a hierarchy —
early filters detect edges and textures, deeper ones detect parts and objects.

Weight sharing makes CNNs far more parameter-efficient than dense networks on
images. Residual connections (ResNet) enabled very deep stacks by letting gradients
flow through identity paths. Vision transformers now rival CNNs at scale, but CNNs
remain strong when data or compute is limited.
