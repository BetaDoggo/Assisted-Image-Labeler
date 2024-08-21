# Assisted Image Labeler
A WIP personal tool for cleaning my lora datasets. I wanted a tool to make hand labeling faster while also allowing quick access to ml tagging tools. Supports a few different models for tagging. Most model support is through apis right now but I'll add support for more local options in the future. Batch processing is supported but it will not be as fast as a dedicated captioner doing several images at once. 
# Install
1. `pip install -r requirements`
2. `python labeler.py`
# Model Support
Via api:
  
1. Florence 2 Large
2. moondream 2 / moondream 2 docci
3. LLaVA1.5 13B
4. LLaVA1.6 34B
5. Some random openrouter llms for rephrasing

Local / built-in:

1. wd-tagger series
# Preview
![preview](https://github.com/BetaDoggo/Assisted-Image-Labeler/blob/main/Preview.png)
