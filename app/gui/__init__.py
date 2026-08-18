# -*- coding: utf-8 -*-
"""GUI 层（PySide6）：主窗口、后台线程、结果视图、对话框、纯展示层。

模块划分（见 ARCHITECTURE.md §7）：
    main_window    —— 主窗口：文件选择 / 参数 / 运行 / 汇总 / 导出
    worker         —— QThread 后台执行 pipeline + 输出
    result_view    —— QTableView + model，未挂靠行高亮
    dialogs        —— 错误 / 信息弹窗
    presentation   —— 纯展示函数（格式化 / 表格行 / 详情），无 Qt 依赖可单测
"""
