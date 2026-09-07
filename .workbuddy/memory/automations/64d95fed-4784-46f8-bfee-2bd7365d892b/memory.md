# 自动化执行摘要：补生成 2026-09-07 矿业日报

- 触发：index.html 被 09:00 卡死任务写成脏版本（今日新增 marker 重复 18 处）。
- 关键发现：**提交的 HEAD（8061f65 / build 20260907-0013）本身即含 18 处重复 `<!-- 今日新增（2026-09-06 抓取） -->` 注释**，故 `git checkout -- index.html` 无法还原干净基线（HEAD 就是脏的，不是工作树脏）。
- 处理：手工删除 18 处重复 marker（保留 canon `<!-- 今日新增 -->`），preflight 通过；再用 generate_20260907.py 重建。
- 修复 generate_20260907.py 两处缺陷：
  ① 重建边界从 installGuideSection div 改为 rightsSection，避免误删矿权专区容器与「详细安装指引」注释 marker；
  ② 生成后移除 canon 今日新增注释（`<!-- 今日新增 -->`），最终仅留 1 个 `今日新增（2026-09-07 抓取）` marker（preflight 要求各 marker 恰好 1 个）。
- 结果：今日 9 / 往期 37 / 合计 46；矿权仅入数据层（主列表 0 条 ky.mnr.gov.cn）；价格两行（SHFE 10 + LME 6 slug lcpt/lalt/lldt/lznt/lnkt/ltnt）保留；市场脉搏条无回归；三个 marker 各 1。
- 链接校验：DOM 结构自检通过；9 条今日链接中 2 条（中国网 / news.com.au）因沙箱机房 IP 被站点 WAF 阻断（HTTP 000，非链接失效，根域名同样 000），2 条（和讯 / 华安期货）HTTP 200 但关键词未命中为误报；无确证死链。
- 提交 3bfbb40 → push main 成功（9138d70..3bfbb40）；deploy_pages.py → gh-pages 093c063 上线 https://pliucugb-cyber.github.io/mining-daily/ 。
- 声音：启动/推送/部署前 Windows Notify，完成时 tada（自动化亦执行）。
