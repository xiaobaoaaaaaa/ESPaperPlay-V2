# r2 引脚与掉电边界审查

2026-11-02。对应十页原生KiCad草案；不代表PCB或实测认证。

- `sd-independent-review.json`：对最终合并XML独立检查87引脚/25器件，包含源文件SHA256；`check_sd_independent.py`是该检查器，不导入绘图脚本。
- `audio-merged-review.json`：最终音频86引脚/24器件及跨页控制、值检查；记录原生文件和网表SHA256。
- `epd-pin-review.json`、`epd-review-notes.json`：按屏厂p6/7/38及缓冲/功率器件原厂脚表审查的设计依据；早期草稿路径为审查历史。
- `tmux1511-control-review.json`：控制输入最坏漏电、10k默认下拉和供电坡度边界。
- `sd-nexperia-rejected-review.json`：不选74CBTLV3245的额定依据；不是当前BOM。
- `audio-review-notes.json`、`audio-pin-net-review.csv`：音频最终设计依据、86引脚映射和未验证项。

正式工程连接检查使用[独立契约](../tools/peripheral-pin-contract.json)与[检查器](../tools/check_peripheral_netlist.py)；原厂来源集中于[资料索引](../../reference/peripherals/README.md)。生成器与临时目录中的审查产物不是正式源文件；正式工程以本目录上级原生KiCad文件为准。
