# 布局阶段证据

本目录为历史布局检查点，数量和叠层结论仅对应当时输入。当前布线结果请读[PCB布线复核](../pcb-routing/pcb-routing-review.md)及[检查点](../checkpoint-status.json)；本目录旧报告不随新源文件换哈希冒充复跑。

先读 [layout-review.md](layout-review.md)。本目录内容不可用于制造放行。

- 两套主 CAM 报告由 verification/ 脚本直接对本目录的 ZIP 和 state 复跑。
- J501/U803、机械、MIC阈值等专项报告保留当时的 build/ 输入路径；其对应文件内容在当前源/ZIP/state 中冻结，SHA-256 映射见 artifact-hashes.json，不要求读者拥有本机 build/。
- native-board-check.json 为完整原生 DRC/规则读回。771项连接错误保留，没有忽略或关闭连接检查。
- archive-coherence.json 对实际归档、PCB及8个封装精确比较。GEOMETRY_RULES_PASS_STACK_PENDING 和退出码2明确保留物理叠层未保存问题。
- stack-mic-patches-review.json 是未持久化的候选叠层/早期组件规则计划；实际MIC采用REGION，当前结果以 mic-rule-persistence-review.json 为准。
