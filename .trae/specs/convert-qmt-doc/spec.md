# QMT HTML 转换为 Markdown 接口文档 Spec

## Why
用户将 QMT (XtQuant.XtData 行情模块) 的网页文档保存为 HTML 文件，需要将其转换为类似 TDX.md 风格的 Markdown 接口文档，方便阅读和查阅。

## What Changes
- 将 `QMT.html` 中的全部接口文档内容转换为 Markdown 格式，输出为 `QMT.md`
- 保留原始 HTML 中的格式结构（函数签名、参数说明、返回值、备注等）
- 参照 `TDX.md` 的文档风格进行排版
- 去除 HTML 标签、CSS 样式、Vue 组件属性等无关内容
- 保留所有代码示例（转为 Markdown 代码块）
- 保留所有数据字段列表（转为 Markdown 代码块或表格）

## Impact
- Affected code: 新增 `QMT.md` 文件
- 不影响任何现有代码

## ADDED Requirements

### Requirement: 生成 QMT.md 文档
系统 SHALL 将 QMT.html 中的接口文档内容完整转换为 Markdown 格式的 QMT.md 文件。

#### Scenario: 文档结构完整性
- **WHEN** 转换完成
- **THEN** QMT.md 应包含以下所有章节：
  1. 模块概述（XtQuant.XtData 行情模块介绍）
  2. 接口概述（运行逻辑、接口分类、常用类型说明、请求限制）
  3. 行情接口（订阅/反订阅/获取/下载等全部接口）
  4. 财务数据接口
  5. 基础行情信息（合约信息、板块操作等）
  6. 附录（行情数据字段列表、数据字典、财务数据字段列表、合约信息字段列表）

#### Scenario: 接口格式一致性
- **WHEN** 每个接口被转换
- **THEN** 每个接口应包含：函数签名（代码块）、释义、参数说明、返回值说明、备注

#### Scenario: 代码块格式
- **WHEN** HTML 中的代码被转换
- **THEN** 应使用 ```python 或 ```text 的 Markdown 代码块格式

#### Scenario: 数据字段列表
- **WHEN** 行情数据字段、财务数据字段、合约信息字段被转换
- **THEN** 应保留原始的 Python 注释格式（`'field' #说明`）
