# 项目开发规则 — Stock Screener

## 第三方库：先查源码，不猜参数

在使用任何第三方库的参数（尤其是枚举、常量、配置名）之前，必须：
1. `pip show <package>` 确认安装路径
2. 打开源码中的 `__init__.py` / `shared.py` / 主模块，搜索参数名
3. 确认有效值列表或枚举定义
4. 用确认后的值修改代码

**禁止行为：** 凭记忆或猜测填写参数值，失败后换一个继续猜。

## streamlit-aggrid 关键事实

| 项目 | 值 |
|------|-----|
| 版本 | 1.2.1 |
| 源码路径 | `Python313/Lib/site-packages/st_aggrid/` |
| 有效 theme | `streamlit` / `alpine` / `balham` / `material` |
| 默认 theme | `streamlit`（自适应 Streamlit 暗色模式） |
| 无效值行为 | **不报错**，静默回退到浅色默认样式 |
| CSS 类名 | `.ag-theme-streamlit` 等 |
| 推荐使用 | `theme='streamlit'` |
| 排序/筛选免刷新 | `update_on=[]` |

## 修改代码的验证标准

- 修改后必须通过 `python -c "import py_compile; py_compile.compile('<file>', doraise=True)"` 
- 如果一个修改 2 次推送后用户反馈仍无效 → 停手，查源码诊断根因
- CSS 选择器不确定时 → 删除自定义，用库默认样式

## Known Issues

- streamlit-aggrid `AgGrid.py:305-308` 存在验证漏洞：`theme` 字符串不校验枚举值
- 文档注释 (`AgGrid.py:147-155`) 和实际枚举 (`shared.py:206-210`) **不一致** — 文档列出 `light/dark/blue/fresh`，枚举是 `streamlit/alpine/balham/material`
