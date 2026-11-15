# -*- coding: utf-8 -*-
"""独立补写器：不依赖 Web 服务，直接从记忆库把断掉的日期补齐。

看门狗启动时、每天各拉一次；也可以双击手动跑。
只补缺失的日期，不覆盖已有日记；内容全部来自 soul.db / memory_stream.db。
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, '大肥鱼服务端'))

import soul

made = soul.backfill_diary(7)
print('补写日期:', ', '.join(made) if made else '无缺口')
