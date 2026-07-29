---
id: nd_01KXJ4ANDYBHY8WWX9NSQBWYWH
title: D Llama3 training hyperparameters
source_ref: abcxyz.pdf
---

## **D Llama3 training hyperparameters** 

We provide the full list of training hyperparameters for our RAG-Llama3-70B in Table 5. 

12 

|**Parameter**|**Default**|**Description**|
|---|---|---|
|IMAGE_DPI|96|DPI for renderingimages from PDFs.|
|EXTRACT_IMAGES|TRUE|Whether to extract images from PDFs.|
|PAGINATE_OUTPUT|FALSE|Whether topaginate the output markdown.<br>|
|DEFAULT_LANG|English|Default language for OCR, should match a key<br>in TESSERACT_LANGUAGES.|
|DETECTOR_BATCH_SIZE|None|Batch size for text line detection. Defaults to 6<br>for CPU,12 otherwise.|
|SURYA_DETECTOR_DPI|96|DPI for the Surya detector.|
|INVALID_CHARS|[chr(0xfffd)]|Characters to ignore duringOCR.|
|OCR_ENGINE|"surya"|OCR engine to use, defaults to "surya" on GPU<br>and "ocrmypdf" on CPU.|
|OCR_ALL_PAGES|FALSE|Whether to run OCR on every page even if text<br>can be extracted.|
|SURYA_OCR_DPI|96|DPI for Surya OCR.<br>|
|RECOGNITION_BATCH_SIZE|None|Batch size for Surya OCR, defaults to 64 for<br>CUDA,32 otherwise.|
|TESSERACT_TIMEOUT|20|Timeout for Tesseract OCR.|
|TEXIFY_MODEL_MAX|384|Max inference length for Texify.|
|TEXIFY_TOKEN_BUFFER|256|Number of tokens to buffer above max for<br>Texify.|
|TEXIFY_DPI|96|DPI for renderingimages in Texify.|
|TEXIFY_BATCH_SIZE|None|Batch size for Texify, defaults to 6 for CUDA,<br>12 otherwise.|
|TEXIFY_MODEL_NAME|"vikp/texify"|Name of the Texifymodel.|
|SURYA_LAYOUT_DPI|96|DPI for Surya layout.|
|BAD_SPAN_TYPES|["Caption", "Footnote",<br>"Page-footer", "Page-header",<br>"Picture"]|Types of spans to consider as bad spans.|
|LAYOUT_MODEL_CHECKPOINT|"vikp/surya_layout3"|Checkpoint for the layout model.|
|BBOX_INTERSECTION_THRESH|0.7|Threshold for boundingbox intersection.<br>|
|LAYOUT_BATCH_SIZE|None|Batch size for layout model, defaults to 12 for<br>CUDA,6 otherwise.|
|SURYA_ORDER_DPI|96|DPI for Surya ordering.<br>|
|ORDER_BATCH_SIZE|None|Batch size for ordering model, defaults to 12<br>for CUDA,6 otherwise.|
|ORDER_MAX_BBOXES|255|Maximum number of boundingboxes for ordering.|
|EDITOR_BATCH_SIZE|None|Batch size for fnal editing model, defaults to<br>6 for CUDA,12 otherwise.|
|EDITOR_MAX_LENGTH|1024|Maximum length for the fnal editingmodel.|
|EDITOR_MODEL_NAME|"vikp/pdf_postprocessor_t5"|Name of the fnal editingmodel.|
|ENABLE_EDITOR_MODEL|FALSE|Whether to enable the fnal editingmodel.<br>|
|EDITOR_CUTOFF_THRESH|0.9|Probability threshold to ignore predictions below<br>this value.|



Table 4: All Marker configurations 

13 

|**Parameter**|**Value**|**Description**|
|---|---|---|
|load_in_8bit|FALSE|Indicates whether to load the model in 8-bitprecision.|
|load_in_4bit|TRUE|Indicates whether to load the model in 4-bitprecision.|
|adapter|qlora|Specifes the adapter type to use,in this case, QLoRA.|
|sequence_len|6000|Maximum sequence length for training.|
|sample_packing|TRUE|Enables effcient multi-packing with block diagonal<br>attention andper sequenceposition_ids.|
|pad_to_sequence_len|TRUE|Pads inputs to ensure each step uses constant-sized<br>buffers,reducingmemoryfragmentation.|
|lora_r|8|Rank of the low-rank adaptation matrices in LoRA.|
|lora_alpha|16|Scalingfactor for LoRA.|
|lora_dropout|0.05|Dropout rate for LoRA layers.|
|lora_target_linear|TRUE|Indicates whether to target all linear modules in LoRA.|
|gradient_accumulation_steps|4|Number of steps to accumulate gradients before<br>updatingmodel weights.|
|micro_batch_size|2|Number of samples in each micro-batch.|
|num_epochs|2|Number of epochs to train the model.|
|optimizer|adamw_bnb_8bit|Optimizer used for training, in this case, AdamW<br>with 8-bitprecision.|
|lr_scheduler|cosine|Learningrate scheduler type,in this case,cosine annealing.|
|learning_rate|8.00E-06|Learningrate for training.|
|train_on_inputs|FALSE|Indicates whether to include the human’s prompt in<br>the traininglabels.|
|group_by_length|FALSE|Whether togroupdata bylength to minimizepadding.|
|bf16|auto|Use bf16precision if available.|
|gradient_checkpointing|TRUE|Enablesgradient checkpointingto save memory.|
|logging_steps|20|Frequencyof loggingtraining progress.|
|fash_attention|TRUE|Enables fash attention for improvedperformance.|
|warmup_steps|20|Number of steps for learningrate warmup.|
|evals_per_epoch|5|Number of evaluations toperformper epoch.|
|saves_per_epoch|3|Number of times to save checkpointsper epoch.|



Table 5: All training hyperparameters. 

14
