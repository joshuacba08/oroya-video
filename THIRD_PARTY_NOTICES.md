# Third-party notices

Oroya Video includes or downloads the following third-party components. The rest of the
dependencies (Python and npm packages) are installed from their registries under their own
licenses.

## Source code included in this repository

### RIFE 4.25 network (`backend/app/enhancers/rife/`)

`IFNet_HDv3_v4_25.py` and `warplayer.py` come unmodified from
[HolyWu/vs-rife](https://github.com/HolyWu/vs-rife), which is based on
[hzwer/Practical-RIFE](https://github.com/hzwer/Practical-RIFE). Both are under the MIT
License:

```
MIT License

Copyright (c) 2021 HolyWu
Copyright (c) 2020 hzwer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Model weights downloaded on demand

These files are not part of the repository or the installer. They are downloaded from the Models
page and checked against a pinned SHA-256 (`backend/app/services/model_download_service.py`).

| Model | Source | License |
| --- | --- | --- |
| Real-ESRGAN x2 / x4 / general | [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | BSD-3-Clause |
| GFPGAN v1.4 | [TencentARC/GFPGAN](https://github.com/TencentARC/GFPGAN) | See the project's LICENSE (Apache-2.0 with third-party terms) |
| facexlib detection/parsing | [xinntao/facexlib](https://github.com/xinntao/facexlib) | MIT |
| RIFE 4.25 (`flownet_v4.25.pkl`) | [HolyWu/vs-rife](https://github.com/HolyWu/vs-rife/releases/tag/model), trained by [hzwer/Practical-RIFE](https://github.com/hzwer/Practical-RIFE) | MIT |

## Tools

FFmpeg is not bundled: Setup downloads the Windows build from
[GyanD/codexffmpeg](https://github.com/GyanD/codexffmpeg) (or uses one already installed) and runs
it as a separate program. FFmpeg is licensed under the LGPL/GPL; see https://ffmpeg.org/legal.html.
