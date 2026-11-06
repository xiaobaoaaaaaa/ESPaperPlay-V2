# 主控与 USB 原厂资料

检索日期：2026-11-02。用于开发验证板 r1 原理图；器件为候选，没有通过整板 USB/ESD 或功耗认证。

[sources.json](sources.json)保存官方 URL、大小、SHA-256、器件脚序与设计边界；本地 PDF/HTML 不进入 Git，版权属于各原厂。使用前在本目录执行 `sha256sum -c SHA256SUMS`。若官网下载文件变化，应重新核对，不可仅沿用旧结论。

| 资料 | 落图用途 |
| --- | --- |
| [ESP32-S3-WROOM-1/1U v1.8](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf) | N16R8型号、实际41个焊盘、GPIO35/36/37保留、模组地与天线约束 |
| [乐鑫原理图指南](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html) | EN/BOOT、去耦、USB串阻和调谐电容预留 |
| [乐鑫布局指南](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html) | USB 90 Ω差分阻抗、器件位置、回流及模组天线布局 |
| [TI TPD2E2U06](https://www.ti.com/lit/ds/symlink/tpd2e2u06.pdf) | 数据/CC各一只，两路对地保护，DCK pin1/2=IO，pin3=GND；无VBUS电源脚 |
| [AOS SMAJ6.0A](https://www.aosmd.com/sites/default/files/res/datasheets/SMAJ6.0A.pdf) | USB分支6 V工作反向电压TVS，KiCad pin1=K、pin2=A；不是持续过压控制器 |
| [Bourns MF-MSMF](https://www.bourns.com/docs/product-datasheets/mf-msmf.pdf?sfvrsn=4a75e5c0_69) | MF-MSMF110/16X-2，1812、16 V；1.10 A hold/2.20 A trip是23°C条件，不是精确限流 |
| [USB-IF Type-C Release 2.0](https://www.usb.org/sites/default/files/USB%20Type-C%20Spec%20R2.0%20-%20August%202019_0.pdf) | 受电设备的独立CC下拉和5 V接口边界；引用该版不表示通过现行认证 |

USB口至主板为设备受电方向，不实现PD、Host或CC电流识别。PTC与TVS仅在USB支路；J101台架输入要求已知稳压、限流5 V，必须经J502选择，不能把两路电源短接。TVS反漏、VBUS检测等绕过BQ输入限流的电流应计入整口测量。PTC复位后最大0.20 Ω带来的低压启动裕量要实测。
