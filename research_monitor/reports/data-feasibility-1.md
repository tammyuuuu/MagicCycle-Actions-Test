# 公开 DuckDB 2015 时点审计

## 文件与完整性

本地文件 1,001,402,368 字节，Get-FileHash SHA256 为 95601e2f1f5b62595a80e735a52da3a64c7446ebe7f8c984e3394b96f90e4778，与发布者 SHA256SUMS 一致；download.log 确认完成。database_inspection.txt 显示七表（security_master、bars、industry、adj_factors、trade_calendar、index_daily、etf_daily）。以 DuckDB 只读打开，各表所有列的 hash 聚合完整扫描成功（verify_duckdb_fullscan.py）；这支持文件可读及传输一致，不证明历史数据真实、来源合法或数据没有遗漏。数据仅本地。

## 时点及覆盖测试

以 security_master 的 list_date≤2015-12-31 且 delist_date 为空或晚于起点的机械过滤：2811 条，其中 SSE 1073、SZSE 1738；在 bars 当日都能连接，其中 tradestatus=1 为 2545、tradestatus=0 为 266。该池未区分暂停上市，不能把 2811 说成正式上市或可交易池，也不等于真实覆盖率。主键及当日行情键无重复。深交所 2015 年末 A 股官方统计为 1735 只（https://www.sz.gov.cn/cn/xxgk/zfxxgj/tjsj/tjgb/content/post_1333723.html），机械结果多 3，只能提示待对账；暂停上市、重上市、证券身份和口径差异均可能，尚未定位，不能推断覆盖率。上交所 1081 为上市公司数，不可直接与 1073 证券数比较。

证券 600240 后续退市，名单历史区间内可见，起点 15.05 与现有 CSMAR 单日预览一致；600519 起点 218.19 且 2016—2020 1218 个收盘价与本地 CSMAR 日价逐日完全相同，运行 crosscheck_snapshot_csmar.py 复核。000002、600690 起点 tradestatus=0，与其停牌公告一致；600656 状态亦为 0，但上交所确认该股自 2015-05-28 起暂停上市（https://www.sse.com.cn/regulation/supervision/dynamic/c/c_20240321_5736689.shtml），机械 IPO/退市区间会把暂停上市误列为上市成员。它们是个别一致或反例，不证明整体覆盖。

industry 在 2015-12-31 有 2889 行；上述 2811 机械池中 2800 行能关联，其中 12 个分类字符串为空，11 个无匹配，即 2788/2811 非空（99.18%，这是机械池中的字段非空率，不是正确率）。同期 2889 个行业行中 89 个证券主表记载已于 2015-12-31 前退市，说明仅有快照日期不代表当时上市；需核验分类是否确为当时有效而非回填。历史身份存在明确时点风险：主表将 001872 和 001914 与 1993、1994 上市日连接，但官方公告分别表明它们由 000022 于 2018 年、000043 于 2019 年改码（https://static.cninfo.com.cn/finalpage/2018-12-26/1205690369.PDF ，https://static.cninfo.com.cn/finalpage/2019-12-20/1207179183.PDF）。没有独立历史代码有效期表，不能把现代码当 2015 代码，也不能把它们简单去重。股票名称和行业中文终端显示异常，未完成编码核查；分类准确性同样未通过。

schema 不含历史总股数或市值列；bars 的 volume/turn 不能无假设替代全部已发行股数或总市值。行业、市值分层所需 2015 时点总市值不能从本库直接取得，尚未连接已核验的历史股本来源。bars 的 pctChg 与 CSMAR 的现金红利再投资日回报口径不同：600519 在 2020-06-24 收盘两源均 1460.01，CSMAR Dretwd 0.001719，而本库 pctChg=0.1736（百分数），须明确定义后才比较；不能直接将其用作含红利总回报。

## 决策

不满足既定 200 只行业×市值分层随机抽样要求：历史证券代码/暂停上市有效期未可验证、深市数量有未解释差异、行业快照有效时点及历史分类不清、缺历史市值和股本。未经解决不冻结 200 名单，避免后视偏差及假分层。可将本库仅作为候选名单与价格对账来源，在本地补充交易所历史名称/代码及上市状态有效期、2015-12-31 或此前最近已知总股数和价格，并对深市 1738 vs 1735 逐项解释，验证行业值；通过后重新计算层与概率。可开展明确范围的案例和非代表性行业或价格序列敏感性研究，不能声称全市场覆盖或计算严格五年含红利收益。

复现：python tenbagger_research/verify_duckdb_fullscan.py；audit_snapshot.py；audit_snapshot_coverage.py；audit_snapshot_pit.py；crosscheck_snapshot_csmar.py。最后一项读取本地 CSMAR 授权样本，结果及数据库不得上传。来源说明 https://github.com/noblechang/a-share-data 仅声明学习研究用途，上游数据再分发许可仍未确认，不公开传播原始文件。
