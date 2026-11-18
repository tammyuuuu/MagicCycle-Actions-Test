# 微软 FY27 Q2 预测登记

登记日为 2026-11-18（北京时间）。截至登记日，微软最新季报为 2026-10-28 公布、截至 2026-09-30 的 FY27 Q1。预测期为截至 2026-12-31 的 FY27 Q2，状态为待核验。[微软投资者关系主页](https://www.microsoft.com/en-us/investor/default)｜[Q1 财报及固定汇率对照表](https://www.microsoft.com/en-us/investor/earnings/fy-2027-q1/press-release-webcast)

## 第三方算力交付推迟，Azure 还能加速吗？

预测 FY27 Q2 的 **Azure 收入按固定汇率同比增长 49%**。简单外推沿用 Q1 同口径的 48%，两者差 1 个百分点。选择这个指标，是因为供给受限时，能否用现有设备承接更多付费工作负载会影响收入兑现。盈利还取决于业务组合。Q1 Azure 自身毛利率改善，但 Azure 占比上升仍使 Microsoft Cloud 整体毛利率同比下降至 66%。[Q1 财报](https://www.microsoft.com/en-us/investor/earnings/fy-2027-q1/press-release-webcast)｜[业绩会，Amy Hood 对云毛利率的说明](https://www.microsoft.com/en-us/investor/events/fy-2027/earnings-fy-2027-q1)

**支持加速的证据。** CFO 在回答 Karl Keirstead 时说明，Q1 的平台优化已释放现有设备容量，使公司能增加 Foundry 的资源分配；部分效率收益会延续到 Q2。管理层称需求仍超过供应，给出 Q2 Azure 固定汇率增速 49%–50% 的指引。[Q1 业绩会，分部展望及问答](https://www.microsoft.com/en-us/investor/events/fy-2027/earnings-fy-2027-q1)

**反证与取值。** 原计划 Q2 交付的部分第三方 GPU 服务合同已推迟至下半财年。CFO 也表示，实现指引还需取得新的效率提升，而 Q1 的 token 定价高于预期，Q2 价格仍有变数。因此取指引下沿 49%。这些交付风险在管理层给出指引时已经知晓；本次检验的是采用指引下沿能否胜过持平外推，单次命中不足以证明具有独立预测能力。[Q1 业绩会，CFO 回答 Karl Keirstead](https://www.microsoft.com/en-us/investor/events/fy-2027/earnings-fy-2027-q1)

## 核验约定

使用微软 FY27 Q2 首次正式披露的 Azure revenue 同比增速，取 constant currency 列及其公布精度。设实际值为 A（百分数），分别记录 |A−49| 和 |A−48|，单位为百分点。实际值等于 49 即点预测命中；A 大于 48.5 则研究预测误差更小，等于 48.5 平局，小于 48.5 则外推胜。另记 A 是否高于 48，以区分方向与点位。披露后追加发布日期、官方链接、实际值及两项误差。若指标缺失或重分类且无可比值，记为无法判定，保留原预测。[Q1 官方指标表，用于比对口径](https://www.microsoft.com/en-us/investor/earnings/fy-2027-q1/metrics)

## Actions 与模型的分工

- 已有设施：仓库的 `.github/workflows/manual.yml` 支持手动及工作日定时触发、运行 Python 和上传产物；`.github/workflows/tenbagger-audit.yml` 提供单独执行来源探测并上传审计产物的范例。
- 可复用这些步骤，另接小脚本检查微软 IR 是否发布新季报，按期末、指标名和汇率列提取数值，保存日期、URL 和原表快照，去重后计算基线与绝对误差。已有工作流执行的是市场检查或其他数据源探测，本次未接入微软抓取和评分，也未启动定时任务。
- 本次用模型完成开放式选题、从业绩会定位正反证、判断交付延迟是否已反映在指引中，并选择预测点。固定指标的抓取、归档和评分可完全由代码执行；披露口径变化时暂停评分，再由模型辅助复核定义及原文。
