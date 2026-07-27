---
title: GPT-4v 上传本地图片报错解决方案
date: 2024-05-19 00:15:23
tags:
- GPT-4v
- api error
- fail to decode image config
---

# GPT-4v 上传本地图片报错解决方案 "fail to decode image config(webp)"
#### 问题描述
如题，博主在使用OpenAI api调用gpt-4-vision-preview时出现如下报错信息：
`
'error': {'message': 'fail to decode image config(webp): riff: missing RIFF chunk header (request id: xxxxxxx)', 'type': 'new_api_error', 'param': '', 'code': 'count_token_messages_failed'}
`

经排查发现问题是因为上传的图片格式(bmp)不支持。目前OpenAI支持的图片格式有：`JPEG`, `JPG`, `PNG`, `WEBP`, (非动图的)`GIF`。

#### 解决方案
要向GPT api上传本地图片，需要使用base64先进行编码，参考[openai document](https://platform.openai.com/docs/guides/vision/uploading-base-64-encoded-images)
如果本地图片格式不在支持范围内，需要先进行转化，修改后的encode代码如下：
```python
import base64
from PIL import Image
from io import BytesIO

def encode_image(image_path):
    """convert image to jpeg and encode with base64"""
    img = Image.open(image_path).convert("RGB")
    im_file = BytesIO()
    img.save(im_file, format="JPEG")
    im_bytes = im_file.getvalue()  # im_bytes: image in binary format.
    return base64.b64encode(im_bytes).decode('utf-8')
```
然后按文档传入`image_url`中对应位置即可。

示例：
```python
base64_image = encode_image(image_filename)
response = client.chat.completions.create(
    model="gpt-4-vision-preview",
    messages=[
        {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {"type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "low"},
            }
        ],
        }
    ],
    max_tokens=300
)
answer = response.choices[0].message.content
```

以上。