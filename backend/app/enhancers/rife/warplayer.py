# Vendored from HolyWu/vs-rife (https://github.com/HolyWu/vs-rife), file vsrife/warplayer.py,
# itself based on hzwer/Practical-RIFE (https://github.com/hzwer/Practical-RIFE).
# Both MIT licensed:
#
#   Copyright (c) 2021 HolyWu
#   Copyright (c) 2020 hzwer
#
#   Permission is hereby granted, free of charge, to any person obtaining a copy of this
#   software and associated documentation files (the "Software"), to deal in the Software
#   without restriction, including without limitation the rights to use, copy, modify, merge,
#   publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
#   to whom the Software is furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in all copies or
#   substantial portions of the Software.
#
#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#   INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#   PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
#   FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#   OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#   DEALINGS IN THE SOFTWARE.
#
# Unmodified apart from this header. See THIRD_PARTY_NOTICES.md.
# ruff: noqa

import torch
import torch.nn.functional as F


def warp(tenInput, tenFlow, tenFlow_div, backwarp_tenGrid):
    dtype = tenInput.dtype
    tenInput = tenInput.to(torch.float)
    tenFlow = tenFlow.to(torch.float)

    tenFlow = torch.cat([tenFlow[:, 0:1] / tenFlow_div[0], tenFlow[:, 1:2] / tenFlow_div[1]], 1)
    g = (backwarp_tenGrid + tenFlow).permute(0, 2, 3, 1)
    return F.grid_sample(input=tenInput, grid=g, mode="bilinear", padding_mode="border", align_corners=True).to(dtype)
