# Bursa Sector Classification Update

## 背景

Yahoo Finance 的 `assetProfile.sector/industry` 使用 GICS 分类，与 Bursa Malaysia
官方的行业分类不一致。例如几乎所有油棕种植园公司都被 Yahoo 归为
`Consumer Defensive / Farm Products`，导致这些股票在 Screener 里被错误归类，
进而污染 sector strength 和 sector-relative-strength 的计算。

项目已有 `tickers/sector_map.csv` 手写覆盖表，但只覆盖了约 170 只股票，
不足以修正全部 universe。

## 数据源

本次更新使用 klsescreener (https://www.klsescreener.com) 的完整上市公司筛选表
(`/v2/screener/quote_results`)，它提供**每只 Bursa 上市股票对应的官方行业**
(Bursa 官方 14 类行业，精确到子行业 + 市场)。该数据作为权威来源，再结合：

1. 原有手写 `sector_map.csv`（保留所有旧条目，0 删除）
2. 对当日停牌/暂停交易、不在筛选表中的 39 只股票，用可靠业务知识补充

## 规范

- 全部行业词统一为大写，与原有手写表一致（例如 `PLANTATION`、`TECHNOLOGY`）。
  `screener_rs.py` 把 sector 字符串作为分组键（dict/groupby），因此大小写必须一致，
  否则同一行业会被拆成两个不同行业。
- 输出格式保持 `CODE,SECTOR`，兼容现有的 `load_sector_override()` /
  `apply_sector_override()`，无需改动任何代码。

## 变更统计

| 项目 | 数量 |
|---|---|
| 原 `sector_map.csv` 行数 | 169 |
| 新 `sector_map.csv` 行数 | 1006 |
| 新增（新覆盖） | 837 |
| 删除 | 0 |
| 值被修正 | 39 |
| 未覆盖（universe 缺失） | 0 |

## 关键修正示例（种植股）

以下股票此前被 Yahoo 归为 `Consumer Defensive / ...`，现已全部正确归为 `PLANTATION`：

| 代码 | 名称 |
|---|---|
| 1961 | IOI Corporation |
| 2445 | Kuala Lumpur Kepong |
| 2089 | United Plantations |
| 2291 | Genting Plantations |
| 5285 | SD Guthrie |
| 5138 | Hap Seng Plantations |
| 9059 | TSH Resources |
| 5135 | Sarawak Plantation |
| 5026 | MHC Plantations |
| 5069 | BLD Plantation |
| 5112 | TH Plantations |
| 9695 | PLS Plantations |
| 6262 | Innoprise Plantations |
| 2453 | KLUANG Rubber (老表误标为 REIT，现修正) |
| 5222 | FGV Holdings |
| 5254 | Boustead Plantations |
| 4936 | Malpac Holdings |
| 2038 | Negri Sembilan Oil Palms (老表误标 ENERGY) |
| 5126 | Sarawak Oil Palms (老表误标 ENERGY) |
| 1902 | Pinehill Pacific |

## 39 处值修正清单（原始手写表 vs 官方分类）

 | 代码 | 公司 | 旧值 | 新值 |
 |---|---|---|---|
 | 0011 | BRITE-TECH | TECHNOLOGY | UTILITIES |
 | 0017 | NOVATECH | TECHNOLOGY | TELECOMMUNICATIONS & MEDIA |
 | 0032 | REDTONE | TECHNOLOGY | TELECOMMUNICATIONS & MEDIA |
 | 0080 | STRAITS ENERGY | ENERGY | TRANSPORTATION & LOGISTICS |
 | 0084 | FAST ENERGY | ENERGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 0089 | TEX CYCLE | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 0092 | MTOUCHE | TECHNOLOGY | TELECOMMUNICATIONS & MEDIA |
 | 0100 | ES CERAMICS | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 0118 | TRIVE | PROPERTY | ENERGY |
 | 0123 | PRINCIPAL FTSE ASEAN 40 | TECHNOLOGY | TELECOMMUNICATIONS & MEDIA |
 | 0133 | SANICHI | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 0148 | SUNZEN BIOTECH | HEALTH CARE | CONSUMER PRODUCTS & SERVICES |
 | 0173 | CATCHA | TECHNOLOGY | TELECOMMUNICATIONS & MEDIA |
 | 0240 | CORAZA | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 0261 | COSMOS | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 0281 | DAYTHREE | TECHNOLOGY | CONSUMER PRODUCTS & SERVICES |
 | 2038 | NEGRI SEMBILAN OIL PALMS | ENERGY | PLANTATION |
 | 2453 | KLCC PROPERTY → 实际 KLUANG | REAL ESTATE INVESTMENT TRUSTS | PLANTATION |
 | 3024 | CE TECHNOLOGY | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 3719 | PANASONIC MANUFACTURING | INDUSTRIAL PRODUCTS & SERVICES | CONSUMER PRODUCTS & SERVICES |
 | 5015 | APM AUTOMOTIVE | CONSUMER PRODUCTS & SERVICES | INDUSTRIAL PRODUCTS & SERVICES |
 | 5126 | SARAWAK OIL PALMS | ENERGY | PLANTATION |
 | 5149 | TAS OFFSHORE | ENERGY | TRANSPORTATION & LOGISTICS |
 | 5183 | PETRONAS CHEMICALS | ENERGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 5186 | MALAYSIA MARINE & HEAVY | INDUSTRIAL PRODUCTS & SERVICES | ENERGY |
 | 5209 | GAS MALAYSIA | ENERGY | UTILITIES |
 | 5317 | CPE TECHNOLOGY | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 5681 | PETRONAS DAGANGAN | ENERGY | CONSUMER PRODUCTS & SERVICES |
 | 5703 | MUHIBBAH ENGINEERING | INDUSTRIAL PRODUCTS & SERVICES | CONSTRUCTION |
 | 6033 | PETRONAS GAS | ENERGY | UTILITIES |
 | 6971 | KOBAY TECHNOLOGY | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 7033 | KUMPULAN H&L HIGH-TECH | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 7036 | BORNEO OIL | ENERGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 7055 | PLB ENGINEERING | INDUSTRIAL PRODUCTS & SERVICES | PROPERTY |
 | 7087 | MAGNI-TECH | TECHNOLOGY | CONSUMER PRODUCTS & SERVICES |
 | 7172 | PMB TECHNOLOGY | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 7233 | DUFU TECHNOLOGY | TECHNOLOGY | INDUSTRIAL PRODUCTS & SERVICES |
 | 7237 | POWER ROOT | UTILITIES | CONSUMER PRODUCTS & SERVICES |
 | 8532 | PERTAMA DIGITAL | TECHNOLOGY | CONSUMER PRODUCTS & SERVICES |

## 影响与验证

- `screener_rs.load_sector_override()` / `apply_sector_override()` 逻辑未改动。
- `run_phase1_screener()` 端到端验证：传入 Yahoo 错误的
  `sector_map = {"9059.KL": "Consumer Defensive"}`，输出 sector = `PLANTATION`，
  并正确参与 sector_strength 计算。
- 62 个现有测试全部通过。

## 备份

原文件以 `tickers/sector_map.csv.bak` 保留，可随时还原。
